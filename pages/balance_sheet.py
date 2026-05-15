import streamlit as st
import pandas as pd
from db import query
from config import PURCHASE_IN, PURCHASE_ALL_IN, NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, grouped_bar, pie_chart


RECEIPT_CODES = ("'BR'", "'CR'")
PAYMENT_CODES = ("'BP'", "'CE'")
RECEIPT_IN    = ",".join(RECEIPT_CODES)
PAYMENT_IN    = ",".join(PAYMENT_CODES)


def render():
    st.header("Balance Sheet & Financial Summary")
    date_filter = st.session_state.get("date_filter", "")
    cutoff      = st.session_state.get("outstanding_cutoff")
    cutoff_sql  = f"AND COALESCE(h.TPDate, h.VoucherDate) < '{cutoff}'" if cutoff else ""
    bal_col     = "CloseBal" if cutoff else "CloseBalTmp"

    st.info(
        "This tab provides a management-level financial summary derived from "
        "voucher data. For audited financials, refer to the official balance sheet.",
        icon="ℹ️"
    )

    # ── Top-line summary ──────────────────────────────────────────────────────
    # Revenue = MS sales invoices (matches ERP Trading A/C "SALES" line)
    # COGS    = PU purchases + excise duty (BP/CE carrying stock items)
    # Opening stock = MsItemBatchOpening.OpeningQty × ValuationBottleRate
    #   (ERP Trading A/C debit side shows OPENING STOCK ₹39.88 Cr)
    pl = query(f"""
        SELECT
            SUM(CASE WHEN t.ShortName='MS'                      AND ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalAmount ELSE 0 END) AS revenue,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_ALL_IN}) AND ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalAmount ELSE 0 END) AS cogs
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_ALL_IN}))
          {NOT_CANCELLED} {date_filter}
    """)
    # Opening stock from MsItemBatchOpening.OpeningQty × ValuationBottleRate
    opening_stock_q = query("""
        SELECT SUM(ob.OpeningQty * m.ValuationBottleRate) AS opening_stock
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.OpeningQty > 0
    """)
    # Receivables from MsPartyOpening — matches ERP debtor closing balance exactly
    recv_q = query(f"""
        SELECT SUM({bal_col}) AS receivables
        FROM MsPartyOpening
        WHERE LEFT(PartyID, 1) = 'D'
    """)
    pay_q = query(f"""
        SELECT SUM(ABS({bal_col})) AS payables
        FROM MsPartyOpening
        WHERE LEFT(PartyID, 1) = 'C'
          AND {bal_col} < 0
    """)
    stock_val = query("""
        SELECT
            SUM(ob.ClosingQty * m.ValuationBottleRate) AS val_amt,
            SUM(ob.ClosingQty)                          AS bottles
        FROM MsItemBatchOpening ob
        JOIN MsItemMaster m ON m.ItemID = ob.ItemID
        WHERE ob.ClosingQty > 0
    """)

    rev_val      = float(pl["revenue"][0]                        or 0)
    cogs_val     = float(pl["cogs"][0]                           or 0)
    recv_val     = float(recv_q["receivables"][0]                or 0)
    pay_val      = float(pay_q["payables"][0]                    or 0)
    open_stk_val = float(opening_stock_q["opening_stock"][0]     or 0)
    clos_stk_val = float(stock_val["val_amt"][0]                 or 0)
    # Trading A/C: GP = Revenue − (COGS + Opening Stock − Closing Stock)
    gross_profit = rev_val - (cogs_val + open_stk_val - clos_stk_val)
    gp_pct = (gross_profit / rev_val * 100) if rev_val else 0

    kpi_row([
        {"label": "Revenue (Sales)",    "value": rev_val,        "fmt": "inr"},
        {"label": "Purchases + Excise", "value": cogs_val,       "fmt": "inr"},
        {"label": "Gross Profit",       "value": gross_profit,   "fmt": "inr",
         "delta": f"{gp_pct:.1f}% GP%"},
        {"label": "Receivables",        "value": recv_val,       "fmt": "inr"},
        {"label": "Payables",           "value": pay_val,        "fmt": "inr"},
        {"label": "Closing Stock",      "value": clos_stk_val,   "fmt": "inr"},
    ])

    st.divider()

    # ── Trading Account summary (mirrors ERP Trading A/C) ────────────────────
    st.subheader("Trading Account")
    trd_rows = [
        ("Sales (MS invoices)",   rev_val,       "Credit"),
        ("Opening Stock",         open_stk_val,  "Debit — MsItemBatchOpening"),
        ("Purchases + Excise",    cogs_val,      "Debit — PU + BP/CE types"),
        ("Closing Stock",         clos_stk_val,  "Credit — MsItemBatchOpening"),
        ("Gross Profit",          gross_profit,  f"{gp_pct:.1f}% on Sales"),
        ("Receivables (Debtors)", recv_val,      "MsPartyOpening D%"),
        ("Payables (Creditors)",  pay_val,       "MsPartyOpening C%"),
        ("Net Working Capital",   recv_val + clos_stk_val - pay_val, ""),
    ]
    df_pl = pd.DataFrame(trd_rows, columns=["Item", "Amount", "Note"])
    df_pl["Amount"] = df_pl["Amount"].apply(fmt_inr)
    st.dataframe(df_pl, use_container_width=True, hide_index=True)

    st.divider()

    # ── Monthly P&L trend ─────────────────────────────────────────────────────
    st.subheader("Monthly Revenue vs Cost of Goods")
    df_trend = query(f"""
        SELECT
            YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
            SUM(CASE WHEN t.ShortName='MS'                       THEN i.TotalAmount ELSE 0 END) AS revenue,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_ALL_IN})  THEN i.TotalAmount ELSE 0 END) AS cogs
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_ALL_IN}))
          {NOT_CANCELLED} AND ISNULL(i.FreeItemYN,'N') <> 'Y'
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
