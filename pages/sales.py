import streamlit as st
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart


def render():
    st.header("Sales")
    date_filter = st.session_state.get("date_filter", "")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    sales_amt = query(f"""
        SELECT SUM(i.TotalAmount) AS sales,
               SUM(i.TotalBottleQty) AS bottles,
               SUM(i.CaseQty) AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          {date_filter}
    """)
    inv_count = query(f"""
        SELECT COUNT(*) AS invoices
        FROM TrVocHead h
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED}
          {date_filter}
    """)
    kpi_row([
        {"label": "Invoices",     "value": inv_count["invoices"][0], "fmt": "qty"},
        {"label": "Total Sales",  "value": sales_amt["sales"][0],    "fmt": "inr"},
        {"label": "Bottles Sold", "value": sales_amt["bottles"][0],  "fmt": "qty"},
        {"label": "Cases Sold",   "value": sales_amt["cases"][0],    "fmt": "qty"},
    ])

    st.divider()

    # ── Monthly trend + Category pie ──────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Sales Trend")
        df_m = query(f"""
            SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate) ORDER BY yr, mo
        """)
        if not df_m.empty:
            df_m = month_col(df_m)
            st.plotly_chart(bar_chart(df_m, x="month", y="sales",
                                      color=COLORS["sales"]),
                            use_container_width=True, key="sl_monthly")

    with col_r:
        st.subheader("Sales by Category")
        df_cat = query(f"""
            SELECT t.TransTypeName AS category, SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
              {date_filter}
            GROUP BY t.TransTypeName ORDER BY sales DESC
        """)
        if not df_cat.empty:
            st.plotly_chart(pie_chart(df_cat, "category", "sales"),
                            use_container_width=True, key="sl_cat_pie")

    # ── Daily last 30 days ────────────────────────────────────────────────────
    st.subheader("Daily Sales — Last 30 Days")
    df_d = query(f"""
        SELECT CAST(h.VoucherDate AS DATE) AS sale_date,
               SUM(i.TotalAmount) AS sales
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          AND h.VoucherDate >= DATEADD(DAY,-30,GETDATE())
        GROUP BY CAST(h.VoucherDate AS DATE) ORDER BY sale_date
    """)
    if not df_d.empty:
        st.plotly_chart(bar_chart(df_d, x="sale_date", y="sales",
                                  color=COLORS["info"]),
                        use_container_width=True, key="sl_daily")

    st.divider()

    # ── Top customers + Salesman ──────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Top 15 Customers")
        df_c = query(f"""
            SELECT TOP 15 p.PartyName AS customer,
                   SUM(v.inv_total) AS sales,
                   COUNT(*) AS invoices
            FROM (
                SELECT h.TransTypeID, h.VoucherNo, SUM(i.TotalAmount) AS inv_total
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
                  {date_filter}
                GROUP BY h.TransTypeID, h.VoucherNo
            ) v
            JOIN TrVocDetail d ON d.TransTypeID=v.TransTypeID AND d.VoucherNo=v.VoucherNo
            JOIN MsPartyMaster p ON p.PartyID=d.PartyID
            WHERE d.DrCrIndicator='D' AND d.PartyID IS NOT NULL
            GROUP BY p.PartyName ORDER BY sales DESC
        """)
        if not df_c.empty:
            st.plotly_chart(bar_chart(df_c, x="customer", y="sales",
                                      orientation="h", color_scale="Purples"),
                            use_container_width=True, key="sl_cust")

    with col_r:
        st.subheader("Salesman Performance")
        df_sm = query(f"""
            SELECT s.FullName AS salesman,
                   SUM(v.inv_total) AS sales,
                   COUNT(*) AS invoices,
                   COUNT(DISTINCT d.PartyID) AS customers
            FROM (
                SELECT h.TransTypeID, h.VoucherNo, h.SalesManID,
                       SUM(i.TotalAmount) AS inv_total
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
                  {date_filter}
                GROUP BY h.TransTypeID, h.VoucherNo, h.SalesManID
            ) v
            JOIN MsSalesmanMaster s ON s.SalesManID=v.SalesManID
            JOIN TrVocDetail d ON d.TransTypeID=v.TransTypeID AND d.VoucherNo=v.VoucherNo
            WHERE d.DrCrIndicator='D' AND d.PartyID IS NOT NULL
              AND s.ResignDate IS NULL
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
        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsBrandMaster b ON b.BrandID=i.BrandID
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

    # ── Salesman detail table ─────────────────────────────────────────────────
    if not df_sm.empty:
        st.divider()
        st.subheader("Salesman Detail")
        df_disp = df_sm.copy()
        df_disp["sales"] = df_disp["sales"].apply(lambda x: fmt_inr(x))
        df_disp.columns = ["Salesman", "Total Sales", "Invoices", "Customers"]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
