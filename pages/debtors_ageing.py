import streamlit as st
import pandas as pd
from db import query
from config import SALES_IN, NOT_CANCELLED, COLORS
from utils import fmt_inr, fmt_qty, scale_cr
from components.kpi_cards import kpi_row
from components.charts import bar_chart, pie_chart


def render():
    st.header("Debtors & Outstanding")
    date_filter = st.session_state.get("date_filter", "")
    cutoff      = st.session_state.get("outstanding_cutoff")           # None = today
    cutoff_sql  = f"AND COALESCE(h.TPDate, h.VoucherDate) < '{cutoff}'" if cutoff else ""
    # CloseBal = FY end (31.03.2026); CloseBalTmp = running current balance
    bal_col     = "CloseBal" if cutoff else "CloseBalTmp"

    # ── KPIs — from MsPartyOpening (pre-computed closing balances, matches ERP) ─
    kpi = query(f"""
        SELECT
            COUNT(CASE WHEN {bal_col} > 0 THEN 1 END) AS debtors,
            SUM({bal_col})                             AS total_outstanding,
            MAX({bal_col})                             AS largest_balance
        FROM MsPartyOpening
        WHERE LEFT(PartyID, 1) = 'D'
    """)
    kpi_row([
        {"label": "Active Debtors",    "value": kpi["debtors"][0],          "fmt": "qty"},
        {"label": "Total Outstanding", "value": kpi["total_outstanding"][0],"fmt": "inr"},
        {"label": "Largest Balance",   "value": kpi["largest_balance"][0],  "fmt": "inr"},
    ])

    st.divider()

    # ── Ageing buckets ────────────────────────────────────────────────────────
    st.subheader("Ageing Analysis")
    df_age = query(f"""
        SELECT
            p.PartyName                                                      AS customer,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN  0 AND  30 THEN d.RemainingAmt ELSE 0 END) AS d0_30,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN 31 AND  60 THEN d.RemainingAmt ELSE 0 END) AS d31_60,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN 61 AND  90 THEN d.RemainingAmt ELSE 0 END) AS d61_90,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE()) BETWEEN 91 AND 180 THEN d.RemainingAmt ELSE 0 END) AS d91_180,
            SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE())  > 180             THEN d.RemainingAmt ELSE 0 END) AS d180_plus,
            SUM(d.RemainingAmt)                                              AS total
        FROM TrVocDetail d
        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        JOIN MsPartyMaster p ON p.PartyID=d.PartyID
        WHERE t.ShortName='MS' {NOT_CANCELLED}
          AND d.DrCrIndicator='D' AND d.RemainingAmt > 0
          AND LEFT(d.PartyID,1)='D'
          {date_filter}
        GROUP BY p.PartyName ORDER BY total DESC
    """)

    if not df_age.empty:
        # Bucket summary bar
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
                                      color=COLORS["warning"],
                                      title="Outstanding by Age Bucket",
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="da_buckets")
        with col_r:
            st.plotly_chart(pie_chart(df_buckets, "bucket", "amount",
                                      title="Age Distribution"),
                            use_container_width=True, key="da_bucket_pie")

        st.divider()

        # ── Top debtors chart (from MsPartyOpening — matches ERP balance) ───────
        st.subheader("Top 20 Debtors by Outstanding")
        df_top20 = query(f"""
            SELECT TOP 20 p.PartyName AS customer, op.{bal_col} AS outstanding
            FROM MsPartyOpening op
            JOIN MsPartyMaster p ON p.PartyID = op.PartyID
            WHERE LEFT(op.PartyID, 1) = 'D' AND op.{bal_col} > 0
            ORDER BY op.{bal_col} DESC
        """)
        if not df_top20.empty:
            df_top20["outstanding_cr"] = df_top20["outstanding"] / 1_00_00_000
            st.plotly_chart(bar_chart(df_top20, x="customer", y="outstanding_cr",
                                      orientation="h", color_scale="Reds",
                                      yaxis_title="₹ Crores"),
                            use_container_width=True, key="da_top_debtors")

        st.divider()

        # ── Ageing detail table ───────────────────────────────────────────────
        st.subheader("Customer-wise Ageing Detail")

        # Filter controls
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            min_outstanding = st.number_input(
                "Show only if outstanding ≥ ₹", min_value=0, value=0, step=10000
            )
        with col_f2:
            highlight_overdue = st.checkbox("Highlight >90 days overdue", value=True)

        df_show = df_age[df_age["total"] >= min_outstanding].copy()
        df_csv  = df_show.copy()

        for col in ["d0_30", "d31_60", "d61_90", "d91_180", "d180_plus", "total"]:
            df_show[col] = df_show[col].apply(fmt_inr)

        df_show.columns = [
            "Customer", "0-30 Days", "31-60 Days", "61-90 Days",
            "91-180 Days", ">180 Days", "Total"
        ]
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download CSV",
            data=df_csv.to_csv(index=False),
            file_name="debtors_ageing.csv",
            mime="text/csv",
            key="da_dl_ageing",
        )

    # ── Salesman-wise outstanding — net ledger balance per salesman ───────────
    st.divider()
    st.subheader("Salesman-wise Outstanding")
    df_sm = query(f"""
        SELECT s.FullName AS salesman,
               COUNT(DISTINCT op.PartyID) AS debtors,
               SUM(op.{bal_col})          AS outstanding
        FROM MsPartyOpening op
        JOIN MsPartyMaster p  ON p.PartyID    = op.PartyID
        JOIN MsSalesmanMaster s ON s.SalesManID = p.SalesManID
        WHERE LEFT(op.PartyID, 1) = 'D'
          AND op.{bal_col} > 0
          AND s.ResignDate IS NULL
        GROUP BY s.FullName ORDER BY outstanding DESC
    """)
    if not df_sm.empty:
        df_sm["outstanding_cr"] = df_sm["outstanding"] / 1_00_00_000
        st.plotly_chart(bar_chart(df_sm, x="salesman", y="outstanding_cr",
                                  color_scale="Oranges",
                                  yaxis_title="₹ Crores"),
                        use_container_width=True, key="da_salesman")
        df_sm_csv  = df_sm[["salesman", "debtors", "outstanding"]].copy()
        df_sm_disp = df_sm_csv.copy()
        df_sm_disp["outstanding"] = df_sm_disp["outstanding"].apply(fmt_inr)
        df_sm_disp.columns = ["Salesman", "Debtors", "Outstanding"]
        st.dataframe(df_sm_disp, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download CSV",
            data=df_sm_csv.to_csv(index=False),
            file_name="salesman_outstanding.csv",
            mime="text/csv",
            key="da_dl_sman",
        )
