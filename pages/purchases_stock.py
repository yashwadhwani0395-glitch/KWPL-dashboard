import streamlit as st
from db import query
from config import PURCHASE_IN, NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart, grouped_bar


def render():
    st.header("Purchases & Stock")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpi = query(f"""
        SELECT
            COUNT(DISTINCT h.VoucherNo)   AS invoices,
            SUM(i.TotalAmount)            AS purchases,
            SUM(i.TotalBottleQty)         AS bottles,
            SUM(i.CaseQty)                AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
    """)
    stock = query("""
        SELECT
            COUNT(DISTINCT o.ItemID)                      AS sku_count,
            SUM(o.ClosingQty)                             AS total_bottles,
            SUM(o.ClosingQty * m.MrpBottRate)             AS stock_mrp,
            SUM(o.ClosingQty * m.PurchaseRate)            AS stock_cost
        FROM MsItemBatchOpening o
        JOIN MsItemMaster m ON m.ItemID = o.ItemID
        WHERE o.ClosingQty > 0
    """)
    kpi_row([
        {"label": "Purchase Invoices", "value": kpi["invoices"][0],           "fmt": "qty"},
        {"label": "Total Purchases",   "value": kpi["purchases"][0],          "fmt": "inr"},
        {"label": "Bottles Purchased", "value": kpi["bottles"][0],            "fmt": "qty"},
        {"label": "Stock Value (MRP)", "value": stock["stock_mrp"][0],        "fmt": "inr"},
        {"label": "Stock (Cost)",      "value": stock["stock_cost"][0],       "fmt": "inr"},
    ])

    st.divider()

    # ── Monthly purchase trend ────────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Purchase Trend")
        df_m = query(f"""
            SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                   SUM(i.TotalAmount) AS purchases
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
            ORDER BY yr, mo
        """)
        if not df_m.empty:
            df_m = month_col(df_m)
            st.plotly_chart(bar_chart(df_m, x="month", y="purchases",
                                      color=COLORS["purchase"]),
                            use_container_width=True, key="ps_monthly")

    with col_r:
        st.subheader("Purchases by Category")
        df_cat = query(f"""
            SELECT t.TransTypeName AS category, SUM(i.TotalAmount) AS purchases
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY t.TransTypeName ORDER BY purchases DESC
        """)
        if not df_cat.empty:
            st.plotly_chart(pie_chart(df_cat, "category", "purchases"),
                            use_container_width=True, key="ps_cat_pie")

    st.divider()

    # ── Top suppliers ─────────────────────────────────────────────────────────
    st.subheader("Top 15 Suppliers")
    df_sup = query(f"""
        SELECT TOP 15 p.PartyName AS supplier,
               SUM(i.TotalAmount) AS purchases,
               COUNT(DISTINCT h.VoucherNo) AS invoices,
               SUM(i.TotalBottleQty) AS bottles
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
          AND d.DrCrIndicator='C'
        GROUP BY p.PartyName ORDER BY purchases DESC
    """)
    if not df_sup.empty:
        st.plotly_chart(bar_chart(df_sup, x="supplier", y="purchases",
                                  orientation="h", color_scale="Reds"),
                        use_container_width=True, key="ps_suppliers")

    st.divider()

    # ── Brand purchase vs stock ───────────────────────────────────────────────
    st.subheader("Brand — Purchased vs In Stock")
    df_br_pur = query(f"""
        SELECT b.BrandName AS brand, SUM(i.TotalBottleQty) AS purchased
        FROM TrVocItem i
        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
        JOIN MsBrandMaster b ON b.BrandID=i.BrandID
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
        GROUP BY b.BrandName ORDER BY purchased DESC
    """)
    df_br_stk = query("""
        SELECT b.BrandName AS brand, SUM(o.ClosingQty) AS stock_bottles
        FROM MsItemBatchOpening o
        JOIN MsItemMaster m ON m.ItemID=o.ItemID
        JOIN MsBrandMaster b ON b.BrandID=m.BrandID
        WHERE o.ClosingQty > 0
        GROUP BY b.BrandName ORDER BY stock_bottles DESC
    """)

    col_l, col_r = st.columns(2)
    with col_l:
        if not df_br_pur.empty:
            st.plotly_chart(bar_chart(df_br_pur.head(15), x="brand", y="purchased",
                                      title="Top 15 Brands by Bottles Purchased",
                                      color_scale="Reds"),
                            use_container_width=True, key="ps_br_pur")
    with col_r:
        if not df_br_stk.empty:
            st.plotly_chart(bar_chart(df_br_stk.head(15), x="brand", y="stock_bottles",
                                      title="Top 15 Brands in Stock",
                                      color_scale="Oranges"),
                            use_container_width=True, key="ps_br_stk")

    st.divider()

    # ── Stock detail table ────────────────────────────────────────────────────
    st.subheader("Stock Summary by Brand")
    df_stk_detail = query("""
        SELECT b.BrandName AS brand,
               COUNT(DISTINCT o.ItemID)              AS skus,
               SUM(o.ClosingQty)                     AS bottles,
               SUM(o.ClosingQty * m.MrpBottRate)     AS mrp_value,
               SUM(o.ClosingQty * m.PurchaseRate)    AS cost_value
        FROM MsItemBatchOpening o
        JOIN MsItemMaster m ON m.ItemID=o.ItemID
        JOIN MsBrandMaster b ON b.BrandID=m.BrandID
        WHERE o.ClosingQty > 0
        GROUP BY b.BrandName ORDER BY mrp_value DESC
    """)
    if not df_stk_detail.empty:
        df_disp = df_stk_detail.copy()
        df_disp["mrp_value"]  = df_disp["mrp_value"].apply(fmt_inr)
        df_disp["cost_value"] = df_disp["cost_value"].apply(fmt_inr)
        df_disp["bottles"]    = df_disp["bottles"].apply(fmt_qty)
        df_disp.columns = ["Brand", "SKUs", "Bottles", "MRP Value", "Cost Value"]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
