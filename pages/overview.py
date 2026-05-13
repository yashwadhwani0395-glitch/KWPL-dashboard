import streamlit as st
from db import query
from config import SALES_IN, PURCHASE_IN, NOT_CANCELLED, NOT_FREE, COLORS
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
    # Sales and invoices — ShortName='MS' is the authoritative sales filter
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

    # ── Monthly trend: Sales / Collections / Purchases ────────────────────────
    st.subheader("Monthly Trend — Sales, Collections & Purchases")
    df_trend = query(f"""
        SELECT
            YEAR(h.VoucherDate)  AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN t.ShortName='MS'
                     THEN i.TotalAmount ELSE 0 END)             AS sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                     THEN i.TotalAmount ELSE 0 END)             AS purchases
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
        WHERE t.ShortName IN ('BR','CR') {NOT_CANCELLED} AND d.DrCrIndicator='C'
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

        fig = grouped_bar(df_trend, x="month", series=[
            {"col": "sales",       "name": "Sales",       "color": COLORS["sales"]},
            {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
            {"col": "purchases",   "name": "Purchases",   "color": COLORS["purchase"]},
        ])
        st.plotly_chart(fig, use_container_width=True, key="ov_monthly")

    st.divider()

    # ── Breakdown toggle ──────────────────────────────────────────────────────
    view = st.radio("Breakdown by", ["Company", "Brand", "Item"], horizontal=True)

    col_l, col_r = st.columns(2)

    if view == "Company":
        df = query(f"""
            SELECT t.TransTypeName AS label, SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY t.TransTypeName ORDER BY sales DESC
        """)
        with col_l:
            st.plotly_chart(pie_chart(df, "label", "sales", "Sales by Company"),
                            use_container_width=True, key="ov_co_pie")
        with col_r:
            st.plotly_chart(bar_chart(df, x="label", y="sales", orientation="h",
                                      color_scale="Purples"),
                            use_container_width=True, key="ov_co_bar")

    elif view == "Brand":
        df = query(f"""
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
            st.plotly_chart(bar_chart(df.head(15), x="label", y="sales",
                                      title="Top Brands by Value", color_scale="Teal"),
                            use_container_width=True, key="ov_br_val")
        with col_r:
            st.plotly_chart(bar_chart(df.head(15).sort_values("bottles", ascending=False),
                                      x="label", y="bottles",
                                      title="Top Brands by Volume", color_scale="Blues"),
                            use_container_width=True, key="ov_br_vol")

    else:  # Item
        df = query(f"""
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
            st.plotly_chart(bar_chart(df, x="label", y="sales", orientation="h",
                                      title="Top 20 Items by Value", color_scale="Oranges"),
                            use_container_width=True, key="ov_it_val")
        with col_r:
            st.plotly_chart(bar_chart(df.sort_values("bottles", ascending=False),
                                      x="label", y="bottles", orientation="h",
                                      title="Top 20 Items by Volume", color_scale="Greens"),
                            use_container_width=True, key="ov_it_vol")
