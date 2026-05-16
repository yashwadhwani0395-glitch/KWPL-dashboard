import streamlit as st
import plotly.graph_objects as go
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS, brand_case, PRINCIPAL_COLORS, PRINCIPAL_ORDER
from utils import fmt_inr, fmt_qty, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart, grouped_bar


def render():
    st.header("Sales")
    date_filter = st.session_state.get("date_filter", "")

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpi = query(f"""
        SELECT
            COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR) + '|' + h.VoucherNo) AS invoices,
            SUM(i.TotalAmount)    AS sales,
            SUM(i.TotalBottleQty) AS bottles,
            SUM(i.CaseQty)        AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
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
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
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
        df_prin = query(f"""
            SELECT COALESCE(p.PartyName,'Others') AS company,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsItemMaster m ON m.ItemID=i.ItemID
            LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
            LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
            GROUP BY COALESCE(p.PartyName,'Others')
            ORDER BY sales DESC
        """)
        if not df_prin.empty:
            comp_colors = [_COMP_COLORS[i % len(_COMP_COLORS)] for i in range(len(df_prin))]
            st.plotly_chart(pie_chart(df_prin, "company", "sales",
                                     colors=comp_colors),
                            use_container_width=True, key="sl_prin_pie")

    # ── Daily last 30 days ────────────────────────────────────────────────────
    st.subheader("Daily Sales — Last 30 Days")
    df_d = query(f"""
        SELECT CAST(COALESCE(h.TPDate, h.VoucherDate) AS DATE) AS sale_date,
               SUM(i.TotalAmount) AS sales
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          AND COALESCE(h.TPDate, h.VoucherDate) >= DATEADD(DAY,-30,GETDATE())
        GROUP BY CAST(COALESCE(h.TPDate, h.VoucherDate) AS DATE)
        ORDER BY sale_date
    """)
    if not df_d.empty:
        st.plotly_chart(bar_chart(df_d, x="sale_date", y="sales",
                                  color=COLORS["info"]),
                        use_container_width=True, key="sl_daily")

    st.divider()

    # ── Principal (Brand Group) Breakdown ─────────────────────────────────────
    st.subheader("Sales by Principal (Brand Group)")
    _bc = brand_case("m")
    df_principal = query(f"""
        SELECT {_bc} AS principal,
               SUM(i.TotalAmount)    AS sales,
               SUM(i.TotalBottleQty) AS bottles,
               COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS invoices
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsItemMaster m ON m.ItemID=i.ItemID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
        GROUP BY {_bc}
        ORDER BY sales DESC
    """)
    if not df_principal.empty:
        # Sort by defined order
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

        # Monthly stacked by principal
        st.subheader("Monthly Sales by Principal")
        _bc_m = brand_case("m")
        df_pm = query(f"""
            SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr,
                   MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
                   {_bc_m} AS principal,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsItemMaster m ON m.ItemID=i.ItemID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
            GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)),
                     MONTH(COALESCE(h.TPDate, h.VoucherDate)),
                     {_bc_m}
            ORDER BY yr, mo
        """)
        if not df_pm.empty:
            df_pm = month_col(df_pm)
            df_wide = (
                df_pm.pivot_table(index="month", columns="principal",
                                  values="sales", aggfunc="sum")
                .fillna(0).reset_index()
            )
            principals = [p for p in PRINCIPAL_ORDER if p in df_wide.columns]
            principals += [c for c in df_wide.columns if c != "month" and c not in principals]
            fig_stack = go.Figure()
            for pr in principals:
                if pr in df_wide.columns:
                    fig_stack.add_trace(go.Bar(
                        name=pr, x=df_wide["month"], y=df_wide[pr] / 1_00_00_000,
                        marker_color=PRINCIPAL_COLORS.get(pr, "#6C757D"),
                        hovertemplate="<b>%{x}</b><br>" + pr + "<br>₹%{y:.2f} Cr<extra></extra>",
                    ))
            fig_stack.update_layout(
                barmode="stack", legend=dict(orientation="h", y=1.1),
                margin=dict(t=10, b=10), yaxis_title="₹ Crores",
            )
            st.plotly_chart(fig_stack, use_container_width=True, key="sl_principal_stack")

        # Summary table with download
        df_p_disp = df_principal[["principal", "sales", "bottles", "invoices"]].copy()
        df_p_csv  = df_p_disp.copy()
        df_p_disp["sales"]   = df_p_disp["sales"].apply(fmt_inr)
        df_p_disp["bottles"] = df_p_disp["bottles"].apply(fmt_qty)
        df_p_disp.columns = ["Principal", "Sales", "Bottles", "Invoices"]
        st.dataframe(df_p_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Principal CSV",
            data=df_p_csv.to_csv(index=False),
            file_name="sales_by_principal.csv",
            mime="text/csv",
            key="sl_dl_principal",
        )

    st.divider()

    # ── Top customers + Salesman ──────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Top 15 Customers")
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
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter} AND s.ResignDate IS NULL
            GROUP BY s.FullName ORDER BY sales DESC
        """)
        if not df_sm.empty:
            st.plotly_chart(bar_chart(df_sm, x="salesman", y="sales",
                                      color_scale="Oranges"),
                            use_container_width=True, key="sl_sman")

    st.divider()

    # ── Brands ────────────────────────────────────────────────────────────────
    st.subheader("Brand Performance")
    df_br = query(f"""
        SELECT TOP 15 b.BrandName AS brand,
               SUM(i.TotalAmount) AS sales, SUM(i.TotalBottleQty) AS bottles
        FROM TrVocItem i
        JOIN TrVocHead h  ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsItemMaster m ON m.ItemID=i.ItemID
        JOIN MsBrandMaster b ON b.BrandID=m.BrandID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
        GROUP BY b.BrandName ORDER BY sales DESC
    """)
    col_l, col_r = st.columns(2)
    with col_l:
        if not df_br.empty:
            st.plotly_chart(bar_chart(df_br, x="brand", y="sales",
                                      title="By Value", color_scale="Teal"),
                            use_container_width=True, key="sl_br_val")
    with col_r:
        if not df_br.empty:
            st.plotly_chart(bar_chart(df_br.sort_values("bottles", ascending=False),
                                      x="brand", y="bottles",
                                      title="By Volume", color_scale="Blues"),
                            use_container_width=True, key="sl_br_vol")

    # ── Salesman detail table with download ───────────────────────────────────
    if not df_sm.empty:
        st.divider()
        st.subheader("Salesman Detail")
        df_disp = df_sm[["salesman", "sales", "invoices"]].copy()
        df_csv  = df_sm[["salesman", "sales", "invoices"]].copy()
        df_disp["sales"] = df_disp["sales"].apply(fmt_inr)
        df_disp.columns = ["Salesman", "Total Sales", "Invoices"]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Salesman CSV",
            data=df_csv.to_csv(index=False),
            file_name="salesman_performance.csv",
            mime="text/csv",
            key="sl_dl_sman",
        )
