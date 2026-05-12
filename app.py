import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import query, SALES_TYPES, PURCHASE_TYPES

st.set_page_config(
    page_title="KWPL Dashboard",
    page_icon="🍷",
    layout="wide",
)

st.title("🍷 Kranti Wines Pvt Ltd — Dashboard")

tabs = st.tabs([
    "🏠 Overview",
    "📊 Sales",
    "📦 Purchases & Stock",
    "💰 Debtors Ageing",
    "💸 Cash Flow & Expenses",
    "📋 Balance Sheet",
])
tab_overview, tab_sales, tab_purchases, tab_debtors, tab_cashflow, tab_bs = tabs


# ─── helpers ────────────────────────────────────────────────────────────────

def fmt_inr(val):
    val = float(val or 0)
    if val >= 1_00_00_000:
        return f"₹{val/1_00_00_000:.2f} Cr"
    elif val >= 1_00_000:
        return f"₹{val/1_00_000:.2f} L"
    return f"₹{val:,.0f}"


SALES_IN     = ",".join(str(x) for x in SALES_TYPES)
PURCHASE_IN  = ",".join(str(x) for x in PURCHASE_TYPES)
NOT_CANCELLED = "AND h.Cancelled <> 'Y'"
NOT_FREE      = "AND i.FreeItemYN <> 'Y'"

