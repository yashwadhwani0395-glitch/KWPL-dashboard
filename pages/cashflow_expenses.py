import streamlit as st
import pandas as pd
from db import query
from config import NOT_CANCELLED, NOT_FREE, COLORS
from utils import fmt_inr, month_col
from components.kpi_cards import kpi_row
from components.charts import bar_chart, grouped_bar, pie_chart, area_chart


RECEIPT_IN = "'BR','CR'"
PAYMENT_IN = "'BP','CE'"
COLL_IND   = "D"   # bank/cash debit = money received
PAY_IND    = "D"   # expense/supplier debit = money paid out


def render():
    st.header("Cash Flow & Expenses")
    date_filter = st.session_state.get("date_filter", "")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpi = query(f"""
        SELECT
            SUM(CASE WHEN t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='{COLL_IND}'
                THEN d.Amount ELSE 0 END) AS total_collections,
            SUM(CASE WHEN t.ShortName IN ({PAYMENT_IN}) AND d.DrCrIndicator='{PAY_IND}'
                THEN d.Amount ELSE 0 END) AS total_payments
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
    """)
    rcpt_count = query(f"""
        SELECT
            COUNT(CASE WHEN t.ShortName IN ({RECEIPT_IN}) THEN 1 END) AS receipt_count,
            COUNT(CASE WHEN t.ShortName IN ({PAYMENT_IN}) THEN 1 END) AS payment_count
        FROM TrVocHead h
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE ISNULL(h.Cancelled,'N') <> 'Y'
          AND t.ShortName IN ({RECEIPT_IN},{PAYMENT_IN})
          {date_filter}
    """)
    kpi_row([
        {"label": "Total Collections", "value": kpi["total_collections"][0], "fmt": "inr"},
        {"label": "Total Payments",    "value": kpi["total_payments"][0],    "fmt": "inr"},
        {"label": "Receipt Vouchers",  "value": rcpt_count["receipt_count"][0], "fmt": "qty"},
        {"label": "Payment Vouchers",  "value": rcpt_count["payment_count"][0], "fmt": "qty"},
    ])

    st.divider()

    # ── Monthly collections vs payments ──────────────────────────────────────
    st.subheader("Monthly Collections vs Payments")
    df_cf = query(f"""
        SELECT
            YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='{COLL_IND}'
                THEN d.Amount ELSE 0 END) AS collections,
            SUM(CASE WHEN t.ShortName IN ({PAYMENT_IN}) AND d.DrCrIndicator='{PAY_IND}'
                THEN d.Amount ELSE 0 END) AS payments
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """)
    if not df_cf.empty:
        df_cf = month_col(df_cf)
        df_cf["net"] = df_cf["collections"] - df_cf["payments"]
        st.plotly_chart(
            grouped_bar(df_cf, x="month", series=[
                {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
                {"col": "payments",    "name": "Payments",    "color": COLORS["purchase"]},
            ]),
            use_container_width=True, key="cf_monthly"
        )
        st.subheader("Net Monthly Cash Flow")
        st.plotly_chart(
            area_chart(df_cf, x="month",
                       y_cols=[{"col": "net", "name": "Net Cash Flow",
                                "color": COLORS["info"]}]),
            use_container_width=True, key="cf_net_area"
        )

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Collections by Salesman")
        df_sm_coll = query(f"""
            SELECT s.FullName AS salesman, SUM(d.Amount) AS collections
            FROM TrVocDetail d
            JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
            WHERE t.ShortName IN ({RECEIPT_IN})
              AND d.DrCrIndicator='{COLL_IND}'
              AND ISNULL(h.Cancelled,'N') <> 'Y'
              AND s.ResignDate IS NULL
              {date_filter}
            GROUP BY s.FullName ORDER BY collections DESC
        """)
        if not df_sm_coll.empty:
            st.plotly_chart(bar_chart(df_sm_coll, x="salesman", y="collections",
                                      color_scale="Greens"),
                            use_container_width=True, key="cf_sm_coll")

    with col_r:
        st.subheader("Payments by Type")
        df_pay_type = query(f"""
            SELECT t.TransTypeName AS pay_type, SUM(d.Amount) AS payments
            FROM TrVocDetail d
            JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ({PAYMENT_IN})
              AND d.DrCrIndicator='{PAY_IND}'
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
    df_eff_sales = query(f"""
        SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
               SUM(i.TotalAmount) AS sales
        FROM TrVocHead h
        JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName='MS' {NOT_CANCELLED} {NOT_FREE}
          AND h.VoucherDate >= DATEADD(MONTH,-12,GETDATE())
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
    """)
    df_eff_coll = query(f"""
        SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
               SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ({RECEIPT_IN})
          AND d.DrCrIndicator='{COLL_IND}'
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          AND h.VoucherDate >= DATEADD(MONTH,-12,GETDATE())
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
    """)
    if not df_eff_sales.empty:
        df_eff_sales = month_col(df_eff_sales)
        if not df_eff_coll.empty:
            df_eff_coll = month_col(df_eff_coll)
            df_eff = df_eff_sales.merge(df_eff_coll[["month","collections"]],
                                        on="month", how="left").fillna(0)
        else:
            df_eff = df_eff_sales.copy()
            df_eff["collections"] = 0
        st.plotly_chart(
            grouped_bar(df_eff, x="month", series=[
                {"col": "sales",       "name": "Sales",       "color": COLORS["sales"]},
                {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
            ]),
            use_container_width=True, key="cf_efficiency"
        )

    st.divider()

    # ── Top payers ────────────────────────────────────────────────────────────
    st.subheader("Top 15 Customers by Collections")
    df_top_pay = query(f"""
        SELECT TOP 15 p.PartyName AS customer, SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE t.ShortName IN ({RECEIPT_IN})
          AND d.DrCrIndicator='C'
          AND d.PartyID IS NOT NULL
          AND ISNULL(h.Cancelled,'N') <> 'Y'
          {date_filter}
        GROUP BY p.PartyName ORDER BY collections DESC
    """)
    if not df_top_pay.empty:
        st.plotly_chart(bar_chart(df_top_pay, x="customer", y="collections",
                                  orientation="h", color_scale="Greens"),
                        use_container_width=True, key="cf_top_payers")
