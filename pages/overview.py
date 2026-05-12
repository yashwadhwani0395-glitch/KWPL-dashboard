import streamlit as st
from db import query
from config import SALES_IN, PURCHASE_IN, NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col
from components.kpi_cards import kpi_row
from components.charts import grouped_bar, bar_chart, pie_chart


def render():
    st.header("Business Overview")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpi = query(f"""
        SELECT
            SUM(CASE WHEN h.TransTypeID IN ({SALES_IN})
                     {NOT_CANCELLED} AND i.FreeItemYN<>'Y'
                THEN i.TotalAmount ELSE 0 END)              AS total_sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                     {NOT_CANCELLED} AND i.FreeItemYN<>'Y'
                THEN i.TotalAmount ELSE 0 END)              AS total_purchases,
            COUNT(DISTINCT CASE WHEN h.TransTypeID IN ({SALES_IN})
                     {NOT_CANCELLED}
                THEN h.VoucherNo END)                       AS total_invoices,
            COUNT(DISTINCT CASE WHEN h.TransTypeID IN ({SALES_IN})
                     {NOT_CANCELLED}
                THEN d.PartyID END)                         AS active_customers
        FROM TrVocHead h
        LEFT JOIN TrVocItem i
            ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        LEFT JOIN TrVocDetail d
            ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
            AND d.DrCrIndicator='D'
        WHERE h.TransTypeID IN ({SALES_IN},{PURCHASE_IN})
    """)
    outstanding = query(f"""
        SELECT SUM(d.RemainingAmt) AS total_outstanding
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED}
          AND d.DrCrIndicator='D' AND d.RemainingAmt > 0
    """)
    stock_val = query("""
        SELECT SUM(o.ClosingQty * m.MrpBottRate) AS stock_value
        FROM MsItemBatchOpening o
        JOIN MsItemMaster m ON m.ItemID = o.ItemID
        WHERE o.ClosingQty > 0
    """)

    kpi_row([
        {"label": "Total Sales",       "value": kpi["total_sales"][0],              "fmt": "inr"},
        {"label": "Total Purchases",   "value": kpi["total_purchases"][0],           "fmt": "inr"},
        {"label": "Total Invoices",    "value": kpi["total_invoices"][0],            "fmt": "qty"},
        {"label": "Outstanding",       "value": outstanding["total_outstanding"][0], "fmt": "inr"},
        {"label": "Stock Value (MRP)", "value": stock_val["stock_value"][0],         "fmt": "inr"},
    ])

    st.divider()

    # ── Monthly trend: Sales / Collections / Purchases ────────────────────────
    st.subheader("Monthly Trend — Sales, Collections & Purchases")
    df_trend = query(f"""
        SELECT
            YEAR(h.VoucherDate)  AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN h.TransTypeID IN ({SALES_IN})    THEN i.TotalAmount ELSE 0 END) AS sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN}) THEN i.TotalAmount ELSE 0 END) AS purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN},{PURCHASE_IN})
          {NOT_CANCELLED} AND i.FreeItemYN<>'Y'
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
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
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
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
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
            JOIN MsItemMaster m ON m.ItemID=i.ItemID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
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
