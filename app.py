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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Sales Overview",
    "👥 Top Customers",
    "🏷️ Brands & Products",
    "👔 Salesman Performance",
    "💰 Outstanding Payments",
    "📦 Purchase vs Sales",
])


# ─── helpers ────────────────────────────────────────────────────────────────

def fmt_inr(val):
    """Format a number as Indian currency (lakhs/crores)."""
    if val >= 1_00_00_000:
        return f"₹{val/1_00_00_000:.2f} Cr"
    elif val >= 1_00_000:
        return f"₹{val/1_00_000:.2f} L"
    else:
        return f"₹{val:,.0f}"


SALES_IN = ",".join(str(x) for x in SALES_TYPES)
PURCHASE_IN = ",".join(str(x) for x in PURCHASE_TYPES)
CANCELLED = "AND h.Cancelled <> 'Y'"


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — SALES OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Sales Overview")

    # KPI row
    kpi_sql = f"""
        SELECT
            COUNT(DISTINCT h.VoucherNo)          AS total_invoices,
            SUM(i.TotalAmount)                   AS total_sales,
            SUM(i.TotalBottleQty)                AS total_bottles,
            COUNT(DISTINCT h.SalesManID)         AS active_salesmen
        FROM TrVocHead h
        JOIN TrVocItem i
            ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN})
          {CANCELLED}
          AND i.FreeItemYN <> 'Y'
    """
    kpi = query(kpi_sql)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Invoices", f"{int(kpi['total_invoices'][0]):,}")
    c2.metric("Total Sales", fmt_inr(float(kpi['total_sales'][0] or 0)))
    c3.metric("Total Bottles Sold", f"{int(kpi['total_bottles'][0] or 0):,}")
    c4.metric("Active Salesmen", int(kpi['active_salesmen'][0]))

    st.divider()

    col_left, col_right = st.columns(2)

    # Monthly sales trend
    with col_left:
        st.subheader("Monthly Sales Trend")
        monthly_sql = f"""
            SELECT
                YEAR(h.VoucherDate)  AS yr,
                MONTH(h.VoucherDate) AS mo,
                SUM(i.TotalAmount)   AS sales
            FROM TrVocHead h
            JOIN TrVocItem i
                ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
            WHERE h.TransTypeID IN ({SALES_IN})
              {CANCELLED}
              AND i.FreeItemYN <> 'Y'
            GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
            ORDER BY yr, mo
        """
        df_monthly = query(monthly_sql)
        if not df_monthly.empty:
            df_monthly['month'] = pd.to_datetime(
                df_monthly['yr'].astype(str) + '-' + df_monthly['mo'].astype(str) + '-01'
            )
            fig = px.bar(df_monthly, x='month', y='sales',
                         labels={'month': 'Month', 'sales': 'Sales (₹)'},
                         color_discrete_sequence=['#7B2D8B'])
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    # Sales by transaction type
    with col_right:
        st.subheader("Sales by Category")
        cat_sql = f"""
            SELECT
                t.TransTypeDescription           AS category,
                SUM(i.TotalAmount)               AS sales
            FROM TrVocHead h
            JOIN TrVocItem i
                ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
            JOIN MsTransType t ON t.id_key = h.TransTypeID
            WHERE h.TransTypeID IN ({SALES_IN})
              {CANCELLED}
              AND i.FreeItemYN <> 'Y'
            GROUP BY t.TransTypeDescription
            ORDER BY sales DESC
        """
        df_cat = query(cat_sql)
        if not df_cat.empty:
            fig = px.pie(df_cat, names='category', values='sales',
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    # Daily sales last 30 days
    st.subheader("Daily Sales — Last 30 Days")
    daily_sql = f"""
        SELECT
            CAST(h.VoucherDate AS DATE)  AS sale_date,
            SUM(i.TotalAmount)           AS sales,
            COUNT(DISTINCT h.VoucherNo)  AS invoices
        FROM TrVocHead h
        JOIN TrVocItem i
            ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN})
          {CANCELLED}
          AND i.FreeItemYN <> 'Y'
          AND h.VoucherDate >= DATEADD(DAY, -30, GETDATE())
        GROUP BY CAST(h.VoucherDate AS DATE)
        ORDER BY sale_date
    """
    df_daily = query(daily_sql)
    if not df_daily.empty:
        fig = px.line(df_daily, x='sale_date', y='sales',
                      labels={'sale_date': 'Date', 'sales': 'Sales (₹)'},
                      markers=True,
                      color_discrete_sequence=['#2E86AB'])
        fig.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — TOP CUSTOMERS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Top Customers")

    col_l, col_r = st.columns([1, 3])
    with col_l:
        top_n = st.selectbox("Show top", [10, 20, 50], index=0)

    cust_sql = f"""
        SELECT TOP {top_n}
            p.PartyName                          AS customer,
            COUNT(DISTINCT h.VoucherNo)          AS invoices,
            SUM(i.TotalAmount)                   AS total_sales,
            SUM(i.TotalBottleQty)                AS total_bottles
        FROM TrVocHead h
        JOIN TrVocItem i
            ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
        JOIN TrVocDetail d
            ON d.TransTypeID = h.TransTypeID AND d.VoucherNo = h.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID = d.PartyID
        WHERE h.TransTypeID IN ({SALES_IN})
          {CANCELLED}
          AND i.FreeItemYN <> 'Y'
          AND d.DrCrIndicator = 'D'
        GROUP BY p.PartyName
        ORDER BY total_sales DESC
    """
    df_cust = query(cust_sql)

    if not df_cust.empty:
        fig = px.bar(df_cust, x='total_sales', y='customer',
                     orientation='h',
                     labels={'total_sales': 'Total Sales (₹)', 'customer': ''},
                     color='total_sales',
                     color_continuous_scale='Purples')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'},
                          margin=dict(t=10, b=10), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Customer Details")
        df_display = df_cust.copy()
        df_display['total_sales'] = df_display['total_sales'].apply(lambda x: fmt_inr(float(x or 0)))
        df_display['total_bottles'] = df_display['total_bottles'].apply(lambda x: f"{int(x or 0):,}")
        df_display.columns = ['Customer', 'Invoices', 'Total Sales', 'Total Bottles']
        st.dataframe(df_display, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — BRANDS & PRODUCTS
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Brands & Products Performance")

    col_l, col_r = st.columns(2)

    # Top brands by sales value
    with col_l:
        st.subheader("Top Brands by Sales Value")
        brand_sql = f"""
            SELECT TOP 15
                b.BrandName                      AS brand,
                SUM(i.TotalAmount)               AS sales,
                SUM(i.TotalBottleQty)            AS bottles
            FROM TrVocItem i
            JOIN TrVocHead h
                ON h.TransTypeID = i.TransTypeID AND h.VoucherNo = i.VoucherNo
            JOIN MsBrandMaster b ON b.BrandID = i.BrandID
            WHERE h.TransTypeID IN ({SALES_IN})
              {CANCELLED}
              AND i.FreeItemYN <> 'Y'
            GROUP BY b.BrandName
            ORDER BY sales DESC
        """
        df_brand = query(brand_sql)
        if not df_brand.empty:
            fig = px.bar(df_brand, x='brand', y='sales',
                         labels={'brand': 'Brand', 'sales': 'Sales (₹)'},
                         color='sales',
                         color_continuous_scale='Teal')
            fig.update_layout(margin=dict(t=10, b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    # Top brands by volume
    with col_r:
        st.subheader("Top Brands by Volume (Bottles)")
        if not df_brand.empty:
            fig = px.bar(df_brand.sort_values('bottles', ascending=False),
                         x='brand', y='bottles',
                         labels={'brand': 'Brand', 'bottles': 'Bottles Sold'},
                         color='bottles',
                         color_continuous_scale='Blues')
            fig.update_layout(margin=dict(t=10, b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    # Top items
    st.subheader("Top Products")
    item_sql = f"""
        SELECT TOP 20
            m.ItemDescription                    AS product,
            SUM(i.TotalAmount)                   AS sales,
            SUM(i.TotalBottleQty)                AS bottles,
            SUM(i.CaseQty)                       AS cases
        FROM TrVocItem i
        JOIN TrVocHead h
            ON h.TransTypeID = i.TransTypeID AND h.VoucherNo = i.VoucherNo
        JOIN MsItemMaster m ON m.ItemID = i.ItemID
        WHERE h.TransTypeID IN ({SALES_IN})
          {CANCELLED}
          AND i.FreeItemYN <> 'Y'
        GROUP BY m.ItemDescription
        ORDER BY sales DESC
    """
    df_items = query(item_sql)
    if not df_items.empty:
        df_items['sales'] = df_items['sales'].apply(lambda x: fmt_inr(float(x or 0)))
        df_items['bottles'] = df_items['bottles'].apply(lambda x: f"{int(x or 0):,}")
        df_items['cases'] = df_items['cases'].apply(lambda x: f"{int(x or 0):,}")
        df_items.columns = ['Product', 'Sales', 'Bottles', 'Cases']
        st.dataframe(df_items, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — SALESMAN PERFORMANCE
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Salesman Performance")

    sm_sql = f"""
        SELECT
            s.FullName                           AS salesman,
            COUNT(DISTINCT h.VoucherNo)          AS invoices,
            SUM(i.TotalAmount)                   AS total_sales,
            SUM(i.TotalBottleQty)                AS total_bottles,
            COUNT(DISTINCT d.PartyID)            AS unique_customers
        FROM TrVocHead h
        JOIN TrVocItem i
            ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
        JOIN TrVocDetail d
            ON d.TransTypeID = h.TransTypeID AND d.VoucherNo = h.VoucherNo
        JOIN MsSalesmanMaster s ON s.SalesManID = h.SalesManID
        WHERE h.TransTypeID IN ({SALES_IN})
          {CANCELLED}
          AND i.FreeItemYN <> 'Y'
          AND d.DrCrIndicator = 'D'
          AND s.ResignDate IS NULL
        GROUP BY s.FullName
        ORDER BY total_sales DESC
    """
    df_sm = query(sm_sql)

    if not df_sm.empty:
        col_l, col_r = st.columns(2)

        with col_l:
            st.subheader("Sales by Salesman")
            fig = px.bar(df_sm, x='salesman', y='total_sales',
                         labels={'salesman': '', 'total_sales': 'Sales (₹)'},
                         color='total_sales',
                         color_continuous_scale='Oranges')
            fig.update_layout(margin=dict(t=10, b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.subheader("Customers Covered")
            fig = px.bar(df_sm, x='salesman', y='unique_customers',
                         labels={'salesman': '', 'unique_customers': 'Unique Customers'},
                         color='unique_customers',
                         color_continuous_scale='Greens')
            fig.update_layout(margin=dict(t=10, b=10), coloraxis_showscale=False,
                              xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Salesman Summary")
        df_display = df_sm.copy()
        df_display['total_sales'] = df_display['total_sales'].apply(lambda x: fmt_inr(float(x or 0)))
        df_display['total_bottles'] = df_display['total_bottles'].apply(lambda x: f"{int(x or 0):,}")
        df_display.columns = ['Salesman', 'Invoices', 'Total Sales', 'Total Bottles', 'Customers']
        st.dataframe(df_display, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — OUTSTANDING PAYMENTS
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("Outstanding Payments")

    out_sql = f"""
        SELECT TOP 50
            p.PartyName                          AS customer,
            SUM(d.RemainingAmt)                  AS outstanding,
            MAX(h.VoucherDate)                   AS last_invoice_date,
            p.CreditDays                         AS credit_days,
            p.CreditLimit                        AS credit_limit
        FROM TrVocDetail d
        JOIN TrVocHead h
            ON h.TransTypeID = d.TransTypeID AND h.VoucherNo = d.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID = d.PartyID
        WHERE h.TransTypeID IN ({SALES_IN})
          {CANCELLED}
          AND d.DrCrIndicator = 'D'
          AND d.RemainingAmt > 0
          AND p.BannedPartyYN <> 'Y'
        GROUP BY p.PartyName, p.CreditDays, p.CreditLimit
        ORDER BY outstanding DESC
    """
    df_out = query(out_sql)

    if not df_out.empty:
        total_out = df_out['outstanding'].sum()
        st.metric("Total Outstanding", fmt_inr(float(total_out)))

        st.divider()

        fig = px.bar(df_out.head(20), x='outstanding', y='customer',
                     orientation='h',
                     labels={'outstanding': 'Outstanding (₹)', 'customer': ''},
                     color='outstanding',
                     color_continuous_scale='Reds')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'},
                          margin=dict(t=10, b=10), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Outstanding Details")
        df_display = df_out.copy()
        df_display['outstanding'] = df_display['outstanding'].apply(lambda x: fmt_inr(float(x or 0)))
        df_display['credit_limit'] = df_display['credit_limit'].apply(lambda x: fmt_inr(float(x or 0)))
        df_display['last_invoice_date'] = pd.to_datetime(df_display['last_invoice_date']).dt.strftime('%d-%b-%Y')
        df_display.columns = ['Customer', 'Outstanding', 'Last Invoice', 'Credit Days', 'Credit Limit']
        st.dataframe(df_display, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — PURCHASE VS SALES
# ════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("Purchase vs Sales")

    pnl_sql = f"""
        SELECT
            YEAR(h.VoucherDate)   AS yr,
            MONTH(h.VoucherDate)  AS mo,
            SUM(CASE WHEN h.TransTypeID IN ({SALES_IN})    THEN i.TotalAmount ELSE 0 END) AS sales,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN}) THEN i.TotalAmount ELSE 0 END) AS purchases
        FROM TrVocHead h
        JOIN TrVocItem i
            ON i.TransTypeID = h.TransTypeID AND i.VoucherNo = h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN},{PURCHASE_IN})
          {CANCELLED}
          AND i.FreeItemYN <> 'Y'
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """
    df_pnl = query(pnl_sql)

    if not df_pnl.empty:
        df_pnl['month'] = pd.to_datetime(
            df_pnl['yr'].astype(str) + '-' + df_pnl['mo'].astype(str) + '-01'
        )
        df_pnl['gross_margin'] = df_pnl['sales'] - df_pnl['purchases']

        # KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Sales", fmt_inr(float(df_pnl['sales'].sum())))
        c2.metric("Total Purchases", fmt_inr(float(df_pnl['purchases'].sum())))
        c3.metric("Gross Margin", fmt_inr(float(df_pnl['gross_margin'].sum())))

        st.divider()

        # Grouped bar chart
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Sales', x=df_pnl['month'], y=df_pnl['sales'],
                             marker_color='#2E86AB'))
        fig.add_trace(go.Bar(name='Purchases', x=df_pnl['month'], y=df_pnl['purchases'],
                             marker_color='#E84855'))
        fig.update_layout(barmode='group',
                          xaxis_title='Month', yaxis_title='Amount (₹)',
                          margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Margin trend
        st.subheader("Gross Margin Trend")
        fig2 = px.line(df_pnl, x='month', y='gross_margin',
                       labels={'month': 'Month', 'gross_margin': 'Gross Margin (₹)'},
                       markers=True,
                       color_discrete_sequence=['#28A745'])
        fig2.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig2, use_container_width=True)
