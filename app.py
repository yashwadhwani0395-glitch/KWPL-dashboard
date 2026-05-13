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
    FY_OPTIONS = {
        "FY 2025-26 (Apr 2025 – Mar 2026)": ("2025-04-01", "2026-03-31"),
        "FY 2026-27 (Apr 2026 – Present)":  ("2026-04-01", None),
        "All Years":                          (None,        None),
    }
    fy_label = st.radio("Financial Year", list(FY_OPTIONS.keys()), key="fy_sel")
    date_from, date_to = FY_OPTIONS[fy_label]

    date_filter = ""
    if date_from:
        date_filter += f" AND h.VoucherDate >= '{date_from}'"
    if date_to:
        date_filter += f" AND h.VoucherDate <= '{date_to}'"
    st.session_state["date_filter"] = date_filter

    st.divider()
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
