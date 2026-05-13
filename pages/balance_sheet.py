import streamlit as st
import pandas as pd
from db import query
from config import SALES_IN, PURCHASE_IN, NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, fmt_qty, month_col
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
    cutoff_sql  = f"AND h.VoucherDate < '{cutoff}'" if cutoff else ""

    st.info(
        "This tab provides a management-level financial summary derived from "
        "voucher data. For audited financials, refer to the official balance sheet.",
        icon="ℹ️"
    )

    # ── Top-line summary — 2 queries instead of 4 ────────────────────────────
    pl = query(f"""
        SELECT
            SUM(CASE WHEN t.ShortName='MS'                 AND ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalAmount ELSE 0 END) AS revenue,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN}) AND ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalAmount ELSE 0 END) AS cogs
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_IN}))
          {NOT_CANCELLED} {date_filter}
    """)
    ar_ap = query(f"""
        SELECT
            (SELECT SUM(net_balance) FROM (
                SELECT SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                WHERE ISNULL(h.Cancelled,'N') <> 'Y' AND d.PartyID LIKE 'D%'
                  {cutoff_sql}
                GROUP BY d.PartyID
                HAVING SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) > 0
            ) r) AS receivables,
            (SELECT SUM(net_balance) FROM (
                SELECT SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE -d.Amount END) AS net_balance
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                WHERE ISNULL(h.Cancelled,'N') <> 'Y' AND d.PartyID LIKE 'C%'
                  {cutoff_sql}
                GROUP BY d.PartyID
                HAVING SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE -d.Amount END) > 0
            ) p) AS payables
    """)
    stock_val = query(f"""
        SELECT SUM(sub.net_bottles * m.MrpBottRate) AS mrp
        FROM (
            SELECT vi.ItemID,
                   SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})
                            THEN vi.TotalBottleQty
                            ELSE -vi.TotalBottleQty END) AS net_bottles
            FROM TrVocItem vi
            JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
            WHERE h.TransTypeID IN ({PURCHASE_IN},{SALES_IN})
              {NOT_CANCELLED} AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
            GROUP BY vi.ItemID
        ) sub
        JOIN MsItemMaster m ON m.ItemID = sub.ItemID
        WHERE sub.net_bottles > 0
    """)

    rev_val  = float(pl["revenue"][0]       or 0)
    cogs_val = float(pl["cogs"][0]          or 0)
    recv_val = float(ar_ap["receivables"][0] or 0)
    pay_val  = float(ar_ap["payables"][0]   or 0)
    gross_profit = rev_val - cogs_val
    gp_pct = (gross_profit / rev_val * 100) if rev_val else 0

    kpi_row([
        {"label": "Revenue (Sales)",   "value": rev_val,               "fmt": "inr"},
        {"label": "Cost of Goods",     "value": cogs_val,              "fmt": "inr"},
        {"label": "Gross Profit",      "value": gross_profit,          "fmt": "inr",
         "delta": f"{gp_pct:.1f}% GP%"},
        {"label": "Receivables",       "value": recv_val,              "fmt": "inr"},
        {"label": "Payables",          "value": pay_val,               "fmt": "inr"},
        {"label": "Stock (MRP Value)", "value": stock_val["mrp"][0],   "fmt": "inr"},
    ])

    st.divider()

    # ── P&L summary table ─────────────────────────────────────────────────────
    st.subheader("P&L Summary")
    pl_rows = [
        ("Revenue",        rev_val,          ""),
        ("Cost of Goods",  cogs_val,         ""),
        ("Gross Profit",   gross_profit,     f"{gp_pct:.1f}%"),
        ("Receivables",    recv_val,         ""),
        ("Payables",       pay_val,          ""),
        ("Net Position",   recv_val - pay_val, ""),
    ]
    df_pl = pd.DataFrame(pl_rows, columns=["Item", "Amount", "Note"])
    df_pl["Amount"] = df_pl["Amount"].apply(fmt_inr)
    st.dataframe(df_pl, use_container_width=True, hide_index=True)

    st.divider()

    # ── Monthly P&L trend ─────────────────────────────────────────────────────
    st.subheader("Monthly Revenue vs Cost of Goods")
    df_trend = query(f"""
        SELECT
            YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN t.ShortName='MS'                      THEN i.TotalAmount ELSE 0 END) AS revenue,
            SUM(CASE WHEN h.TransTypeID IN ({PURCHASE_IN})      THEN i.TotalAmount ELSE 0 END) AS cogs
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE (t.ShortName='MS' OR h.TransTypeID IN ({PURCHASE_IN}))
          {NOT_CANCELLED} AND ISNULL(i.FreeItemYN,'N') <> 'Y'
          {date_filter}
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """)
    if not df_trend.empty:
        df_trend = month_col(df_trend)
        df_trend["gross_profit"] = df_trend["revenue"] - df_trend["cogs"]
        fig = grouped_bar(df_trend, x="month", series=[
            {"col": "revenue",       "name": "Revenue",       "color": COLORS["sales"]},
            {"col": "cogs",          "name": "Cost of Goods", "color": COLORS["purchase"]},
            {"col": "gross_profit",  "name": "Gross Profit",  "color": COLORS["collection"]},
        ])
        st.plotly_chart(fig, use_container_width=True, key="bs_monthly_pl")

    st.divider()

    # ── Working capital ───────────────────────────────────────────────────────
    st.subheader("Working Capital Components")
    wc_data = {
        "Component": ["Receivables", "Stock (MRP)", "Payables"],
        "Amount":    [recv_val, float(stock_val["mrp"][0] or 0), pay_val],
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
        SELECT TOP 10 p.PartyName AS party, SUM(d.RemainingAmt) AS receivable
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED}
          AND d.DrCrIndicator='D' AND d.RemainingAmt > 0
          AND d.PartyID IS NOT NULL
        GROUP BY p.PartyName ORDER BY receivable DESC
    """)
    df_pay = query(f"""
        SELECT TOP 10 p.PartyName AS party, SUM(d.RemainingAmt) AS payable
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE h.TransTypeID IN ({PURCHASE_IN}) {NOT_CANCELLED}
          AND d.DrCrIndicator='C' AND d.RemainingAmt > 0
        GROUP BY p.PartyName ORDER BY payable DESC
    """)
    col_l, col_r = st.columns(2)
    with col_l:
        if not df_rec.empty:
            st.plotly_chart(bar_chart(df_rec, x="party", y="receivable",
                                      orientation="h",
                                      color_scale="Purples",
                                      title="Top Receivables"),
                            use_container_width=True, key="bs_recv")
    with col_r:
        if not df_pay.empty:
            st.plotly_chart(bar_chart(df_pay, x="party", y="payable",
                                      orientation="h",
                                      color_scale="Reds",
                                      title="Top Payables"),
                            use_container_width=True, key="bs_pay")
