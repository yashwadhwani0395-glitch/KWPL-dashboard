import streamlit as st
import plotly.graph_objects as go
from db import query
from config import SALES_IN, PURCHASE_IN, PURCHASE_ALL_IN, NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col
from components.kpi_cards import kpi_row
from components.charts import grouped_bar, bar_chart, pie_chart

_CR = 10_000_000  # 1 Crore


def render():
    st.header("Business Overview")
    date_filter = st.session_state.get("date_filter", "")
    st.divider()

    # ── KPIs ──────────────────────────────────────────────────────────────────
    # Total Sales from TrVocItem (product-level, excludes free items).
    # Combined query also fetches purchases to save a round-trip.
    # Purchases = company invoices (PU) + excise duty paid to Maharashtra govt (BP/CE).
    # For out-of-state/imported goods, companies invoice ex-excise; KWPL pays excise
    # separately via bank/cash — those BP/CE vouchers carry TrVocItem lines tracking
    # the exact bottles. Balance sheet Purchases ≈ PU + BP + CE TrVocItem ≈ ₹432 Cr.
    kpi_vol = query(f"""
        SELECT
            SUM(CASE WHEN t.ShortName='MS'
                     AND ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalAmount ELSE 0 END) AS total_sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_ALL_IN})
                     AND ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalAmount ELSE 0 END) AS total_purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_ALL_IN}))
          {NOT_CANCELLED} {date_filter}
    """)
    # Invoice count: only vouchers with actual product lines (excludes accounting-only entries)
    kpi_cnt = query(f"""
        SELECT COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS total_invoices
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} AND ISNULL(i.FreeItemYN,'N')<>'Y' {date_filter}
    """)
    kpi_ar = query(f"""
        SELECT COUNT(DISTINCT d.PartyID) AS active_customers
        FROM (
            SELECT h.TransTypeID, h.VoucherNo
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ('MS','LD')
              {NOT_CANCELLED} {date_filter}
        ) v
        JOIN TrVocDetail d ON d.TransTypeID=v.TransTypeID AND d.VoucherNo=v.VoucherNo
        WHERE d.DrCrIndicator='D' AND LEFT(d.PartyID, 1) = 'D'
    """)
    _cutoff  = st.session_state.get("outstanding_cutoff")
    _bal_col = "CloseBal" if _cutoff else "CloseBalTmp"
    kpi_os = query(f"""
        SELECT SUM({_bal_col}) AS total_outstanding
        FROM MsPartyOpening
        WHERE LEFT(PartyID, 1) = 'D'
    """)
    # Stock from MsItemBatchOpening — ERP pre-computed live stock (ClosingQtyTmp).
    # Valued at ValuationBottleRate (balance-sheet rate, not MRP).
    stock_val = query("""
        SELECT
            SUM(ob.ClosingQtyTmp)                                  AS stock_bottles,
            SUM(ob.ClosingQtyTmp * m.ValuationBottleRate)          AS stock_value
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.ClosingQtyTmp > 0
    """)

    kpi_row([
        {"label": "Total Sales",         "value": kpi_vol["total_sales"][0],      "fmt": "inr"},
        {"label": "Total Purchases",     "value": kpi_vol["total_purchases"][0],  "fmt": "inr"},
        {"label": "Total Invoices",      "value": kpi_cnt["total_invoices"][0],   "fmt": "qty"},
        {"label": "Active Customers",    "value": kpi_ar["active_customers"][0],  "fmt": "qty"},
        {"label": "Outstanding",         "value": kpi_os["total_outstanding"][0], "fmt": "inr"},
        {"label": "Stock (Valuation)",   "value": stock_val["stock_value"][0],    "fmt": "inr"},
    ])

    st.divider()

    # ── Monthly Trend: Sales / Collections / Purchases ─────────────────────────
    st.subheader("Monthly Trend — Sales, Collections & Purchases")
    df_trend = query(f"""
        SELECT
            YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
            SUM(CASE WHEN t.ShortName='MS'
                     THEN i.TotalAmount ELSE 0 END) AS sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_ALL_IN})
                     THEN i.TotalAmount ELSE 0 END) AS purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_ALL_IN}))
          {NOT_CANCELLED} AND ISNULL(i.FreeItemYN,'N')<>'Y'
          {date_filter}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
        ORDER BY yr, mo
    """)
    # BR/CR vouchers in this ERP debit the customer (DR=D%) when cash is received —
    # opposite to standard convention. Collections = DrCrIndicator='D' on D% in BR/CR.
    df_coll = query(f"""
        SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
               SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR')
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D' AND LEFT(d.PartyID, 1) = 'D'
          {date_filter}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
        ORDER BY yr, mo
    """)

    if not df_trend.empty:
        df_trend = month_col(df_trend)
        if not df_coll.empty:
            df_coll = month_col(df_coll)
            df_trend = df_trend.merge(
                df_coll[["month", "collections"]], on="month", how="left"
            ).fillna(0)
        else:
            df_trend["collections"] = 0

        for col in ["sales", "collections", "purchases"]:
            df_trend[f"{col}_cr"] = df_trend[col] / _CR

        fig = grouped_bar(df_trend, x="month", series=[
            {"col": "sales_cr",       "name": "Sales",       "color": COLORS["sales"]},
            {"col": "collections_cr", "name": "Collections", "color": COLORS["collection"]},
            {"col": "purchases_cr",   "name": "Purchases",   "color": COLORS["purchase"]},
        ])
        fig.update_layout(yaxis_title="₹ Crores")
        fig.update_traces(hovertemplate="%{x}<br>₹%{y:.2f} Cr<extra></extra>")
        st.plotly_chart(fig, use_container_width=True, key="ov_monthly")

    st.divider()

    # ── Sales by Company (from ERP MsBrandMaster.CompanyID) ─────────────────────
    st.subheader("Sales by Company")
    _COMPANY_COLORS = [
        "#7B2D8B","#E84855","#F7B731","#28A745","#2E86AB",
        "#8B4513","#FF6B6B","#4ECDC4","#6C757D","#C0392B",
    ]
    df_prin = query(f"""
        SELECT COALESCE(p.PartyName,'Others') AS company,
               SUM(i.TotalAmount)    AS sales,
               SUM(i.TotalBottleQty) AS bottles
        FROM TrVocHead h
        JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsItemMaster m ON m.ItemID=i.ItemID
        LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
        LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
        GROUP BY COALESCE(p.PartyName,'Others')
        ORDER BY sales DESC
    """)

    if not df_prin.empty:
        comp_colors = [_COMPANY_COLORS[i % len(_COMPANY_COLORS)]
                       for i in range(len(df_prin))]
        col_l, col_r = st.columns(2)
        with col_l:
            fig_pie = pie_chart(df_prin, "company", "sales", "Share by Value",
                                colors=comp_colors)
            fig_pie.update_traces(
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>%{percent}<extra></extra>",
            )
            st.plotly_chart(fig_pie, use_container_width=True, key="ov_prin_pie")
        with col_r:
            df_pr = df_prin.copy()
            df_pr["sales_cr"] = df_pr["sales"] / _CR
            fig_bar = go.Figure(go.Bar(
                x=df_pr["sales_cr"], y=df_pr["company"],
                orientation="h", marker_color=comp_colors,
                text=df_prin["sales"].apply(fmt_inr), textposition="auto",
            ))
            fig_bar.update_layout(
                xaxis_title="₹ Crores",
                yaxis={"categoryorder": "total ascending"},
                margin=dict(t=10, b=10),
            )
            st.plotly_chart(fig_bar, use_container_width=True, key="ov_prin_bar")

    # ── Monthly Sales by Company (stacked) ────────────────────────────────────
    st.subheader("Monthly Sales by Company")
    df_pm = query(f"""
        SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
               COALESCE(p.PartyName,'Others') AS company,
               SUM(i.TotalAmount) AS sales
        FROM TrVocHead h
        JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsItemMaster m ON m.ItemID=i.ItemID
        LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
        LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate)), COALESCE(p.PartyName,'Others')
        ORDER BY yr, mo
    """)

    if not df_pm.empty:
        df_pm = month_col(df_pm)
        top_companies = (df_pm.groupby("company")["sales"].sum()
                         .sort_values(ascending=False).head(8).index.tolist())
        df_pm["company"] = df_pm["company"].where(
            df_pm["company"].isin(top_companies), "Others"
        )
        df_wide = (
            df_pm.pivot_table(index="month", columns="company", values="sales", aggfunc="sum")
            .fillna(0).reset_index()
        )
        companies = [c for c in df_wide.columns if c != "month"]
        fig_stack = go.Figure()
        for i, co in enumerate(companies):
            fig_stack.add_trace(go.Bar(
                name=co, x=df_wide["month"], y=df_wide[co] / _CR,
                marker_color=_COMPANY_COLORS[i % len(_COMPANY_COLORS)],
                hovertemplate="<b>%{x}</b><br>" + co + "<br>₹%{y:.2f} Cr<extra></extra>",
            ))
        fig_stack.update_layout(
            barmode="stack", legend=dict(orientation="h", y=1.1),
            margin=dict(t=10, b=10), yaxis_title="₹ Crores",
        )
        st.plotly_chart(fig_stack, use_container_width=True, key="ov_prin_stack")

    st.divider()

    # ── Brand / Item drill-down ────────────────────────────────────────────────
    view = st.radio("Drill down by", ["Brand", "Item"], horizontal=True)
    col_l, col_r = st.columns(2)

    if view == "Brand":
        df_br = query(f"""
            SELECT b.BrandName AS label, SUM(i.TotalAmount) AS sales,
                   SUM(i.TotalBottleQty) AS bottles
            FROM TrVocItem i
            JOIN TrVocHead h  ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsItemMaster m  ON m.ItemID  = i.ItemID
            JOIN MsBrandMaster b ON b.BrandID = m.BrandID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY b.BrandName ORDER BY sales DESC
        """)
        with col_l:
            st.plotly_chart(
                bar_chart(df_br.head(15), x="label", y="sales",
                          title="Top 15 Brands by Value", color_scale="Purples"),
                use_container_width=True, key="ov_br_val"
            )
        with col_r:
            st.plotly_chart(
                bar_chart(df_br.head(15).sort_values("bottles", ascending=False),
                          x="label", y="bottles",
                          title="Top 15 Brands by Volume", color_scale="Blues"),
                use_container_width=True, key="ov_br_vol"
            )

    else:  # Item
        df_it = query(f"""
            SELECT TOP 20 m.ItemDescription AS label,
                   SUM(i.TotalAmount) AS sales, SUM(i.TotalBottleQty) AS bottles
            FROM TrVocItem i
            JOIN TrVocHead h  ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsItemMaster m ON m.ItemID = i.ItemID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY m.ItemDescription ORDER BY sales DESC
        """)
        with col_l:
            st.plotly_chart(
                bar_chart(df_it, x="label", y="sales", orientation="h",
                          title="Top 20 Items by Value", color_scale="Oranges"),
                use_container_width=True, key="ov_it_val"
            )
        with col_r:
            st.plotly_chart(
                bar_chart(df_it.sort_values("bottles", ascending=False),
                          x="label", y="bottles", orientation="h",
                          title="Top 20 Items by Volume", color_scale="Greens"),
                use_container_width=True, key="ov_it_vol"
            )

    st.divider()

    # ── Top 10 Customers ──────────────────────────────────────────────────────
    # All DR billing entries to D% customer accounts across all transaction types,
    # excluding BR/CR (collections) so only goods/excise charges to customers count.
    st.subheader("Top 10 Customers by Billing")
    df_cust = query(f"""
        SELECT TOP 10 p.PartyName AS customer,
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
    if not df_cust.empty:
        st.plotly_chart(
            bar_chart(df_cust, x="customer", y="sales",
                      orientation="h", color_scale="Purples"),
            use_container_width=True, key="ov_top_cust"
        )