# Bank receipt / payment transaction type codes
BR_TYPES = "('BR')"
BP_TYPES = "('BP','CE')"


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
with tab_overview:
    st.header("Business Overview")

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
        WHERE h.TransTypeID IN ({SALES_IN})
          {NOT_CANCELLED}
          AND d.DrCrIndicator='D'
          AND d.RemainingAmt > 0
    """)

    stock_val = query("""
        SELECT SUM(o.ClosingQty * m.MrpBottRate) AS stock_value
        FROM MsItemBatchOpening o
        JOIN MsItemMaster m ON m.ItemID = o.ItemID
        WHERE o.ClosingQty > 0
    """)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Sales",        fmt_inr(kpi['total_sales'][0]))
    c2.metric("Total Purchases",    fmt_inr(kpi['total_purchases'][0]))
    c3.metric("Total Invoices",     f"{int(kpi['total_invoices'][0] or 0):,}")
    c4.metric("Outstanding",        fmt_inr(outstanding['total_outstanding'][0]))
    c5.metric("Stock Value (MRP)",  fmt_inr(stock_val['stock_value'][0]))

    st.divider()

    # ── Monthly Sales / Collections / Purchases ──────────────────────────────
    st.subheader("Monthly Trend — Sales, Collections & Purchases")
    df_trend = query(f"""
        SELECT
            YEAR(h.VoucherDate)  AS yr,
            MONTH(h.VoucherDate) AS mo,
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
        SELECT
            YEAR(h.VoucherDate)  AS yr,
            MONTH(h.VoucherDate) AS mo,
            SUM(d.Amount)        AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR') {NOT_CANCELLED}
          AND d.DrCrIndicator='C'
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """)
    if not df_trend.empty:
        df_trend['month'] = pd.to_datetime(
            df_trend['yr'].astype(str)+'-'+df_trend['mo'].astype(str)+'-01')
        if not df_coll.empty:
            df_coll['month'] = pd.to_datetime(
                df_coll['yr'].astype(str)+'-'+df_coll['mo'].astype(str)+'-01')
            df_trend = df_trend.merge(df_coll[['month','collections']], on='month', how='left').fillna(0)
        else:
            df_trend['collections'] = 0
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Sales',       x=df_trend['month'], y=df_trend['sales'],
                             marker_color='#7B2D8B'))
        fig.add_trace(go.Bar(name='Collections', x=df_trend['month'], y=df_trend['collections'],
                             marker_color='#28A745'))
        fig.add_trace(go.Bar(name='Purchases',   x=df_trend['month'], y=df_trend['purchases'],
                             marker_color='#E84855'))
        fig.update_layout(barmode='group', margin=dict(t=10,b=10), yaxis_title='₹',
                          legend=dict(orientation='h', y=1.1))
        st.plotly_chart(fig, use_container_width=True, key="chart_1")

    st.divider()

    # ── Company-wise / Brand-wise / Item-wise breakdown ───────────────────────
    view = st.radio("Breakdown by", ["Company", "Brand", "Item"], horizontal=True)

    if view == "Company":
        df_co = query(f"""
            SELECT t.TransTypeName AS label, SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY t.TransTypeName ORDER BY sales DESC
        """)
        col_l, col_r = st.columns(2)
        with col_l:
            if not df_co.empty:
                fig = px.pie(df_co, names='label', values='sales',
                             title='Sales by Company/Category',
                             color_discrete_sequence=px.colors.qualitative.Set2)
                fig.update_layout(margin=dict(t=40,b=10))
                st.plotly_chart(fig, use_container_width=True, key="chart_2")
        with col_r:
            if not df_co.empty:
                fig = px.bar(df_co, x='sales', y='label', orientation='h',
                             labels={'sales':'Sales (₹)','label':''},
                             color='sales', color_continuous_scale='Purples')
                fig.update_layout(yaxis={'categoryorder':'total ascending'},
                                  margin=dict(t=10,b=10), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True, key="chart_3")

    elif view == "Brand":
        df_br = query(f"""
            SELECT b.BrandName AS label, SUM(i.TotalAmount) AS sales,
                   SUM(i.TotalBottleQty) AS bottles
            FROM TrVocItem i
            JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
            JOIN MsBrandMaster b ON b.BrandID=i.BrandID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY b.BrandName ORDER BY sales DESC
        """)
        col_l, col_r = st.columns(2)
        with col_l:
            if not df_br.empty:
                fig = px.bar(df_br.head(15), x='label', y='sales',
                             labels={'label':'Brand','sales':'Sales (₹)'},
                             color='sales', color_continuous_scale='Teal',
                             title='Top Brands by Sales Value')
                fig.update_layout(margin=dict(t=40,b=10), coloraxis_showscale=False,
                                  xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="chart_2")
        with col_r:
            if not df_br.empty:
                fig = px.bar(df_br.head(15).sort_values('bottles', ascending=False),
                             x='label', y='bottles',
                             labels={'label':'Brand','bottles':'Bottles Sold'},
                             color='bottles', color_continuous_scale='Blues',
                             title='Top Brands by Volume')
                fig.update_layout(margin=dict(t=40,b=10), coloraxis_showscale=False,
                                  xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="chart_3")

    else:  # Item
        df_it = query(f"""
            SELECT TOP 20 m.ItemDescription AS label,
                   SUM(i.TotalAmount) AS sales,
                   SUM(i.TotalBottleQty) AS bottles
            FROM TrVocItem i
            JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
            JOIN MsItemMaster m ON m.ItemID=i.ItemID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY m.ItemDescription ORDER BY sales DESC
        """)
        col_l, col_r = st.columns(2)
        with col_l:
            if not df_it.empty:
                fig = px.bar(df_it, x='sales', y='label', orientation='h',
                             labels={'sales':'Sales (₹)','label':''},
                             color='sales', color_continuous_scale='Oranges',
                             title='Top 20 Items by Sales Value')
                fig.update_layout(yaxis={'categoryorder':'total ascending'},
                                  margin=dict(t=40,b=10), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True, key="chart_2")
        with col_r:
            if not df_it.empty:
                fig = px.bar(df_it.sort_values('bottles', ascending=False),
                             x='bottles', y='label', orientation='h',
                             labels={'bottles':'Bottles','label':''},
                             color='bottles', color_continuous_scale='Greens',
                             title='Top 20 Items by Volume')
                fig.update_layout(yaxis={'categoryorder':'total ascending'},
                                  margin=dict(t=40,b=10), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True, key="chart_3")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — SALES
# ════════════════════════════════════════════════════════════════════════════
with tab_sales:
    st.header("Sales")

    # KPIs
    s_kpi = query(f"""
        SELECT
            COUNT(DISTINCT h.VoucherNo) AS invoices,
            SUM(i.TotalAmount)          AS sales,
            SUM(i.TotalBottleQty)       AS bottles,
            SUM(i.CaseQty)              AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
    """)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Invoices",       f"{int(s_kpi['invoices'][0] or 0):,}")
    c2.metric("Total Sales",    fmt_inr(s_kpi['sales'][0]))
    c3.metric("Bottles Sold",   f"{int(s_kpi['bottles'][0] or 0):,}")
    c4.metric("Cases Sold",     f"{int(s_kpi['cases'][0] or 0):,}")

    st.divider()

    # Monthly trend + Category breakdown
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Sales Trend")
        df_monthly = query(f"""
            SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                   SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
            ORDER BY yr, mo
        """)
        if not df_monthly.empty:
            df_monthly['month'] = pd.to_datetime(
                df_monthly['yr'].astype(str)+'-'+df_monthly['mo'].astype(str)+'-01')
            fig = px.bar(df_monthly, x='month', y='sales',
                         labels={'month':'Month','sales':'Sales (₹)'},
                         color_discrete_sequence=['#7B2D8B'])
            fig.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True, key="chart_3")

    with col_r:
        st.subheader("Sales by Category")
        df_cat = query(f"""
            SELECT t.TransTypeName AS category, SUM(i.TotalAmount) AS sales
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY t.TransTypeName ORDER BY sales DESC
        """)
        if not df_cat.empty:
            fig = px.pie(df_cat, names='category', values='sales',
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True, key="chart_4")

    # Daily last 30 days
    st.subheader("Daily Sales — Last 30 Days")
    df_daily = query(f"""
        SELECT CAST(h.VoucherDate AS DATE) AS sale_date,
               SUM(i.TotalAmount) AS sales,
               COUNT(DISTINCT h.VoucherNo) AS invoices
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
          AND h.VoucherDate >= DATEADD(DAY,-30,GETDATE())
        GROUP BY CAST(h.VoucherDate AS DATE) ORDER BY sale_date
    """)
    if not df_daily.empty:
        fig = px.bar(df_daily, x='sale_date', y='sales',
                     labels={'sale_date':'Date','sales':'Sales (₹)'},
                     color_discrete_sequence=['#2E86AB'])
        fig.update_layout(margin=dict(t=10,b=10))
        st.plotly_chart(fig, use_container_width=True, key="chart_5")

    st.divider()

    # Top customers + Salesman side by side
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Top 15 Customers")
        df_cust = query(f"""
            SELECT TOP 15
                p.PartyName AS customer,
                SUM(i.TotalAmount) AS sales,
                COUNT(DISTINCT h.VoucherNo) AS invoices
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
            JOIN MsPartyMaster p ON p.PartyID=d.PartyID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
              AND d.DrCrIndicator='D'
            GROUP BY p.PartyName ORDER BY sales DESC
        """)
        if not df_cust.empty:
            fig = px.bar(df_cust, x='sales', y='customer', orientation='h',
                         labels={'sales':'Sales (₹)','customer':''},
                         color='sales', color_continuous_scale='Purples')
            fig.update_layout(yaxis={'categoryorder':'total ascending'},
                              margin=dict(t=10,b=10), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True, key="chart_6")

    with col_r:
        st.subheader("Salesman Performance")
        df_sm = query(f"""
            SELECT s.FullName AS salesman,
                   SUM(i.TotalAmount) AS sales,
                   COUNT(DISTINCT h.VoucherNo) AS invoices,
                   COUNT(DISTINCT d.PartyID) AS customers
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
            JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
            WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
              AND d.DrCrIndicator='D' AND s.ResignDate IS NULL
            GROUP BY s.FullName ORDER BY sales DESC
        """)
        if not df_sm.empty:
            fig = px.bar(df_sm, x='salesman', y='sales',
                         labels={'salesman':'','sales':'Sales (₹)'},
                         color='sales', color_continuous_scale='Oranges')
            fig.update_layout(margin=dict(t=10,b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True, key="chart_7")

    st.divider()

    # Top brands
    st.subheader("Top Brands")
    col_l, col_r = st.columns(2)
    df_brand = query(f"""
        SELECT TOP 15 b.BrandName AS brand,
               SUM(i.TotalAmount) AS sales,
               SUM(i.TotalBottleQty) AS bottles
        FROM TrVocItem i
        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
        JOIN MsBrandMaster b ON b.BrandID=i.BrandID
        WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED} {NOT_FREE}
        GROUP BY b.BrandName ORDER BY sales DESC
    """)
    with col_l:
        if not df_brand.empty:
            fig = px.bar(df_brand, x='brand', y='sales',
                         labels={'brand':'Brand','sales':'Sales (₹)'},
                         color='sales', color_continuous_scale='Teal')
            fig.update_layout(margin=dict(t=10,b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, key="chart_8")
    with col_r:
        if not df_brand.empty:
            fig = px.bar(df_brand.sort_values('bottles', ascending=False),
                         x='brand', y='bottles',
                         labels={'brand':'Brand','bottles':'Bottles'},
                         color='bottles', color_continuous_scale='Blues')
            fig.update_layout(margin=dict(t=10,b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, key="chart_9")


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — PURCHASES & STOCK
# ════════════════════════════════════════════════════════════════════════════
with tab_purchases:
    st.header("Purchases & Stock")

    p_kpi = query(f"""
        SELECT COUNT(DISTINCT h.VoucherNo) AS vouchers,
               SUM(i.TotalAmount)          AS purchases,
               SUM(i.TotalBottleQty)       AS bottles,
               SUM(i.CaseQty)              AS cases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
    """)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Purchase Vouchers", f"{int(p_kpi['vouchers'][0] or 0):,}")
    c2.metric("Total Purchases",   fmt_inr(p_kpi['purchases'][0]))
    c3.metric("Bottles Purchased", f"{int(p_kpi['bottles'][0] or 0):,}")
    c4.metric("Cases Purchased",   f"{int(p_kpi['cases'][0] or 0):,}")

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Purchase Trend")
        df_pur = query(f"""
            SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                   SUM(i.TotalAmount) AS purchases
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate) ORDER BY yr, mo
        """)
        if not df_pur.empty:
            df_pur['month'] = pd.to_datetime(
                df_pur['yr'].astype(str)+'-'+df_pur['mo'].astype(str)+'-01')
            fig = px.bar(df_pur, x='month', y='purchases',
                         labels={'month':'Month','purchases':'Purchases (₹)'},
                         color_discrete_sequence=['#E84855'])
            fig.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True, key="chart_10")

    with col_r:
        st.subheader("Purchases by Category")
        df_pcat = query(f"""
            SELECT t.TransTypeName AS category, SUM(i.TotalAmount) AS purchases
            FROM TrVocHead h
            JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED} {NOT_FREE}
            GROUP BY t.TransTypeName ORDER BY purchases DESC
        """)
        if not df_pcat.empty:
            fig = px.pie(df_pcat, names='category', values='purchases',
                         color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True, key="chart_11")

    st.divider()
    st.subheader("Current Stock Position")

    df_stock = query("""
        SELECT m.ItemDescription AS item,
               b.BrandName       AS brand,
               SUM(o.ClosingQty) AS bottles,
               MAX(m.MrpBottRate) AS mrp,
               SUM(o.ClosingQty) * MAX(m.MrpBottRate) AS stock_value
        FROM MsItemBatchOpening o
        JOIN MsItemMaster m ON m.ItemID=o.ItemID
        JOIN MsBrandMaster b ON b.BrandID=m.BrandID
        WHERE o.ClosingQty > 0
        GROUP BY m.ItemDescription, b.BrandName
        ORDER BY stock_value DESC
    """)

    if not df_stock.empty:
        total_sv = df_stock['stock_value'].sum()
        c1, c2 = st.columns(2)
        c1.metric("Total Stock Items", f"{len(df_stock):,}")
        c2.metric("Total Stock Value (MRP)", fmt_inr(total_sv))

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Stock Value by Brand")
            df_sbrand = df_stock.groupby('brand')['stock_value'].sum().reset_index()
            df_sbrand = df_sbrand.sort_values('stock_value', ascending=False).head(15)
            fig = px.bar(df_sbrand, x='brand', y='stock_value',
                         labels={'brand':'Brand','stock_value':'Value (₹)'},
                         color='stock_value', color_continuous_scale='Greens')
            fig.update_layout(margin=dict(t=10,b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True, key="chart_12")

        with col_r:
            st.subheader("Top 10 Items by Quantity")
            df_top = df_stock.nlargest(10, 'bottles')[['item','bottles','stock_value']]
            fig = px.bar(df_top, x='bottles', y='item', orientation='h',
                         labels={'bottles':'Bottles','item':''},
                         color='bottles', color_continuous_scale='Teal')
            fig.update_layout(yaxis={'categoryorder':'total ascending'},
                              margin=dict(t=10,b=10), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True, key="chart_13")

        st.subheader("Full Stock List")
        df_disp = df_stock.copy()
        df_disp['mrp'] = df_disp['mrp'].apply(lambda x: f"₹{float(x or 0):,.2f}")
        df_disp['stock_value'] = df_disp['stock_value'].apply(lambda x: fmt_inr(x))
        df_disp['bottles'] = df_disp['bottles'].apply(lambda x: f"{int(x or 0):,}")
        df_disp.columns = ['Item','Brand','Bottles','MRP/Bottle','Stock Value']
        st.dataframe(df_disp, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — DEBTORS AGEING
# ════════════════════════════════════════════════════════════════════════════
with tab_debtors:
    st.header("Debtors Ageing")

    df_age = query(f"""
        SELECT
            p.PartyName                                    AS customer,
            p.CreditDays                                   AS credit_days,
            p.CreditLimit                                  AS credit_limit,
            SUM(d.RemainingAmt)                            AS outstanding,
            SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) <= 30
                     THEN d.RemainingAmt ELSE 0 END)       AS d0_30,
            SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) BETWEEN 31 AND 60
                     THEN d.RemainingAmt ELSE 0 END)       AS d30_60,
            SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) BETWEEN 61 AND 90
                     THEN d.RemainingAmt ELSE 0 END)       AS d60_90,
            SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) > 90
                     THEN d.RemainingAmt ELSE 0 END)       AS d90_plus,
            MAX(h.VoucherDate)                             AS last_invoice
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE h.TransTypeID IN ({SALES_IN})
          {NOT_CANCELLED}
          AND d.DrCrIndicator='D'
          AND d.RemainingAmt > 0
        GROUP BY p.PartyName, p.CreditDays, p.CreditLimit
        HAVING SUM(d.RemainingAmt) > 0
        ORDER BY outstanding DESC
    """)

    if not df_age.empty:
        tot = df_age['outstanding'].sum()
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total Outstanding",  fmt_inr(tot))
        c2.metric("0–30 Days",          fmt_inr(df_age['d0_30'].sum()))
        c3.metric("30–60 Days",         fmt_inr(df_age['d30_60'].sum()))
        c4.metric("60–90 Days",         fmt_inr(df_age['d60_90'].sum()))
        c5.metric("90+ Days",           fmt_inr(df_age['d90_plus'].sum()))

        st.divider()

        # Ageing bucket chart
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Ageing Bucket Summary")
            buckets = pd.DataFrame({
                'Bucket': ['0–30 Days','30–60 Days','60–90 Days','90+ Days'],
                'Amount': [
                    float(df_age['d0_30'].sum()),
                    float(df_age['d30_60'].sum()),
                    float(df_age['d60_90'].sum()),
                    float(df_age['d90_plus'].sum()),
                ]
            })
            fig = px.pie(buckets, names='Bucket', values='Amount',
                         color_discrete_sequence=['#28A745','#FFC107','#FF851B','#E84855'])
            fig.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True, key="chart_14")

        with col_r:
            st.subheader("Top 15 Debtors")
            df_top = df_age.head(15)
            fig = px.bar(df_top, x='outstanding', y='customer', orientation='h',
                         labels={'outstanding':'Outstanding (₹)','customer':''},
                         color='outstanding', color_continuous_scale='Reds')
            fig.update_layout(yaxis={'categoryorder':'total ascending'},
                              margin=dict(t=10,b=10), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True, key="chart_15")

        st.subheader("Debtor Details")
        df_disp = df_age.copy()
        for col in ['outstanding','d0_30','d30_60','d60_90','d90_plus','credit_limit']:
            df_disp[col] = df_disp[col].apply(lambda x: fmt_inr(x))
        df_disp['last_invoice'] = pd.to_datetime(df_disp['last_invoice']).dt.strftime('%d-%b-%Y')
        df_disp.columns = ['Customer','Credit Days','Credit Limit','Outstanding',
                            '0–30','30–60','60–90','90+','Last Invoice']
        st.dataframe(df_disp, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — CASH FLOW & EXPENSES
# ════════════════════════════════════════════════════════════════════════════
with tab_cashflow:
    st.header("Cash Flow & Expenses")

    cf_kpi = query(f"""
        SELECT
            SUM(CASE WHEN t.ShortName IN ('BR','CR') THEN d.Amount ELSE 0 END) AS total_receipts,
            SUM(CASE WHEN t.ShortName IN ('BP','CE') THEN d.Amount ELSE 0 END) AS total_payments
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR','BP','CE')
          {NOT_CANCELLED}
    """)

    c1,c2,c3 = st.columns(3)
    receipts = float(cf_kpi['total_receipts'][0] or 0)
    payments = float(cf_kpi['total_payments'][0] or 0)
    c1.metric("Total Receipts",  fmt_inr(receipts))
    c2.metric("Total Payments",  fmt_inr(payments))
    c3.metric("Net Cash Flow",   fmt_inr(receipts - payments))

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Monthly Cash Flow")
        df_cf = query(f"""
            SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                   SUM(CASE WHEN t.ShortName IN ('BR','CR') THEN d.Amount ELSE 0 END) AS receipts,
                   SUM(CASE WHEN t.ShortName IN ('BP','CE') THEN d.Amount ELSE 0 END) AS payments
            FROM TrVocDetail d
            JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ('BR','CR','BP','CE') {NOT_CANCELLED}
            GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
            ORDER BY yr, mo
        """)
        if not df_cf.empty:
            df_cf['month'] = pd.to_datetime(
                df_cf['yr'].astype(str)+'-'+df_cf['mo'].astype(str)+'-01')
            fig = go.Figure()
            fig.add_trace(go.Bar(name='Receipts', x=df_cf['month'], y=df_cf['receipts'],
                                 marker_color='#28A745'))
            fig.add_trace(go.Bar(name='Payments', x=df_cf['month'], y=df_cf['payments'],
                                 marker_color='#E84855'))
            fig.update_layout(barmode='group', margin=dict(t=10,b=10), yaxis_title='₹')
            st.plotly_chart(fig, use_container_width=True, key="chart_16")

    with col_r:
        st.subheader("Expenses Breakdown")
        df_exp = query(f"""
            SELECT a.AccName AS expense_head, SUM(d.Amount) AS amount
            FROM TrVocDetail d
            JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsAccountHead a ON a.AccHeadID=d.AccHeadID
            WHERE h.TransTypeID IN (SELECT id_key FROM MsTransType WHERE ShortName IN ('BP','CE'))
              {NOT_CANCELLED}
              AND d.DrCrIndicator='D'
              AND a.MainHeadType='4'
            GROUP BY a.AccName ORDER BY amount DESC
        """)
        if not df_exp.empty:
            fig = px.pie(df_exp.head(10), names='expense_head', values='amount',
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True, key="chart_17")

    # Return cheques
    st.divider()
    st.subheader("Return Cheques")
    df_rc = query(f"""
        SELECT TOP 20
            p.PartyName AS customer,
            h.VoucherDate AS date,
            h.VoucherNo AS voucher,
            d.Amount AS amount,
            h.Narration AS narration
        FROM TrVocHead h
        JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.TransTypeName LIKE '%Return%Cheque%'
          {NOT_CANCELLED}
        ORDER BY h.VoucherDate DESC
    """)
    if not df_rc.empty:
        df_rc['date'] = pd.to_datetime(df_rc['date']).dt.strftime('%d-%b-%Y')
        df_rc['amount'] = df_rc['amount'].apply(lambda x: fmt_inr(x))
        df_rc.columns = ['Customer','Date','Voucher','Amount','Narration']
        st.dataframe(df_rc, use_container_width=True, hide_index=True)
    else:
        st.info("No return cheques found.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — BALANCE SHEET
# ════════════════════════════════════════════════════════════════════════════
with tab_bs:
    st.header("Balance Sheet")

    # MainHeadType mapping:
    # '1' = Application of Funds (Assets)
    # '2' = Sources of Funds (Liabilities)
    # '4' = Expenditure
    # '5' = Trading Debit (Purchases side)
    # '6' = Trading Credit (Sales side)

    df_bs = query("""
        SELECT
            a.MainHeadType,
            mc.CodeName AS main_head,
            a.AccName   AS account,
            SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS balance
        FROM TrVocDetail d
        JOIN MsAccountHead a ON a.AccHeadID=d.AccHeadID
        LEFT JOIN MsCodeMaster mc ON mc.CodeID=a.MainHeadID AND mc.CodeTypeID=1
        GROUP BY a.MainHeadType, mc.CodeName, a.AccName
    """)

    if not df_bs.empty:
        type_labels = {
            '1': '📂 Application of Funds (Assets)',
            '2': '📂 Sources of Funds (Liabilities)',
            '4': '📂 Expenditure',
            '5': '📂 Trading Debit',
            '6': '📂 Trading Credit',
        }

        col_l, col_r = st.columns(2)

        assets      = df_bs[df_bs['MainHeadType']=='1']['balance'].sum()
        liabilities = df_bs[df_bs['MainHeadType']=='2']['balance'].sum()
        expenditure = df_bs[df_bs['MainHeadType']=='4']['balance'].sum()
        trading_dr  = df_bs[df_bs['MainHeadType']=='5']['balance'].sum()
        trading_cr  = df_bs[df_bs['MainHeadType']=='6']['balance'].sum()

        with col_l:
            st.metric("Assets",      fmt_inr(assets))
            st.metric("Expenditure", fmt_inr(expenditure))
            st.metric("Trading Debit (Purchases)", fmt_inr(trading_dr))

        with col_r:
            st.metric("Liabilities", fmt_inr(abs(liabilities)))
            st.metric("Trading Credit (Sales)",    fmt_inr(abs(trading_cr)))

        st.divider()

        for type_code, label in type_labels.items():
            df_section = df_bs[df_bs['MainHeadType']==type_code].copy()
            if df_section.empty:
                continue
            df_section = df_section.sort_values('balance', ascending=False)
            total = df_section['balance'].sum()
            with st.expander(f"{label}  —  {fmt_inr(abs(total))}"):
                df_disp = df_section[['main_head','account','balance']].copy()
                df_disp['balance'] = df_disp['balance'].apply(lambda x: fmt_inr(x))
                df_disp.columns = ['Group','Account','Balance']
                st.dataframe(df_disp, use_container_width=True, hide_index=True)
