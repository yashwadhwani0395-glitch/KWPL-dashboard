import streamlit as st
import pandas as pd
from db import query
from config import NOT_CANCELLED, COLORS
from utils import fmt_inr, fmt_qty, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, grouped_bar, pie_chart


def render():
    st.header("Balance Sheet & Financial Summary")
    date_filter = st.session_state.get("date_filter", "")
    cutoff      = st.session_state.get("outstanding_cutoff")
    bal_col     = "CloseBal" if cutoff else "CloseBalTmp"

    st.info(
        "Figures read directly from ERP GL accounts (TrVocDetail by AccHeadID) "
        "and pre-computed period balances (MsAcHeadOpening). "
        "Should match ERP Trading Account and Balance Sheet reports exactly.",
        icon="ℹ️"
    )

    # ── Top-line summary ──────────────────────────────────────────────────────
    # All figures from GL posting table (TrVocDetail), mirroring how ERP computes
    # the Trading Account. Each line maps to the exact account in MsAccountHead.
    rev_q = query(f"""
        SELECT SUM(d.Amount) AS revenue
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        WHERE d.PartyID = '000004'
          AND d.DrCrIndicator = 'C'
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
    """)
    pur_q = query(f"""
        SELECT SUM(d.Amount) AS purchases
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        WHERE d.PartyID = '000005'
          AND d.DrCrIndicator = 'D'
          AND ISNULL(h.Cancelled,'N') <> 'Y'
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
    opening_stock_q = query("""
        SELECT SUM(ob.OpeningQty * m.ValuationBottleRate) AS opening_stock
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.OpeningQty > 0
    """)
    # Debtors and Creditors from GL control account pre-computed balances
    recv_q = query(f"""
        SELECT {bal_col} AS receivables
        FROM MsAcHeadOpening
        WHERE AccHeadID = '000002'
    """)
    cred_q = query(f"""
        SELECT ABS({bal_col}) AS payables
        FROM MsAcHeadOpening
        WHERE AccHeadID = '000003'
    """)
    stock_val = query("""
        SELECT
            SUM(ob.ClosingQty * m.ValuationBottleRate) AS val_amt,
            SUM(ob.ClosingQty)                          AS bottles
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.ClosingQty > 0
    """)

    rev_val      = float(rev_q["revenue"][0]               or 0) if not rev_q.empty else 0
    pur_val      = float(pur_q["purchases"][0]              or 0) if not pur_q.empty else 0
    exc_val      = float(exc_q["excise"][0]                 or 0) if not exc_q.empty else 0
    ssr_val      = float(ssr_q["sales_scheme"][0]           or 0) if not ssr_q.empty else 0
    recv_val     = float(recv_q["receivables"][0]           or 0) if not recv_q.empty else 0
    pay_val      = float(cred_q["payables"][0]              or 0) if not cred_q.empty else 0
    open_stk_val = float(opening_stock_q["opening_stock"][0] or 0) if not opening_stock_q.empty else 0
    clos_stk_val = float(stock_val["val_amt"][0]            or 0) if not stock_val.empty else 0

    cogs_val     = pur_val + exc_val
    total_income = rev_val + ssr_val
    gross_profit = total_income - (cogs_val + open_stk_val - clos_stk_val)
    gp_pct = (gross_profit / total_income * 100) if total_income else 0

    kpi_row([
        {"label": "Revenue (Sales)",       "value": rev_val,      "fmt": "inr"},
        {"label": "Sales Scheme Receipt",  "value": ssr_val,      "fmt": "inr"},
        {"label": "Purchases",             "value": pur_val,      "fmt": "inr"},
        {"label": "Excise Duty",           "value": exc_val,      "fmt": "inr"},
        {"label": "Gross Profit",          "value": gross_profit, "fmt": "inr",
         "delta": f"{gp_pct:.1f}% GP%"},
        {"label": "Closing Stock",         "value": clos_stk_val, "fmt": "inr"},
    ])

    st.divider()

    # ── Trading Account summary (mirrors ERP Trading A/C exactly) ───────────
    st.subheader("Trading Account")
    trd_rows = [
        ("Sales (GL 000004)",          rev_val,       "CR to SALES account"),
        ("Sales Scheme Receipt",       ssr_val,       "CR to SALES SCHEME account"),
        ("Less: Opening Stock",        open_stk_val,  "MsItemBatchOpening.OpeningQty × ValuationBottleRate"),
        ("Less: Purchases (GL 000005)", pur_val,      "DR to PURCHASES-TRADING account"),
        ("Less: Excise Duty",          exc_val,       "DR to EXCISE DUTY account(s)"),
        ("Add: Closing Stock",         clos_stk_val,  "MsItemBatchOpening.ClosingQty × ValuationBottleRate"),
        ("Gross Profit",               gross_profit,  f"{gp_pct:.1f}% on Sales+SSR"),
        ("Receivables (Debtors)",      recv_val,      "MsAcHeadOpening GL 000002"),
        ("Payables (Creditors)",       pay_val,       "MsAcHeadOpening GL 000003"),
        ("Net Working Capital",        recv_val + clos_stk_val - pay_val, "Receivables + Stock − Payables"),
    ]
    df_pl = pd.DataFrame(trd_rows, columns=["Item", "Amount", "Note"])
    df_pl["Amount"] = df_pl["Amount"].apply(fmt_inr)
    st.dataframe(df_pl, use_container_width=True, hide_index=True)

    st.divider()

    # ── Monthly P&L trend ─────────────────────────────────────────────────────
    st.subheader("Monthly Revenue vs Cost of Goods")
    df_trend = query(f"""
        SELECT
            YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr,
            MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
            SUM(CASE WHEN d.PartyID='000004' AND d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS revenue,
            SUM(CASE WHEN d.PartyID='000005' AND d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS cogs
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        WHERE d.PartyID IN ('000004','000005')
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
        ORDER BY yr, mo
    """)
    if not df_trend.empty:
        df_trend = month_col(df_trend)
        df_trend["gross_profit"] = df_trend["revenue"] - df_trend["cogs"]
        df_trend = scale_cr(df_trend, "revenue", "cogs", "gross_profit")
        fig = grouped_bar(df_trend, x="month", series=[
            {"col": "revenue",       "name": "Revenue",       "color": COLORS["sales"]},
            {"col": "cogs",          "name": "Cost of Goods", "color": COLORS["purchase"]},
            {"col": "gross_profit",  "name": "Gross Profit",  "color": COLORS["collection"]},
        ], yaxis_title="₹ Crores")
        st.plotly_chart(fig, use_container_width=True, key="bs_monthly_pl")

    st.divider()

    # ── Working capital ───────────────────────────────────────────────────────
    st.subheader("Working Capital Components")
    wc_data = {
        "Component": ["Receivables", "Stock (Valuation)", "Payables"],
        "Amount":    [recv_val, clos_stk_val, pay_val],
        "Type":      ["Asset", "Asset", "Liability"],
    }
    df_wc = pd.DataFrame(wc_data)

    col_l, col_r = st.columns(2)
    with col_l:
        assets = df_wc[df_wc["Type"]=="Asset"]
        st.plotly_chart(pie_chart(assets, "Component", "Amount", "Current Assets"),
                        use_container_width=True, key="bs_assets_pie")
    with col_r:
        net_wc = (df_wc[df_wc["Type"]=="Asset"]["Amount"].sum()
                  - df_wc[df_wc["Type"]=="Liability"]["Amount"].sum())
        df_wc_disp = df_wc.copy()
        df_wc_disp["Amount"] = df_wc_disp["Amount"].apply(fmt_inr)
        st.dataframe(df_wc_disp, use_container_width=True, hide_index=True)
        st.metric("Net Working Capital", fmt_inr(net_wc))

    st.divider()

    # ── Receivables vs Payables trend ─────────────────────────────────────────
    st.subheader("Receivables vs Payables by Party (Top 10)")
    df_rec = query(f"""
        SELECT TOP 10 p.PartyName AS party, op.{bal_col} AS receivable
        FROM MsPartyOpening op
        JOIN MsPartyMaster p ON p.PartyID = op.PartyID
        WHERE LEFT(op.PartyID, 1) = 'D' AND op.{bal_col} > 0
        ORDER BY op.{bal_col} DESC
    """)
    df_pay = query(f"""
        SELECT TOP 10 p.PartyName AS party, ABS(op.{bal_col}) AS payable
        FROM MsPartyOpening op
        JOIN MsPartyMaster p ON p.PartyID = op.PartyID
        WHERE LEFT(op.PartyID, 1) = 'C'
          AND op.{bal_col} < 0
        ORDER BY ABS(op.{bal_col}) DESC
    """)
    col_l, col_r = st.columns(2)
    with col_l:
        if not df_rec.empty:
            df_rec = scale_cr(df_rec, "receivable")
            st.plotly_chart(bar_chart(df_rec, x="party", y="receivable",
                                      orientation="h",
                                      color_scale="Purples",
                                      title="Top Receivables",
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="bs_recv")
    with col_r:
        if not df_pay.empty:
            df_pay = scale_cr(df_pay, "payable")
            st.plotly_chart(bar_chart(df_pay, x="party", y="payable",
                                      orientation="h",
                                      color_scale="Reds",
                                      title="Top Payables",
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="bs_pay")
