import streamlit as st
from db import query
from config import PURCHASE_IN, SALES_IN, NOT_CANCELLED, NOT_FREE, COLORS
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
    stock = query(f"""
        SELECT
            COUNT(DISTINCT sub.ItemID)               AS sku_count,
            SUM(sub.net_bottles)                     AS total_bottles,
            SUM(sub.net_bottles * m.MrpBottRate)     AS stock_mrp
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
        {"label": "Purchase Invoices", "value": kpi["invoices"][0],        "fmt": "qty"},
        {"label": "Total Purchases",   "value": kpi["purchases"][0],       "fmt": "inr"},
        {"label": "Bottles Purchased", "value": kpi["bottles"][0],         "fmt": "qty"},
        {"label": "Stock (MRP Value)", "value": stock["stock_mrp"][0],     "fmt": "inr"},
        {"label": "Stock (Bottles)",   "value": stock["total_bottles"][0], "fmt": "qty"},
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
    df_br_stk = query(f"""
        SELECT b.BrandName AS brand,
               SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                        THEN vi.TotalBottleQty
                        ELSE -vi.TotalBottleQty END) AS stock_bottles
        FROM TrVocItem vi
        JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
        JOIN MsBrandMaster b ON b.BrandID=vi.BrandID
        WHERE h.TransTypeID IN ({PURCHASE_IN},{SALES_IN})
          {NOT_CANCELLED} AND vi.FreeItemYN <> 'Y'
        GROUP BY b.BrandName
        HAVING SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                        THEN vi.TotalBottleQty
                        ELSE -vi.TotalBottleQty END) > 0
        ORDER BY stock_bottles DESC
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
    df_stk_detail = query(f"""
        SELECT b.BrandName AS brand,
               COUNT(DISTINCT vi.ItemID) AS skus,
               SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                        THEN vi.TotalBottleQty
                        ELSE -vi.TotalBottleQty END) AS bottles,
               SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                        THEN vi.TotalBottleQty * m.MrpBottRate
                        ELSE -vi.TotalBottleQty * m.MrpBottRate END) AS mrp_value
        FROM TrVocItem vi
        JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
        JOIN MsItemMaster m ON m.ItemID=vi.ItemID
        JOIN MsBrandMaster b ON b.BrandID=vi.BrandID
        WHERE h.TransTypeID IN ({PURCHASE_IN},{SALES_IN})
          {NOT_CANCELLED} AND vi.FreeItemYN <> 'Y'
        GROUP BY b.BrandName
        HAVING SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                        THEN vi.TotalBottleQty
                        ELSE -vi.TotalBottleQty END) > 0
        ORDER BY mrp_value DESC
    """)
    if not df_stk_detail.empty:
        df_disp = df_stk_detail.copy()
        df_disp["mrp_value"] = df_disp["mrp_value"].apply(fmt_inr)
        df_disp["bottles"]   = df_disp["bottles"].apply(fmt_qty)
        df_disp.columns = ["Brand", "SKUs", "Bottles", "MRP Value"]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
