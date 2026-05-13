import streamlit as st
import json
from db import get_connection


def _q(cur, sql):
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        return rows or []
    except Exception as e:
        return [{"ERROR": str(e)}]


def render():
    st.header("🔍 Database Schema Explorer")

    if st.button("📥 Build & Download Full Schema Report", type="primary"):
        conn = get_connection()
        cur = conn.cursor(as_dict=True)
        report = {}

        # 1. All tables
        report["all_tables"] = _q(cur, """
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME
        """)

        # 2. All Ms* / X* / Tr* tables — columns + sample rows
        tables = _q(cur, """
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE='BASE TABLE'
              AND (TABLE_NAME LIKE 'Ms%' OR TABLE_NAME LIKE 'X%'
                   OR TABLE_NAME LIKE 'Tr%')
            ORDER BY TABLE_NAME
        """)
        report["master_tables"] = {}
        for row in tables:
            tbl = row["TABLE_NAME"]
            cols = _q(cur, f"""
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='{tbl}' ORDER BY ORDINAL_POSITION
            """)
            sample = _q(cur, f"SELECT TOP 10 * FROM {tbl}")
            count = _q(cur, f"SELECT COUNT(*) AS cnt FROM {tbl}")
            report["master_tables"][tbl] = {
                "columns": cols,
                "sample": sample,
                "row_count": count[0]["cnt"] if count else 0
            }

        # 3. MsAccountHead — all rows
        report["MsAccountHead_all"] = _q(cur, "SELECT * FROM MsAccountHead ORDER BY 1")

        # 4. MsTransType — all rows
        report["MsTransType_all"] = _q(cur, "SELECT * FROM MsTransType ORDER BY ShortName, id_key")

        # 5. MsPartyMaster — columns + 20 sample rows
        report["MsPartyMaster_columns"] = _q(cur, """
            SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME='MsPartyMaster' ORDER BY ORDINAL_POSITION
        """)
        report["MsPartyMaster_sample"] = _q(cur, "SELECT TOP 20 * FROM MsPartyMaster")

        # 6. TrVocDetail — PartyID breakdown on BR/CR vouchers
        report["collection_party_breakdown"] = _q(cur, """
            SELECT
                CASE WHEN d.PartyID IS NULL THEN 'NULL' ELSE 'SET' END AS party_status,
                d.DrCrIndicator, COUNT(*) AS entries, SUM(d.Amount) AS total
            FROM TrVocDetail d
            JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ('BR','CR') AND h.Cancelled<>'Y'
            GROUP BY CASE WHEN d.PartyID IS NULL THEN 'NULL' ELSE 'SET' END, d.DrCrIndicator
        """)

        # 7. Sample BR/CR voucher — all detail lines
        sample_voc = _q(cur, """
            SELECT TOP 1 h.VoucherNo, h.TransTypeID, t.ShortName, h.VoucherDate
            FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ('BR','CR') AND h.Cancelled<>'Y'
        """)
        if sample_voc:
            vno = sample_voc[0]["VoucherNo"]
            ttid = sample_voc[0]["TransTypeID"]
            report["sample_BR_CR_voucher"] = {
                "header": sample_voc[0],
                "detail_lines": _q(cur, f"""
                    SELECT d.*, p.PartyName, ah.AccountName
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    LEFT JOIN MsAccountHead ah ON ah.AccountID=d.AccHeadID
                    WHERE d.TransTypeID={ttid} AND d.VoucherNo='{vno}'
                """)
            }

        # 8. Sample MS (sales) voucher — all detail lines
        sample_ms = _q(cur, """
            SELECT TOP 1 h.VoucherNo, h.TransTypeID, h.VoucherDate
            FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName='MS' AND h.Cancelled<>'Y'
        """)
        if sample_ms:
            vno = sample_ms[0]["VoucherNo"]
            ttid = sample_ms[0]["TransTypeID"]
            report["sample_MS_voucher"] = {
                "header": sample_ms[0],
                "detail_lines": _q(cur, f"""
                    SELECT d.*, p.PartyName, ah.AccountName
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    LEFT JOIN MsAccountHead ah ON ah.AccountID=d.AccHeadID
                    WHERE d.TransTypeID={ttid} AND d.VoucherNo='{vno}'
                """)
            }

        # 9. MsItemBatchOpening — columns + sample
        report["MsItemBatchOpening_columns"] = _q(cur, """
            SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME='MsItemBatchOpening' ORDER BY ORDINAL_POSITION
        """)
        report["MsItemBatchOpening_sample"] = _q(cur, "SELECT TOP 5 * FROM MsItemBatchOpening")

        conn.close()

        # Serialise — convert any non-serialisable types to str
        def default(o):
            return str(o)

        json_bytes = json.dumps(report, indent=2, default=default).encode("utf-8")
        st.success("Schema report built! Click below to download.")
        st.download_button(
            label="⬇️ Download schema_report.json",
            data=json_bytes,
            file_name="schema_report.json",
            mime="application/json",
        )
