import streamlit as st
import plotly.graph_objects as go
from db import query
from config import (SALES_IN, PURCHASE_IN, NOT_CANCELLED, NOT_FREE, COLORS,
                    brand_case, PRINCIPAL_COLORS, PRINCIPAL_ORDER)
from utils import fmt_inr, fmt_qty, month_col
from components.kpi_cards import kpi_row
from components.charts import grouped_bar, bar_chart, pie_chart


def render():
    st.header("Business Overview")

    # ── Financial Year selector ───────────────────────────────────────────────
    FY_OPTIONS = {
        "Current FY (Apr 2026 – Present)": ("2026-04-01", None),
        "FY 2025-26 (Apr 2025 – Mar 2026)": ("2025-04-01", "2026-03-31"),
        "All Years":                         (None,        None),
    }
    fy_sel = st.radio("Financial Year", list(FY_OPTIONS.keys()), horizontal=True)
    date_from, date_to = FY_OPTIONS[fy_sel]

    date_filter = ""
    if date_from:
        date_filter += f" AND h.VoucherDate >= '{date_from}'"
    if date_to:
        date_filter += f" AND h.VoucherDate <= '{date_to}'"

    st.divider()

    # ── KPIs ─────────────────────────────────────────────────────────────────
    sales_kpi = query(f"""
        SELECT SUM(i.TotalAmount)          AS total_sales,
               COUNT(DISTINCT h.VoucherNo) AS total_invoices
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
    """)
    purchase_kpi = query(f"""
        SELECT SUM(i.TotalAmount) AS total_purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
    """)
    cust_kpi = query(f"""
        SELECT COUNT(DISTINCT d.PartyID) AS active_customers
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED}
          AND d.DrCrIndicator='D' AND d.PartyID IS NOT NULL
          {date_filter}
    """)
    outstanding = query(f"""
        SELECT SUM(d.RemainingAmt) AS total_outstanding
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED}
          AND d.DrCrIndicator='D' AND d.RemainingAmt > 0
          AND d.PartyID IS NOT NULL
          {date_filter}
    """)
    stock_val = query(f"""
        SELECT SUM(sub.net_bottles * m.MrpBottRate) AS stock_value
        FROM (
            SELECT vi.ItemID,
                   SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                            THEN vi.TotalBottleQty
                            ELSE -vi.TotalBottleQty END) AS net_bottles
            FROM TrVocItem vi
            JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
            WHERE h.TransTypeID IN ({PURCHASE_IN},{SALES_IN})
              {NOT_CANCELLED} AND vi.FreeItemYN <> 'Y'
            GROUP BY vi.ItemID
        ) sub
        JOIN MsItemMaster m ON m.ItemID = sub.ItemID
        WHERE sub.net_bottles > 0
    """)

    kpi_row([
        {"label": "Total Sales",       "value": sales_kpi["total_sales"][0],        "fmt": "inr"},
        {"label": "Total Purchases",   "value": purchase_kpi["total_purchases"][0], "fmt": "inr"},
        {"label": "Total Invoices",    "value": sales_kpi["total_invoices"][0],     "fmt": "qty"},
        {"label": "Active Customers",  "value": cust_kpi["active_customers"][0],    "fmt": "qty"},
        {"label": "Outstanding",       "value": outstanding["total_outstanding"][0],"fmt": "inr"},
        {"label": "Stock Value (MRP)", "value": stock_val["stock_value"][0],        "fmt": "inr"},
    ])

    st.divider()

    # ── Monthly Trend: Sales / Collections / Purchases ────────────────────────
    st.subheader("Monthly Trend — Sales, Collections & Purchases")
    df_trend = query(f"""
        SELECT
            YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN t.ShortName='MS'
                     THEN i.TotalAmount ELSE 0 END)  AS sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                     THEN i.TotalAmount ELSE 0 END)  AS purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_IN}))
          {NOT_CANCELLED} AND i.FreeItemYN<>'Y'
          {date_filter}
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """)
    df_coll = query(f"""
        SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
               SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR') {NOT_CANCELLED}
          AND d.DrCrIndicator='C'
          {date_filter}
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """)

    if not df_trend.empty:
        df_trend = month_col(df_trend)
        if not df_coll.empty:
            df_coll = month_col(df_coll)
            df_trend = df_trend.merge(df_coll[["month", "collections"]], on="month", how="left").fillna(0)
        else:
            df_trend["collections"] = 0
        st.plotly_chart(
            grouped_bar(df_trend, x="month", series=[
                {"col": "sales",       "name": "Sales",       "color": COLORS["sales"]},
                {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
                {"col": "purchases",   "name": "Purchases",   "color": COLORS["purchase"]},
            ]),
            use_container_width=True, key="ov_monthly"
        )

    st.divider()

    # ── Sales by Principal ────────────────────────────────────────────────────
    st.subheader("Sales by Principal")
    df_prin = query(f"""
        SELECT principal, SUM(sales) AS sales, SUM(bottles) AS bottles
        FROM (
            SELECT {brand_case("i")} AS principal,
                   i.TotalAmount AS sales, i.TotalBottleQty AS bottles
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
        ) t
        GROUP BY principal
        ORDER BY sales DESC
    """)

    if not df_prin.empty:
        col_l, col_r = st.columns(2)
        prin_colors = [PRINCIPAL_COLORS.get(p, "#6C757D") for p in df_prin["principal"]]

        with col_l:
            fig_pie = pie_chart(df_prin, "principal", "sales", "Share by Value",
                                colors=prin_colors)
            st.plotly_chart(fig_pie, use_container_width=True, key="ov_prin_pie")

        with col_r:
            fig_bar = go.Figure(go.Bar(
                x=df_prin["sales"],
                y=df_prin["principal"],
                orientation="h",
                marker_color=prin_colors,
                text=df_prin["sales"].apply(fmt_inr),
                textposition="auto",
            ))
            fig_bar.update_layout(
                xaxis_title="₹", yaxis={"categoryorder": "total ascending"},
                margin=dict(t=10, b=10),
            )
            st.plotly_chart(fig_bar, use_container_width=True, key="ov_prin_bar")

    # ── Monthly Sales by Principal (stacked) ──────────────────────────────────
    st.subheader("Monthly Sales by Principal")
    df_pm = query(f"""
        SELECT yr, mo, principal, SUM(sales) AS sales
        FROM (
            SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                   {brand_case("i")} AS principal,
                   i.TotalAmount AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
        ) t
        GROUP BY yr, mo, principal
        ORDER BY yr, mo
    """)

    if not df_pm.empty:
        df_pm = month_col(df_pm)
        df_wide = (
            df_pm.pivot_table(index="month", columns="principal", values="sales", aggfunc="sum")
            .reindex(columns=[p for p in PRINCIPAL_ORDER if p in df_pm["principal"].unique()])
            .fillna(0)
            .reset_index()
        )
        fig_stack = go.Figure()
        for p in [c for c in df_wide.columns if c != "month"]:
            fig_stack.add_trace(go.Bar(
                name=p,
                x=df_wide["month"],
                y=df_wide[p],
                marker_color=PRINCIPAL_COLORS.get(p, "#6C757D"),
            ))
        fig_stack.update_layout(
            barmode="stack",
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=10, b=10),
            yaxis_title="₹",
        )
        st.plotly_chart(fig_stack, use_container_width=True, key="ov_prin_stack")

    st.divider()

    # ── Brand / Item drill-down ───────────────────────────────────────────────
    view = st.radio("Drill down by", ["Brand", "Item"], horizontal=True)
    col_l, col_r = st.columns(2)

    if view == "Brand":
        df_br = query(f"""
            SELECT b.BrandName AS label, SUM(i.TotalAmount) AS sales,
                   SUM(i.TotalBottleQty) AS bottles
            FROM TrVocItem i
            JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
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
            JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsItemMaster m ON m.ItemID=i.ItemID
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

    # ── Top 10 Customers ─────────────────────────────────────────────────────
    st.subheader("Top 10 Customers by Sales")
    df_cust = query(f"""
        SELECT TOP 10 p.PartyName AS customer,
               SUM(i.TotalAmount) AS sales,
               COUNT(DISTINCT h.VoucherNo) AS invoices
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
          AND d.DrCrIndicator='D'
          {date_filter}
        GROUP BY p.PartyName ORDER BY sales DESC
    """)
    if not df_cust.empty:
        st.plotly_chart(
            bar_chart(df_cust, x="customer", y="sales",
                      orientation="h", color_scale="Purples"),
            use_container_width=True, key="ov_top_cust"
        )
