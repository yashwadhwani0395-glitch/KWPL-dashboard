import streamlit as st
from config import COMPANY_NAME

st.set_page_config(
    page_title="KWPL Dashboard",
    page_icon="🍷",
    layout="wide",
)

st.title(f"🍷 {COMPANY_NAME} — Dashboard")

# ── Global sidebar controls ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**Financial Year**")
    st.info("FY 2025-26\n\nApr 2025 – Mar 2026", icon="📅")

    # ERP reports use TPDate (Transport Permit date), not VoucherDate.
    # COALESCE falls back to VoucherDate for voucher types that have no TPDate (BR/CR/BP/CE).
    date_filter = (
        " AND COALESCE(h.TPDate, h.VoucherDate) >= '2025-04-01'"
        " AND COALESCE(h.TPDate, h.VoucherDate) < '2026-04-01'"
    )
    st.session_state["date_filter"]        = date_filter
    st.session_state["outstanding_cutoff"] = "2026-04-01"   # → uses CloseBal

    st.divider()
    st.caption("Data refreshes every 5 minutes.")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

from pages import overview, sales, purchases_stock, debtors_ageing, creditors_ageing, cashflow_expenses, balance_sheet
from pages import schema_explorer

tabs = st.tabs([
    "🏠 Overview",
    "📊 Sales",
    "📦 Purchases & Stock",
    "💰 Debtors Ageing",
    "🏦 Creditors Ageing",
    "💸 Cash Flow & Expenses",
    "📋 Balance Sheet",
    "🔍 DB Explorer",
])

with tabs[0]: overview.render()
with tabs[1]: sales.render()
with tabs[2]: purchases_stock.render()
with tabs[3]: debtors_ageing.render()
with tabs[4]: creditors_ageing.render()
with tabs[5]: cashflow_expenses.render()
with tabs[6]: balance_sheet.render()
with tabs[7]: schema_explorer.render()
