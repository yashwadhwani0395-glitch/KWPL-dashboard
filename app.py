import streamlit as st
from config import COMPANY_NAME

st.set_page_config(
    page_title="KWPL Dashboard",
    page_icon="🍷",
    layout="wide",
)

st.title(f"🍷 {COMPANY_NAME} — Dashboard")

with st.sidebar:
    st.caption("Data is cached for 5 minutes.")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

from pages import overview, sales, purchases_stock, debtors_ageing, cashflow_expenses, balance_sheet
from pages import schema_explorer

tabs = st.tabs([
    "🏠 Overview",
    "📊 Sales",
    "📦 Purchases & Stock",
    "💰 Debtors Ageing",
    "💸 Cash Flow & Expenses",
    "📋 Balance Sheet",
    "🔍 DB Explorer",
])

with tabs[0]: overview.render()
with tabs[1]: sales.render()
with tabs[2]: purchases_stock.render()
with tabs[3]: debtors_ageing.render()
with tabs[4]: cashflow_expenses.render()
with tabs[5]: balance_sheet.render()
with tabs[6]: schema_explorer.render()
