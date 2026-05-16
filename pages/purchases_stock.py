import streamlit as st
from db import query
from config import PURCHASE_IN, PURCHASE_ALL_IN, NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart, grouped_bar


def render():
    st.header("Purchases & Stock")
    date_filter = st.session_state.get("date_filter", "")

    # ── KPIs — 2 queries instead of 3 ───────────────────────────────────────
    pur = query(f"""
        SELECT
            COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR) + '|' + h.VoucherNo) AS invoices,
            SUM(i.TotalAmount)    AS purchases,
            SUM(i.TotalBottleQty) AS bottles,
            SUM(i.CaseQty)        AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
    """)
    pur_total = query(f"""
        SELECT SUM(i.TotalAmount) AS total_purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({PURCHASE_ALL_IN}) {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
    """)
    stock = query("""
        SELECT COUNT(DISTINCT ob.ItemID)                      AS sku_count,
               SUM(ob.ClosingQty)                          AS total_bottles,
               SUM(ob.ClosingQty * m.ValuationBottleRate)  AS stock_val
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.ClosingQty > 0
    """)
    kpi_row([
        {"label": "Purchase Invoices",          "value": pur["invoices"][0],              "fmt": "qty"},
        {"label": "Company Invoices (PU)",       "value": pur["purchases"][0],             "fmt": "inr"},
        {"label": "Total Purchases (+ Excise)",  "value": pur_total["total_purchases"][0], "fmt": "inr"},
        {"label": "Bottles Purchased",           "value": pur["bottles"][0],               "fmt": "qty"},
        {"label": "Stock (Valuation)",           "value": stock["stock_val"][0],           "fmt": "inr"},
        {"label": "Stock (Bottles)",             "value": stock["total_bottles"][0],       "fmt": "qty"},
    ])

    st.divider()

    # ── Monthly purchase trend ────────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Purchase Trend")
        df_m = query(f"""
            SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
                   SUM(i.TotalAmount) AS purchases
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({PURCHASE_ALL_IN}) {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate)) ORDER BY yr, mo
        """)
        if not df_m.empty:
            df_m = month_col(df_m)
            df_m = scale_cr(df_m, 'purchases')
            st.plotly_chart(bar_chart(df_m, x="month", y="purchases",
                                      color=COLORS["purchase"],
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="ps_monthly")

    with col_r:
        st.subheader("Purchases by Category")
        df_cat = query(f"""
            SELECT t.TransTypeName AS category, SUM(i.TotalAmount) AS purchases
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY t.TransTypeName ORDER BY purchases DESC
        """)
        if not df_cat.empty:
            st.plotly_chart(pie_chart(df_cat, "category", "purchases"),
                            use_container_width=True, key="ps_cat_pie")

    st.divider()

    # ── Top suppliers ─────────────────────────────────────────────────────────
    # Aggregate to invoice level first, then join supplier via DrCrIndicator='C'
    st.subheader("Top 15 Suppliers")
    df_sup = query(f"""
        SELECT TOP 15 p.PartyName AS supplier,
               SUM(v.inv_total) AS purchases,
               COUNT(*) AS invoices,
               SUM(v.bottles) AS bottles
        FROM (
            SELECT h.TransTypeID, h.VoucherNo,
                   SUM(i.TotalAmount) AS inv_total,
                   SUM(i.TotalBottleQty) AS bottles
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY h.TransTypeID, h.VoucherNo
        ) v
        JOIN TrVocDetail d ON d.TransTypeID=v.TransTypeID AND d.VoucherNo=v.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE d.DrCrIndicator='C' AND LEFT(d.PartyID,1)='C'
        GROUP BY p.PartyName ORDER BY purchases DESC
    """)
    if not df_sup.empty:
        st.plotly_chart(bar_chart(df_sup, x="supplier", y="purchases",
                                  orientation="h", color_scale="Reds"),
                        use_container_width=True, key="ps_suppliers")

    st.divider()

    # ── Brand purchase vs stock ───────────────────────────────────────────────
    st.subheader("Brand — Purchased vs In Stock")
    # Use i.BrandID directly (confirmed column on TrVocItem); IS NOT NULL excludes service lines.
    df_br_pur = query(f"""
        SELECT b.BrandName AS brand, SUM(i.TotalBottleQty) AS purchased
        FROM TrVocItem i
        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
        JOIN MsBrandMaster b ON b.BrandID=i.BrandID
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
          AND i.BrandID IS NOT NULL
          {date_filter}
        GROUP BY b.BrandName ORDER BY purchased DESC
    """)
    df_br_stk = query("""
        SELECT b.BrandName AS brand,
               SUM(ob.ClosingQty) AS stock_bottles
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        JOIN MsBrandMaster b ON b.BrandID = m.BrandID
        WHERE ob.ClosingQty > 0
        GROUP BY b.BrandName
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
    df_stk_detail = query("""
        SELECT b.BrandName AS brand,
               COUNT(DISTINCT ob.ItemID) AS skus,
               SUM(ob.ClosingQty) AS bottles,
               SUM(ob.ClosingQty * m.ValuationBottleRate) AS val_value
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        JOIN MsBrandMaster b ON b.BrandID = m.BrandID
        WHERE ob.ClosingQty > 0
        GROUP BY b.BrandName
        ORDER BY val_value DESC
    """)
    if not df_stk_detail.empty:
        df_stk_csv = df_stk_detail.copy()
        df_disp = df_stk_detail.copy()
        df_disp["val_value"] = df_disp["val_value"].apply(fmt_inr)
        df_disp["bottles"]   = df_disp["bottles"].apply(fmt_qty)
        df_disp.columns = ["Brand", "SKUs", "Bottles", "Valuation Value"]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Stock CSV",
            data=df_stk_csv.to_csv(index=False),
            file_name="stock_by_brand.csv",
            mime="text/csv",
            key="ps_dl_stock",
        )
