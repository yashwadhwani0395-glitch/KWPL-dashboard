import streamlit as st
import pandas as pd
from db import query
from config import SALES_IN, NOT_CANCELLED, COLORS
from utils import fmt_inr, month_col
from components.kpi_cards import kpi_row
from components.charts import bar_chart, grouped_bar, pie_chart, area_chart


RECEIPT_CODES = ("'BR'", "'CR'")
PAYMENT_CODES = ("'BP'", "'CE'")
RECEIPT_IN    = ",".join(RECEIPT_CODES)
PAYMENT_IN    = ",".join(PAYMENT_CODES)


def render():
    st.header("Cash Flow & Expenses")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    kpi = query(f"""
        SELECT
            SUM(CASE WHEN t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='C'
                THEN d.Amount ELSE 0 END)  AS total_collections,
            SUM(CASE WHEN t.ShortName IN ({PAYMENT_IN}) AND d.DrCrIndicator='D'
                THEN d.Amount ELSE 0 END)  AS total_payments,
            COUNT(DISTINCT CASE WHEN t.ShortName IN ({RECEIPT_IN})
                THEN h.VoucherNo END)       AS receipt_count,
            COUNT(DISTINCT CASE WHEN t.ShortName IN ({PAYMENT_IN})
                THEN h.VoucherNo END)       AS payment_count
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE h.Cancelled <> 'Y'
    """)
    kpi_row([
        {"label": "Total Collections", "value": kpi["total_collections"][0], "fmt": "inr"},
        {"label": "Total Payments",    "value": kpi["total_payments"][0],    "fmt": "inr"},
        {"label": "Receipt Vouchers",  "value": kpi["receipt_count"][0],     "fmt": "qty"},
        {"label": "Payment Vouchers",  "value": kpi["payment_count"][0],     "fmt": "qty"},
    ])

    st.divider()

    # ── Monthly collections vs payments ──────────────────────────────────────
    st.subheader("Monthly Collections vs Payments")
    df_cf = query(f"""
        SELECT
            YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='C'
                THEN d.Amount ELSE 0 END) AS collections,
            SUM(CASE WHEN t.ShortName IN ({PAYMENT_IN}) AND d.DrCrIndicator='D'
                THEN d.Amount ELSE 0 END) AS payments
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE h.Cancelled <> 'Y'
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
        ORDER BY yr, mo
    """)
    if not df_cf.empty:
        df_cf = month_col(df_cf)
        df_cf["net"] = df_cf["collections"] - df_cf["payments"]
        fig = grouped_bar(df_cf, x="month", series=[
            {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
            {"col": "payments",    "name": "Payments",    "color": COLORS["purchase"]},
        ])
        st.plotly_chart(fig, use_container_width=True, key="cf_monthly")

        # Net cash flow area chart
        st.subheader("Net Monthly Cash Flow")
        st.plotly_chart(
            area_chart(df_cf, x="month",
                       y_cols=[{"col": "net", "name": "Net Cash Flow",
                                "color": COLORS["info"]}]),
            use_container_width=True, key="cf_net_area"
        )

    st.divider()

    # ── Collections by salesman ───────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Collections by Salesman")
        df_sm_coll = query(f"""
            SELECT s.FullName AS salesman, SUM(d.Amount) AS collections
            FROM TrVocDetail d
            JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
            WHERE t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='C'
              AND h.Cancelled <> 'Y' AND s.ResignDate IS NULL
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
            WHERE t.ShortName IN ({PAYMENT_IN}) AND d.DrCrIndicator='D'
              AND h.Cancelled <> 'Y'
            GROUP BY t.TransTypeName ORDER BY payments DESC
        """)
        if not df_pay_type.empty:
            st.plotly_chart(pie_chart(df_pay_type, "pay_type", "payments",
                                      "Payment Distribution"),
                            use_container_width=True, key="cf_pay_pie")

    st.divider()

    # ── Collection efficiency: sales vs collected ─────────────────────────────
    st.subheader("Collection Efficiency — Last 12 Months")
    df_eff = query(f"""
        SELECT
            YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
            SUM(CASE WHEN h.TransTypeID IN ({SALES_IN}) AND i.FreeItemYN<>'Y'
                THEN i.TotalAmount ELSE 0 END) AS sales,
            0 AS collections
        FROM TrVocHead h
        LEFT JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
        WHERE h.TransTypeID IN ({SALES_IN}) {NOT_CANCELLED}
          AND h.VoucherDate >= DATEADD(MONTH,-12,GETDATE())
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
    """)
    df_coll12 = query(f"""
        SELECT YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
               SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='C'
          AND h.Cancelled <> 'Y'
          AND h.VoucherDate >= DATEADD(MONTH,-12,GETDATE())
        GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
    """)
    if not df_eff.empty and not df_coll12.empty:
        df_eff = month_col(df_eff)
        df_coll12 = month_col(df_coll12)
        df_eff = df_eff.merge(df_coll12[["month","collections"]],
                              on="month", how="left", suffixes=("_drop",""))
        df_eff = df_eff.drop(columns=["collections_drop"], errors="ignore").fillna(0)
        fig = grouped_bar(df_eff, x="month", series=[
            {"col": "sales",       "name": "Sales",       "color": COLORS["sales"]},
            {"col": "collections", "name": "Collections", "color": COLORS["collection"]},
        ])
        st.plotly_chart(fig, use_container_width=True, key="cf_efficiency")

    st.divider()

    # ── Top payers ────────────────────────────────────────────────────────────
    st.subheader("Top 15 Customers by Collections")
    df_top_pay = query(f"""
        SELECT TOP 15 p.PartyName AS customer, SUM(d.Amount) AS collections
        FROM TrVocDetail d
        JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE t.ShortName IN ({RECEIPT_IN}) AND d.DrCrIndicator='C'
          AND h.Cancelled <> 'Y'
        GROUP BY p.PartyName ORDER BY collections DESC
    """)
    if not df_top_pay.empty:
        st.plotly_chart(bar_chart(df_top_pay, x="customer", y="collections",
                                  orientation="h", color_scale="Greens"),
                        use_container_width=True, key="cf_top_payers")
