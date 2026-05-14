import streamlit as st
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart


def render():
    st.header("Sales")
    date_filter = st.session_state.get("date_filter", "")

    # ── KPIs — single query ───────────────────────────────────────────────────
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
            SELECT company, SUM(sales) AS sales FROM (
                SELECT COALESCE(p.PartyName,'Others') AS company, i.TotalAmount AS sales
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsItemMaster m ON m.ItemID=i.ItemID
                LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
                WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE} {date_filter}
                UNION ALL
                SELECT COALESCE(p.PartyName,'Others') AS company, i.TotalAmount AS sales
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsItemMaster m ON m.ItemID=i.ItemID
                LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
                WHERE h.TransTypeID=53
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y' {date_filter}
            ) t GROUP BY company ORDER BY sales DESC
        """)
        if not df_prin.empty:
            comp_colors = [_COMP_COLORS[i % len(_COMP_COLORS)] for i in range(len(df_prin))]
            st.plotly_chart(pie_chart(df_prin, "company", "sales",
                                     colors=comp_colors),
                            use_container_width=True, key="sl_prin_pie")

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

    # ── Salesman detail table ─────────────────────────────────────────────────
    if not df_sm.empty:
        st.divider()
        st.subheader("Salesman Detail")
        df_disp = df_sm[["salesman", "sales", "invoices"]].copy()
        df_disp["sales"] = df_disp["sales"].apply(fmt_inr)
        df_disp.columns = ["Salesman", "Total Sales", "Invoices"]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
