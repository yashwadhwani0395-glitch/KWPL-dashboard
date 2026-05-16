import streamlit as st
import pandas as pd
from db import query
from config import NOT_CANCELLED, COLORS
from utils import fmt_inr, fmt_qty, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart


def render():
    st.header("Creditors & Payables")
    date_filter = st.session_state.get("date_filter", "")
    cutoff      = st.session_state.get("outstanding_cutoff")
    bal_col     = "CloseBal" if cutoff else "CloseBalTmp"

    # ── KPIs ─────────────────────────────────────────────────────────────────
    # CloseBal is negative for creditor balances (KWPL owes them), so use ABS.
    kpi = query(f"""
        SELECT
            COUNT(CASE WHEN ABS({bal_col}) > 0 THEN 1 END) AS creditors,
            SUM(ABS({bal_col}))                             AS total_payable,
            MAX(ABS({bal_col}))                             AS largest_balance
        FROM MsPartyOpening
        WHERE LEFT(PartyID, 1) = 'C'
          AND {bal_col} < 0
    """)
    kpi_row([
        {"label": "Active Creditors",  "value": kpi["creditors"][0],      "fmt": "qty"},
        {"label": "Total Payable",     "value": kpi["total_payable"][0],   "fmt": "inr"},
        {"label": "Largest Balance",   "value": kpi["largest_balance"][0], "fmt": "inr"},
    ])

    st.divider()

    # ── Ageing buckets ────────────────────────────────────────────────────────
    st.subheader("Ageing Analysis")
    df_age = query(f"""
        SELECT
            p.PartyName                                                           AS supplier,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN  0 AND  30 THEN d.RemainingAmt ELSE 0 END) AS d0_30,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN 31 AND  60 THEN d.RemainingAmt ELSE 0 END) AS d31_60,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN 61 AND  90 THEN d.RemainingAmt ELSE 0 END) AS d61_90,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN 91 AND 180 THEN d.RemainingAmt ELSE 0 END) AS d91_180,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE())  > 180             THEN d.RemainingAmt ELSE 0 END) AS d180_plus,
            SUM(d.RemainingAmt)                                                   AS total
        FROM TrVocDetail d
        JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE t.ShortName IN ('PU','PE')
          {NOT_CANCELLED}
          AND d.DrCrIndicator='C' AND d.RemainingAmt > 0
          AND LEFT(d.PartyID,1)='C'
          {date_filter}
        GROUP BY p.PartyName ORDER BY total DESC
    """)

    if not df_age.empty:
        buckets = {
            "0-30 Days":   df_age["d0_30"].sum(),
            "31-60 Days":  df_age["d31_60"].sum(),
            "61-90 Days":  df_age["d61_90"].sum(),
            "91-180 Days": df_age["d91_180"].sum(),
            ">180 Days":   df_age["d180_plus"].sum(),
        }
        df_buckets = pd.DataFrame({"bucket": list(buckets.keys()),
                                   "amount": list(buckets.values())})
        df_buckets["amount_cr"] = df_buckets["amount"] / 1_00_00_000

        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(bar_chart(df_buckets, x="bucket", y="amount_cr",
                                      color=COLORS["purchase"],
                                      title="Payables by Age Bucket",
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="ca_buckets")
        with col_r:
            st.plotly_chart(pie_chart(df_buckets, "bucket", "amount",
                                      title="Age Distribution"),
                            use_container_width=True, key="ca_bucket_pie")

        st.divider()

    # ── Top creditors chart ───────────────────────────────────────────────────
    st.subheader("Top 20 Creditors by Payable")
    df_top20 = query(f"""
        SELECT TOP 20 p.PartyName AS supplier, ABS(op.{bal_col}) AS payable
        FROM MsPartyOpening op
        JOIN MsPartyMaster p ON p.PartyID = op.PartyID
        WHERE LEFT(op.PartyID, 1) = 'C' AND op.{bal_col} < 0
        ORDER BY ABS(op.{bal_col}) DESC
    """)
    if not df_top20.empty:
        df_top20["payable_cr"] = df_top20["payable"] / 1_00_00_000
        st.plotly_chart(bar_chart(df_top20, x="supplier", y="payable_cr",
                                  orientation="h", color_scale="Reds",
                                  yaxis_title="₹ Crores"),
                        use_container_width=True, key="ca_top_creditors")

    st.divider()

    # ── Ageing detail table with download ────────────────────────────────────
    st.subheader("Supplier-wise Ageing Detail")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        min_payable = st.number_input(
            "Show only if payable ≥ ₹", min_value=0, value=0, step=10000,
            key="ca_min_pay"
        )
    with col_f2:
        highlight_old = st.checkbox("Highlight >90 days overdue", value=True,
                                    key="ca_highlight")

    if not df_age.empty:
        df_show = df_age[df_age["total"] >= min_payable].copy()
        csv_data = df_show.copy()
        for col in ["d0_30", "d31_60", "d61_90", "d91_180", "d180_plus", "total"]:
            df_show[col] = df_show[col].apply(fmt_inr)
        df_show.columns = [
            "Supplier", "0-30 Days", "31-60 Days", "61-90 Days",
            "91-180 Days", ">180 Days", "Total"
        ]
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download CSV",
            data=csv_data.to_csv(index=False),
            file_name="creditors_ageing.csv",
            mime="text/csv",
        )
    else:
        st.info("No outstanding payable entries found for this period.")
