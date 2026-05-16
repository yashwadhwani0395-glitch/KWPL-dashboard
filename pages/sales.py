import streamlit as st
import plotly.graph_objects as go
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS, brand_case, PRINCIPAL_COLORS, PRINCIPAL_ORDER
from utils import fmt_inr, fmt_qty, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart, grouped_bar

# Service items (S00xxx) live in TrVocItem alongside product lines.
# Filtering i.BrandID IS NOT NULL excludes them — only product lines have a brand.
_PRODUCT_ONLY = "AND i.BrandID IS NOT NULL"


def render():
    st.header("Sales")
    date_filter = st.session_state.get("date_filter", "")

    # ── KPIs ──────────────────────────────────────────────────────────────────
    # All KPIs from TrVocItem (product lines only: BrandID IS NOT NULL excludes S00xxx service items).
    kpi = query(f"""
        SELECT
            COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS invoices,
            SUM(i.TotalAmount)    AS sales,
            SUM(i.TotalBottleQty) AS bottles,
            SUM(i.CaseQty)        AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {_PRODUCT_ONLY}
          {date_filter}
    """)
    kpi_row([
        {"label": "Invoices",     "value": kpi["invoices"][0], "fmt": "qty"},
        {"label": "Total Sales",  "value": kpi["sales"][0],    "fmt": "inr"},
        {"label": "Bottles Sold", "value": kpi["bottles"][0],  "fmt": "qty"},
        {"label": "Cases Sold",   "value": kpi["cases"][0],    "fmt": "qty"},
    ])

    st.divider()

    # ── Monthly trend + Company pie ───────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Sales Trend")
        df_m = query(f"""
            SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr,
                   MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {_PRODUCT_ONLY}
              {date_filter}
            GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)),
                     MONTH(COALESCE(h.TPDate, h.VoucherDate))
            ORDER BY yr, mo
        """)
        if not df_m.empty:
            df_m = month_col(df_m)
            df_m = scale_cr(df_m, 'sales')
            st.plotly_chart(bar_chart(df_m, x="month", y="sales",
                                      color=COLORS["sales"],
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="sl_monthly")

    with col_r:
        st.subheader("Sales by Company")
        _COMP_COLORS = [
            "#7B2D8B","#E84855","#F7B731","#28A745","#2E86AB",
            "#8B4513","#FF6B6B","#4ECDC4","#6C757D","#C0392B",
        ]
        # Company = principal company linked to brand via MsBrandMaster.CompanyID → MsPartyMaster.
        df_co = query(f"""
            SELECT COALESCE(p.PartyName,'Others') AS company,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
            LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {_PRODUCT_ONLY} {date_filter}
            GROUP BY COALESCE(p.PartyName,'Others')
            ORDER BY sales DESC
        """)
        if not df_co.empty:
            comp_colors = [_COMP_COLORS[i % len(_COMP_COLORS)] for i in range(len(df_co))]
            st.plotly_chart(pie_chart(df_co, "company", "sales",
                                     colors=comp_colors),
                            use_container_width=True, key="sl_co_pie")

    # ── Daily last 30 days ────────────────────────────────────────────────────
    st.subheader("Daily Sales — Last 30 Days")
    df_d = query(f"""
        SELECT CAST(COALESCE(h.TPDate, h.VoucherDate) AS DATE) AS sale_date,
               SUM(i.TotalAmount) AS sales
        FROM TrVocHead h
        JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {_PRODUCT_ONLY}
          AND COALESCE(h.TPDate, h.VoucherDate) >= DATEADD(DAY,-30,GETDATE())
        GROUP BY CAST(COALESCE(h.TPDate, h.VoucherDate) AS DATE)
        ORDER BY sale_date
    """)
    if not df_d.empty:
        st.plotly_chart(bar_chart(df_d, x="sale_date", y="sales",
                                  color=COLORS["info"]),
                        use_container_width=True, key="sl_daily")

    st.divider()

    # ── Brand-wise Breakdown ──────────────────────────────────────────────────
    # Primary analysis: sales by brand. TrVocItem.BrandID → MsBrandMaster.
    # Service items (TCS, excise, discounts) have BrandID = NULL, excluded by join.
    st.subheader("Brand-wise Sales")
    df_brand = query(f"""
        SELECT b.BrandName AS brand,
               SUM(i.TotalAmount)    AS sales,
               SUM(i.TotalBottleQty) AS bottles,
               COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS invoices
        FROM TrVocHead h
        JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsBrandMaster b ON b.BrandID=i.BrandID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
        GROUP BY b.BrandName
        ORDER BY sales DESC
    """)

    if not df_brand.empty:
        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(
                bar_chart(df_brand.head(20), x="brand", y="sales",
                          orientation="h", color_scale="Purples",
                          title="Top 20 Brands by Value",
                          yaxis_title="₹"),
                use_container_width=True, key="sl_brand_val"
            )
        with col_r:
            st.plotly_chart(
                bar_chart(df_brand.head(20).sort_values("bottles", ascending=False),
                          x="brand", y="bottles",
                          orientation="h", color_scale="Blues",
                          title="Top 20 Brands by Volume (Bottles)",
                          yaxis_title="Bottles"),
                use_container_width=True, key="sl_brand_vol"
            )

        # Monthly brand trend — top 8 brands stacked
        st.subheader("Monthly Sales by Brand (Top 8)")
        top8 = df_brand.head(8)["brand"].tolist()
        df_bm = query(f"""
            SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr,
                   MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
                   b.BrandName AS brand,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)),
                     MONTH(COALESCE(h.TPDate, h.VoucherDate)),
                     b.BrandName
            ORDER BY yr, mo
        """)
        if not df_bm.empty:
            df_bm = month_col(df_bm)
            df_bm["brand"] = df_bm["brand"].where(df_bm["brand"].isin(top8), "Others")
            df_wide = (
                df_bm.pivot_table(index="month", columns="brand",
                                  values="sales", aggfunc="sum")
                .fillna(0).reset_index()
            )
            brands_ordered = top8 + (["Others"] if "Others" in df_wide.columns else [])
            _PALETTE = [
                "#7B2D8B","#E84855","#F7B731","#28A745","#2E86AB",
                "#8B4513","#FF6B6B","#4ECDC4","#6C757D","#C0392B",
            ]
            fig_bm = go.Figure()
            for i, br in enumerate([b for b in brands_ordered if b in df_wide.columns]):
                fig_bm.add_trace(go.Bar(
                    name=br, x=df_wide["month"], y=df_wide[br] / 1_00_00_000,
                    marker_color=_PALETTE[i % len(_PALETTE)],
                    hovertemplate="<b>%{x}</b><br>" + br + "<br>₹%{y:.2f} Cr<extra></extra>",
                ))
            fig_bm.update_layout(
                barmode="stack", legend=dict(orientation="h", y=1.1),
                margin=dict(t=10, b=10), yaxis_title="₹ Crores",
            )
            st.plotly_chart(fig_bm, use_container_width=True, key="sl_brand_stack")

        # Full brand table with download
        df_brand_disp = df_brand.copy()
        df_brand_csv  = df_brand.copy()
        df_brand_disp["sales"]   = df_brand_disp["sales"].apply(fmt_inr)
        df_brand_disp["bottles"] = df_brand_disp["bottles"].apply(fmt_qty)
        df_brand_disp.columns    = ["Brand", "Sales", "Bottles", "Invoices"]
        st.dataframe(df_brand_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Brand CSV",
            data=df_brand_csv.to_csv(index=False),
            file_name="brand_sales.csv",
            mime="text/csv",
            key="sl_dl_brand",
        )

    st.divider()

    # ── Principal Group Breakdown (secondary view) ────────────────────────────
    with st.expander("Sales by Principal Group (Diageo / USL / UB / Brown-Forman / Wines)"):
        _bc = brand_case("b")
        df_principal = query(f"""
            SELECT {_bc} AS principal,
                   SUM(i.TotalAmount)    AS sales,
                   SUM(i.TotalBottleQty) AS bottles
            FROM TrVocHead h
            JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
            GROUP BY {_bc}
            ORDER BY sales DESC
        """)
        if not df_principal.empty:
            df_principal["_sort"] = df_principal["principal"].map(
                {p: i for i, p in enumerate(PRINCIPAL_ORDER)}
            ).fillna(99)
            df_principal = df_principal.sort_values("_sort").drop(columns="_sort")
            colors = [PRINCIPAL_COLORS.get(p, "#6C757D") for p in df_principal["principal"]]

            col_l, col_r = st.columns(2)
            with col_l:
                fig_pie = pie_chart(df_principal, "principal", "sales",
                                    "Share by Value", colors=colors)
                fig_pie.update_traces(
                    textinfo="percent+label",
                    hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
                )
                st.plotly_chart(fig_pie, use_container_width=True, key="sl_principal_pie")
            with col_r:
                df_p = df_principal.copy()
                df_p["sales_cr"] = df_p["sales"] / 1_00_00_000
                fig_bar = go.Figure(go.Bar(
                    x=df_p["sales_cr"], y=df_p["principal"],
                    orientation="h", marker_color=colors,
                    text=df_principal["sales"].apply(fmt_inr), textposition="auto",
                ))
                fig_bar.update_layout(
                    xaxis_title="₹ Crores",
                    yaxis={"categoryorder": "total ascending"},
                    margin=dict(t=10, b=10),
                )
                st.plotly_chart(fig_bar, use_container_width=True, key="sl_principal_bar")

            df_p_disp = df_principal[["principal", "sales", "bottles"]].copy()
            df_p_disp["sales"]   = df_p_disp["sales"].apply(fmt_inr)
            df_p_disp["bottles"] = df_p_disp["bottles"].apply(fmt_qty)
            df_p_disp.columns    = ["Principal", "Sales", "Bottles"]
            st.dataframe(df_p_disp, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download Principal CSV",
                data=df_principal[["principal","sales","bottles"]].to_csv(index=False),
                file_name="sales_by_principal.csv",
                mime="text/csv",
                key="sl_dl_principal",
            )

    st.divider()

    # ── Top customers + Salesman ──────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Top 15 Customers")
        # Customer sales = DR postings to D% accounts (excludes BR/CR collections).
        df_c = query(f"""
            SELECT TOP 15 p.PartyName AS customer,
                   SUM(d.Amount) AS sales,
                   COUNT(DISTINCT CAST(d.TransTypeID AS VARCHAR)+'|'+d.VoucherNo) AS transactions
            FROM TrVocDetail d
            JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsPartyMaster p ON p.PartyID=d.PartyID
            WHERE d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
              AND t.ShortName NOT IN ('BR','CR')
              AND ISNULL(h.Cancelled,'N') <> 'Y'
              {date_filter}
            GROUP BY p.PartyName ORDER BY sales DESC
        """)
        if not df_c.empty:
            st.plotly_chart(bar_chart(df_c, x="customer", y="sales",
                                      orientation="h", color_scale="Purples"),
                            use_container_width=True, key="sl_cust")
            st.download_button(
                "⬇️ Download Top Customers CSV",
                data=df_c.to_csv(index=False),
                file_name="top_customers.csv",
                mime="text/csv",
                key="sl_dl_cust",
            )

    with col_r:
        st.subheader("Salesman Performance")
        df_sm = query(f"""
            SELECT s.FullName AS salesman,
                   SUM(i.TotalAmount) AS sales,
                   COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS invoices
            FROM TrVocHead h
            JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter} AND s.ResignDate IS NULL
            GROUP BY s.FullName ORDER BY sales DESC
        """)
        if not df_sm.empty:
            st.plotly_chart(bar_chart(df_sm, x="salesman", y="sales",
                                      color_scale="Oranges"),
                            use_container_width=True, key="sl_sman")

    # ── Salesman detail table with download ───────────────────────────────────
    if not df_sm.empty:
        st.divider()
        st.subheader("Salesman Detail")
        df_sm_csv  = df_sm[["salesman", "sales", "invoices"]].copy()
        df_sm_disp = df_sm_csv.copy()
        df_sm_disp["sales"] = df_sm_disp["sales"].apply(fmt_inr)
        df_sm_disp.columns  = ["Salesman", "Total Sales", "Invoices"]
        st.dataframe(df_sm_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Salesman CSV",
            data=df_sm_csv.to_csv(index=False),
            file_name="salesman_performance.csv",
            mime="text/csv",
            key="sl_dl_sman",
        )
