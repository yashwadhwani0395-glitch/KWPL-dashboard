import streamlit as st
import pandas as pd
from db import get_connection


def _q(conn, sql):
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(sql)
        rows = cur.fetchall()
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as e:
        return pd.DataFrame([{"ERROR": str(e)}])


def render():
    st.header("Database Schema Explorer (Temporary Debug Page)")
    st.info("Use this page to understand the full DB structure. Remove after exploration.")

    conn = get_connection()

    # ── 1. All tables ─────────────────────────────────────────────────────────
    st.subheader("1. All Tables in Database")
    all_tables = _q(conn, """
        SELECT TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
        ORDER BY TABLE_NAME
    """)
    st.dataframe(all_tables, use_container_width=True, hide_index=True)

    # ── 2. All columns for every Ms* and X* table ────────────────────────────
    st.subheader("2. Columns for Master Tables (Ms*, X*, Tr*)")
    master_tables = _q(conn, """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE 'Ms%' OR TABLE_NAME LIKE 'X%')
        ORDER BY TABLE_NAME
    """)

    if not master_tables.empty:
        for tbl in master_tables["TABLE_NAME"].tolist():
            with st.expander(f"📋 {tbl}"):
                cols = _q(conn, f"""
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = '{tbl}'
                    ORDER BY ORDINAL_POSITION
                """)
                st.dataframe(cols, use_container_width=True, hide_index=True)

                sample = _q(conn, f"SELECT TOP 5 * FROM {tbl}")
                if not sample.empty:
                    st.write("Sample data:")
                    st.dataframe(sample, use_container_width=True, hide_index=True)

    # ── 3. Full MsPartyMaster deep dive ──────────────────────────────────────
    st.subheader("3. MsPartyMaster — Full Column List + Sample")
    party_cols = _q(conn, """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='MsPartyMaster'
        ORDER BY ORDINAL_POSITION
    """)
    st.dataframe(party_cols, use_container_width=True, hide_index=True)

    st.write("Sample rows:")
    st.dataframe(_q(conn, "SELECT TOP 10 * FROM MsPartyMaster"), use_container_width=True, hide_index=True)

    st.write("Row count:")
    st.dataframe(_q(conn, "SELECT COUNT(*) AS total_parties FROM MsPartyMaster"), use_container_width=True, hide_index=True)

    # ── 4. MsTransType — every row ───────────────────────────────────────────
    st.subheader("4. MsTransType — All Rows")
    tt_cols = _q(conn, """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='MsTransType'
        ORDER BY ORDINAL_POSITION
    """)
    st.write("Columns:", tt_cols["COLUMN_NAME"].tolist() if not tt_cols.empty else "N/A")
    st.dataframe(_q(conn, "SELECT * FROM MsTransType ORDER BY ShortName, id_key"),
                 use_container_width=True, hide_index=True)

    # ── 5. Any AccHead / MainHead / SubHead tables ───────────────────────────
    st.subheader("5. Account Hierarchy Tables (AccHead / MainHead / SubHead)")
    acct_tables = _q(conn, """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE '%AccHead%'
               OR TABLE_NAME LIKE '%MainHead%'
               OR TABLE_NAME LIKE '%SubHead%'
               OR TABLE_NAME LIKE '%Account%'
               OR TABLE_NAME LIKE '%Ledger%')
        ORDER BY TABLE_NAME
    """)
    if not acct_tables.empty:
        for tbl in acct_tables["TABLE_NAME"].tolist():
            with st.expander(f"📋 {tbl}"):
                cols = _q(conn, f"""
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='{tbl}'
                    ORDER BY ORDINAL_POSITION
                """)
                st.dataframe(cols, use_container_width=True, hide_index=True)
                sample = _q(conn, f"SELECT TOP 10 * FROM {tbl}")
                st.write("Sample data:")
                st.dataframe(sample, use_container_width=True, hide_index=True)
                cnt = _q(conn, f"SELECT COUNT(*) AS rows FROM {tbl}")
                st.write("Row count:", cnt)
    else:
        st.warning("No tables matching AccHead/MainHead/SubHead/Account/Ledger found.")

    # ── 6. TrVocDetail — distinct AccHeadID values (top 50) ─────────────────
    st.subheader("6. TrVocDetail — What AccHeadIDs are used?")
    st.dataframe(
        _q(conn, """
            SELECT TOP 50 AccHeadID, COUNT(*) AS entries,
                   SUM(CASE WHEN DrCrIndicator='D' THEN Amount ELSE 0 END) AS total_debit,
                   SUM(CASE WHEN DrCrIndicator='C' THEN Amount ELSE 0 END) AS total_credit
            FROM TrVocDetail
            GROUP BY AccHeadID
            ORDER BY entries DESC
        """),
        use_container_width=True, hide_index=True
    )

    # ── 7. TrVocDetail — entries where PartyID is set ─────────────────────────
    st.subheader("7. TrVocDetail — PartyID null vs not-null breakdown")
    st.dataframe(
        _q(conn, """
            SELECT
                CASE WHEN PartyID IS NULL THEN 'PartyID IS NULL' ELSE 'PartyID set' END AS party_status,
                DrCrIndicator,
                COUNT(*) AS entries,
                SUM(Amount) AS total_amount
            FROM TrVocDetail
            JOIN TrVocHead h ON h.TransTypeID=TrVocDetail.TransTypeID AND h.VoucherNo=TrVocDetail.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ('BR','CR')
            GROUP BY CASE WHEN PartyID IS NULL THEN 'PartyID IS NULL' ELSE 'PartyID set' END, DrCrIndicator
            ORDER BY entries DESC
        """),
        use_container_width=True, hide_index=True
    )

    # ── 8. Sample BR/CR voucher with all its detail lines ────────────────────
    st.subheader("8. Sample BR/CR Voucher — all detail lines")
    sample_voucher = _q(conn, """
        SELECT TOP 1 h.VoucherNo, h.TransTypeID
        FROM TrVocHead h
        JOIN MsTransType t ON t.id_key=h.TransTypeID
        WHERE t.ShortName IN ('BR','CR') AND h.Cancelled<>'Y'
    """)
    if not sample_voucher.empty:
        vno = sample_voucher["VoucherNo"][0]
        ttid = sample_voucher["TransTypeID"][0]
        st.write(f"VoucherNo: {vno}, TransTypeID: {ttid}")
        st.dataframe(
            _q(conn, f"""
                SELECT d.*, p.PartyName
                FROM TrVocDetail d
                LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                WHERE d.TransTypeID={ttid} AND d.VoucherNo='{vno}'
            """),
            use_container_width=True, hide_index=True
        )

    conn.close()
