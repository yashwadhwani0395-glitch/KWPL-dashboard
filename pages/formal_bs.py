import streamlit as st
import pandas as pd
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS, PURCHASE_IN
from utils import fmt_inr


def _row(label, dr, cr):
    return {"": label, "Dr (₹)": fmt_inr(dr) if dr else "", "Cr (₹)": fmt_inr(cr) if cr else ""}


def render():
    st.header("Formal Balance Sheet — FY 2025-26")
    date_filter = st.session_state.get("date_filter", "")
    cutoff      = st.session_state.get("outstanding_cutoff")
    bal_col     = "CloseBal" if cutoff else "CloseBalTmp"

    # ── Fetch all figures ─────────────────────────────────────────────────────
    rev_q = query(f"""
        SELECT SUM(i.TotalAmount) AS revenue
        FROM TrVocHead h
        JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS'
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND ISNULL(i.FreeItemYN,'N') <> 'Y'
          AND i.BrandID IS NOT NULL
          {date_filter}
    """)
    pur_q = query(f"""
        SELECT SUM(i.TotalAmount) AS purchases
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({PURCHASE_IN})
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND ISNULL(i.FreeItemYN,'N') <> 'Y'
          AND i.BrandID IS NOT NULL
          {date_filter}
    """)
    exc_q = query(f"""
        SELECT SUM(d.Amount) AS excise
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsAccountHead a ON a.AccHeadID = d.PartyID
        WHERE a.AccHeadName LIKE '%EXCISE DUTY%'
          AND d.DrCrIndicator = 'D'
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
    """)
    ssr_q = query(f"""
        SELECT SUM(d.Amount) AS sales_scheme
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsAccountHead a ON a.AccHeadID = d.PartyID
        WHERE a.AccHeadName LIKE '%SALES SCHEME%'
          AND d.DrCrIndicator = 'C'
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
    """)
    open_stk_q = query("""
        SELECT SUM(ob.OpeningQty * m.ValuationBottleRate) AS opening_stock
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.OpeningQty > 0
    """)
    clos_stk_q = query("""
        SELECT SUM(ob.ClosingQty * m.ValuationBottleRate) AS closing_stock
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.ClosingQty > 0
    """)
    recv_q = query(f"SELECT {bal_col} AS receivables FROM MsAcHeadOpening WHERE AccHeadID = '000002'")
    cred_q = query(f"SELECT ABS({bal_col}) AS payables FROM MsAcHeadOpening WHERE AccHeadID = '000003'")

    # All GL account balances for full balance sheet
    gl_q = query(f"""
        SELECT
            a.AccHeadID,
            a.AccHeadName,
            a.MainHeadType,
            o.{bal_col} AS balance
        FROM MsAcHeadOpening o
        JOIN MsAccountHead a ON a.AccHeadID = o.AccHeadID
        WHERE o.{bal_col} <> 0
        ORDER BY a.MainHeadType, a.AccHeadName
    """)

    rev_val      = float(rev_q["revenue"][0]          or 0) if not rev_q.empty else 0
    pur_val      = float(pur_q["purchases"][0]         or 0) if not pur_q.empty else 0
    exc_val      = float(exc_q["excise"][0]            or 0) if not exc_q.empty else 0
    ssr_val      = float(ssr_q["sales_scheme"][0]      or 0) if not ssr_q.empty else 0
    open_stk_val = float(open_stk_q["opening_stock"][0] or 0) if not open_stk_q.empty else 0
    clos_stk_val = float(clos_stk_q["closing_stock"][0] or 0) if not clos_stk_q.empty else 0
    recv_val     = float(recv_q["receivables"][0]      or 0) if not recv_q.empty else 0
    pay_val      = float(cred_q["payables"][0]         or 0) if not cred_q.empty else 0

    gross_profit = (rev_val + ssr_val) - (open_stk_val + pur_val + exc_val - clos_stk_val)
    gp_pct       = (gross_profit / (rev_val + ssr_val) * 100) if (rev_val + ssr_val) else 0

    # ── Trading Account ───────────────────────────────────────────────────────
    st.subheader("Trading Account (Dr / Cr)")
    st.caption("Mirrors ERP Trading Account — product lines only (BrandID IS NOT NULL)")

    dr_items = [
        ("Opening Stock",          open_stk_val),
        ("Purchases (product)",    pur_val),
        ("Excise Duty",            exc_val),
        ("Gross Profit c/d",       gross_profit),
    ]
    cr_items = [
        ("Sales",                  rev_val),
        ("Sales Scheme Receipts",  ssr_val),
        ("Closing Stock",          clos_stk_val),
    ]

    dr_total = sum(v for _, v in dr_items)
    cr_total = sum(v for _, v in cr_items)

    # Pad shorter side with blank rows
    while len(dr_items) < len(cr_items):
        dr_items.append(("", 0))
    while len(cr_items) < len(dr_items):
        cr_items.append(("", 0))

    trd_rows = []
    for (dl, dv), (cl, cv) in zip(dr_items, cr_items):
        trd_rows.append({
            "Dr — Particulars": dl,
            "Dr Amount (₹)":    fmt_inr(dv) if dv else "",
            "Cr — Particulars": cl,
            "Cr Amount (₹)":    fmt_inr(cv) if cv else "",
        })
    trd_rows.append({
        "Dr — Particulars": "TOTAL",
        "Dr Amount (₹)":    fmt_inr(dr_total),
        "Cr — Particulars": "TOTAL",
        "Cr Amount (₹)":    fmt_inr(cr_total),
    })

    df_trd = pd.DataFrame(trd_rows)
    st.dataframe(df_trd, use_container_width=True, hide_index=True)
    st.metric("Gross Profit", fmt_inr(gross_profit), delta=f"{gp_pct:.1f}% GP%")

    st.divider()

    # ── Balance Sheet from GL balances ────────────────────────────────────────
    st.subheader("Balance Sheet — All GL Account Balances")
    st.caption(
        "From MsAcHeadOpening. MainHeadType: 1/7=Debtors, 2/8=Creditors, "
        "3=Other Income, 4=Expenses, 5=Purchases, 6=Sales, 9=Stock. "
        "Positive CloseBal = Debit balance (asset/expense). "
        "Negative CloseBal = Credit balance (liability/income)."
    )

    if not gl_q.empty:
        TYPE_LABELS = {
            1: "Debtors",
            2: "Creditors",
            3: "Other Income",
            4: "Expenses / Overheads",
            5: "Purchases / COGS",
            6: "Sales Revenue",
            7: "Debtors (Misc)",
            8: "Creditors (Misc)",
            9: "Stock / Inventory",
            10: "Miscellaneous",
            11: "Other",
        }
        gl_q["Type"] = gl_q["MainHeadType"].map(lambda x: TYPE_LABELS.get(int(x), f"Type {x}"))
        gl_q["balance_fmt"] = gl_q["balance"].apply(lambda x: fmt_inr(float(x)))
        gl_q["Dr/Cr"] = gl_q["balance"].apply(lambda x: "Dr" if float(x) >= 0 else "Cr")

        # Show grouped by type
        for type_name, grp in gl_q.groupby("Type", sort=False):
            with st.expander(f"**{type_name}** — {len(grp)} accounts", expanded=(type_name in ("Debtors", "Creditors", "Stock / Inventory"))):
                disp = grp[["AccHeadID", "AccHeadName", "balance_fmt", "Dr/Cr"]].copy()
                disp.columns = ["GL Code", "Account Name", "Balance (₹)", "Nature"]
                st.dataframe(disp, use_container_width=True, hide_index=True)

        # Summary totals
        st.divider()
        st.subheader("Balance Sheet Summary")
        asset_types   = gl_q[gl_q["balance"].astype(float) >= 0]
        liab_types    = gl_q[gl_q["balance"].astype(float) < 0]
        total_assets  = asset_types["balance"].astype(float).sum()
        total_liabs   = abs(liab_types["balance"].astype(float).sum())

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Debit Balances (Assets/Expenses)", fmt_inr(total_assets))
        c2.metric("Total Credit Balances (Liabilities/Income)", fmt_inr(total_liabs))
        c3.metric("Balance Sheet Difference", fmt_inr(total_assets - total_liabs),
                  delta="Should be 0 if books balance")

        # Key accounts highlighted
        st.divider()
        st.subheader("Key Balance Sheet Items")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Assets**")
            key_assets = pd.DataFrame([
                {"Account": "Sundry Debtors (GL 000002)",     "Amount": fmt_inr(recv_val)},
                {"Account": "Closing Stock (Valuation)",       "Amount": fmt_inr(clos_stk_val)},
            ])
            st.dataframe(key_assets, use_container_width=True, hide_index=True)
        with col_b:
            st.markdown("**Liabilities**")
            key_liabs = pd.DataFrame([
                {"Account": "Sundry Creditors (GL 000003)",   "Amount": fmt_inr(pay_val)},
            ])
            st.dataframe(key_liabs, use_container_width=True, hide_index=True)

        # Full GL dump as CSV
        st.divider()
        csv_data = gl_q[["AccHeadID", "AccHeadName", "Type", "balance", "Dr/Cr"]].copy()
        csv_data.columns = ["GL Code", "Account Name", "Type", "Balance", "Nature"]
        st.download_button(
            "⬇️ Download Full GL Balances CSV",
            data=csv_data.to_csv(index=False),
            file_name="gl_balances_fy2526.csv",
            mime="text/csv",
            key="fbs_dl_gl",
        )
    else:
        st.warning("No GL balance data found in MsAcHeadOpening.")
