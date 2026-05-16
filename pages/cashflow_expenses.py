import streamlit as st
import pandas as pd
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, month_col, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, grouped_bar, pie_chart, area_chart


PAYMENT_IN = "'BP','CE'"


def render():
    st.header("Cash Flow & Expenses")
    date_filter = st.session_state.get("date_filter", "")

    st.info(
        "Collections = Bank Receipts (BR) + Cash Receipts (CR) — customer accounts are debited "
        "when payment is received in this ERP. "
        "Payments = Bank Payment (BP) + Cash Payment (CE) vouchers, debit side.",
        icon="ℹ️"
    )

    # ── KPIs ─────────────────────────────────────────────────────────────────
    # Collections = BR+CR transaction types only — cash/bank receipts from D% customers
    kpi_coll = query(f"""
        SELECT
            SUM(d.Amount) AS total_collections,
            COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS receipt_vouchers
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR')
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D'
          AND LEFT(d.PartyID,1)='D'
          {date_filter}
    """)
    kpi_pay = query(f"""
        SELECT
            SUM(d.Amount) AS total_payments,
            COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS payment_count
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ({PAYMENT_IN})
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D'
          {date_filter}
    """)

    kpi_row([
        {"label": "Total Collections",  "value": kpi_coll["total_collections"][0], "fmt": "inr"},
        {"label": "Receipt Vouchers",   "value": kpi_coll["receipt_vouchers"][0],  "fmt": "qty"},
        {"label": "Total Payments Out", "value": kpi_pay["total_payments"][0],     "fmt": "inr"},
        {"label": "Payment Vouchers",   "value": kpi_pay["payment_count"][0],      "fmt": "qty"},
    ])

    st.divider()

    # ── Monthly collections vs payments ──────────────────────────────────────
    st.subheader("Monthly Collections vs Payments")
    df_coll_m = query(f"""
        SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
               SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR')
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
          {date_filter}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
        ORDER BY yr, mo
    """)
    df_pay_m = query(f"""
        SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
               SUM(d.Amount) AS payments
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ({PAYMENT_IN})
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D'
          {date_filter}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
        ORDER BY yr, mo
    """)
    if not df_coll_m.empty:
        df_coll_m = month_col(df_coll_m)
        if not df_pay_m.empty:
            df_pay_m = month_col(df_pay_m)
            df_cf = df_coll_m.merge(df_pay_m[["month", "payments"]], on="month", how="outer").fillna(0)
        else:
            df_cf = df_coll_m.copy()
            df_cf["payments"] = 0
        df_cf["net"] = df_cf["collections"] - df_cf["payments"]
        df_cf = scale_cr(df_cf, "collections", "payments", "net")
        st.plotly_chart(
            grouped_bar(df_cf, x="month", series=[
                {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
                {"col": "payments",    "name": "Payments",    "color": COLORS["purchase"]},
            ], yaxis_title="₹ Crores"),
            use_container_width=True, key="cf_monthly"
        )
        st.subheader("Net Monthly Cash Flow")
        st.plotly_chart(
            area_chart(df_cf, x="month",
                       y_cols=[{"col": "net", "name": "Net Cash Flow",
                                "color": COLORS["info"]}],
                       yaxis_title="₹ Crores"),
            use_container_width=True, key="cf_net_area"
        )

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Top 15 Customers — Collections")
        df_cust_coll = query(f"""
            SELECT TOP 15 p.PartyName AS customer,
                   SUM(d.Amount) AS collections
            FROM TrVocDetail d
            JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsPartyMaster p ON p.PartyID=d.PartyID
            WHERE t.ShortName IN ('BR','CR')
              AND ISNULL(h.Cancelled,'N') <> 'Y'
              AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
              {date_filter}
            GROUP BY p.PartyName
            ORDER BY collections DESC
        """)
        if not df_cust_coll.empty:
            df_cust_coll = scale_cr(df_cust_coll, "collections")
            st.plotly_chart(bar_chart(df_cust_coll, x="customer", y="collections",
                                      orientation="h", color_scale="Greens",
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="cf_cust_coll")

    with col_r:
        st.subheader("Payments by Type")
        df_pay_type = query(f"""
            SELECT t.TransTypeName AS pay_type, SUM(d.Amount) AS payments
            FROM TrVocDetail d
            JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ({PAYMENT_IN})
              AND d.DrCrIndicator='D'
              AND ISNULL(h.Cancelled,'N') <> 'Y'
              {date_filter}
            GROUP BY t.TransTypeName ORDER BY payments DESC
        """)
        if not df_pay_type.empty:
            st.plotly_chart(pie_chart(df_pay_type, "pay_type", "payments",
                                      "Payment Distribution"),
                            use_container_width=True, key="cf_pay_pie")

    st.divider()

    # ── Collection efficiency ─────────────────────────────────────────────────
    st.subheader("Collection Efficiency — Last 12 Months")
    _12m = "AND COALESCE(h.TPDate, h.VoucherDate) >= DATEADD(MONTH,-12,GETDATE())"
    df_eff_s = query(f"""
        SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
               SUM(i.TotalAmount) AS sales
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND ISNULL(i.FreeItemYN,'N') <> 'Y' {_12m}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
    """)
    df_eff_c = query(f"""
        SELECT YEAR(COALESCE(h.TPDate, h.VoucherDate)) AS yr, MONTH(COALESCE(h.TPDate, h.VoucherDate)) AS mo,
               SUM(d.Amount) AS collected
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR')
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D' {_12m}
        GROUP BY YEAR(COALESCE(h.TPDate, h.VoucherDate)), MONTH(COALESCE(h.TPDate, h.VoucherDate))
    """)
    if not df_eff_s.empty:
        df_eff_s = month_col(df_eff_s)
        if not df_eff_c.empty:
            df_eff_c = month_col(df_eff_c)
            df_eff = df_eff_s.merge(df_eff_c[["month","collected"]], on="month", how="left").fillna(0)
        else:
            df_eff = df_eff_s.copy(); df_eff["collected"] = 0
        df_eff_cr = scale_cr(df_eff, "sales", "collected")
        st.plotly_chart(
            grouped_bar(df_eff_cr, x="month", series=[
                {"col": "sales",     "name": "Sales",     "color": COLORS["sales"]},
                {"col": "collected", "name": "Collected", "color": COLORS["collection"]},
            ], yaxis_title="₹ Crores"),
            use_container_width=True, key="cf_efficiency"
        )

    st.divider()

    # ── Expense breakdown by GL account ──────────────────────────────────────
    st.subheader("Expenses by Account (BP + CE vouchers → GL accounts)")
    st.caption(
        "GL expense accounts (MainHeadType=4) debited on Bank Payment and Cash Expense vouchers."
    )
    df_exp = query(f"""
        SELECT TOP 30
            a.AccHeadName AS account,
            SUM(d.Amount) AS amount,
            COUNT(DISTINCT CAST(d.TransTypeID AS VARCHAR)+'|'+d.VoucherNo) AS vouchers
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsAccountHead a ON a.AccHeadID = d.AccHeadID
        WHERE t.ShortName IN ('BP','CE')
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND d.DrCrIndicator='D'
          AND a.MainHeadType = 4
          {date_filter}
        GROUP BY a.AccHeadName
        ORDER BY amount DESC
    """)
    if not df_exp.empty:
        df_exp_cr = df_exp.copy()
        df_exp_cr["amount_cr"] = df_exp_cr["amount"] / 10_000_000
        st.plotly_chart(
            bar_chart(df_exp_cr, x="account", y="amount_cr",
                      orientation="h",
                      color=COLORS["warning"],
                      yaxis_title="₹ Crores"),
            use_container_width=True, key="cf_exp_gl"
        )
        df_exp_csv  = df_exp[["account", "amount", "vouchers"]].copy()
        df_exp_disp = df_exp_csv.copy()
        df_exp_disp["amount"] = df_exp_disp["amount"].apply(fmt_inr)
        df_exp_disp.columns = ["GL Account", "Amount", "Vouchers"]
        st.dataframe(df_exp_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Expenses CSV",
            data=df_exp_csv.to_csv(index=False),
            file_name="expenses_by_gl.csv",
            mime="text/csv",
            key="cf_dl_exp",
        )
    else:
        st.info("No expense GL account entries found for this period.")
