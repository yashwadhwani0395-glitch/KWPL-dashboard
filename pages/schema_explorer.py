import streamlit as st
import json
from db import get_connection


def _q(cur, sql):
    try:
        cur.execute(sql)
        return cur.fetchall() or []
    except Exception as e:
        return [{"ERROR": str(e)}]


def render():
    st.header("🔍 DB Schema Report")

    btn_spot = st.empty()
    status   = st.empty()

    status.info("⏳ Querying database — this may take 15–30 seconds...")

    try:
        conn = get_connection()
        cur  = conn.cursor(as_dict=True)
        report = {}

        report["all_tables"] = _q(cur,
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")

        tables = _q(cur,
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE='BASE TABLE' "
            "AND (TABLE_NAME LIKE 'Ms%' OR TABLE_NAME LIKE 'X%' OR TABLE_NAME LIKE 'Tr%') "
            "ORDER BY TABLE_NAME")

        report["master_tables"] = {}
        for row in tables:
            tbl = row["TABLE_NAME"]
            cols   = _q(cur, f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tbl}' ORDER BY ORDINAL_POSITION")
            sample = _q(cur, f"SELECT TOP 10 * FROM {tbl}")
            cnt    = _q(cur, f"SELECT COUNT(*) AS cnt FROM {tbl}")
            report["master_tables"][tbl] = {
                "columns": cols,
                "sample":  sample,
                "row_count": cnt[0].get("cnt", 0) if cnt else 0,
            }

        report["MsAccountHead_all"]       = _q(cur, "SELECT * FROM MsAccountHead ORDER BY 1")
        report["MsTransType_all"]          = _q(cur, "SELECT * FROM MsTransType ORDER BY ShortName, id_key")
        report["MsPartyMaster_columns"]    = _q(cur, "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MsPartyMaster' ORDER BY ORDINAL_POSITION")
        report["MsPartyMaster_sample"]     = _q(cur, "SELECT TOP 20 * FROM MsPartyMaster")
        report["MsItemBatchOpening_cols"]  = _q(cur, "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MsItemBatchOpening' ORDER BY ORDINAL_POSITION")
        report["MsItemBatchOpening_sample"]= _q(cur, "SELECT TOP 5 * FROM MsItemBatchOpening")

        report["br_cr_party_breakdown"] = _q(cur, """
            SELECT CASE WHEN d.PartyID IS NULL THEN 'NULL' ELSE 'SET' END AS party_status,
                   d.DrCrIndicator, COUNT(*) AS entries, SUM(d.Amount) AS total
            FROM TrVocDetail d
            JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
            JOIN MsTransType t ON t.id_key=h.TransTypeID
            WHERE t.ShortName IN ('BR','CR') AND h.Cancelled<>'Y'
            GROUP BY CASE WHEN d.PartyID IS NULL THEN 'NULL' ELSE 'SET' END, d.DrCrIndicator
        """)

        for short, key in [("BR", "sample_BR_voucher"), ("MS", "sample_MS_voucher"), ("PU", "sample_PU_voucher")]:
            hdr = _q(cur, f"""
                SELECT TOP 1 h.VoucherNo, h.TransTypeID, h.VoucherDate
                FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='{short}' AND h.Cancelled<>'Y'
            """)
            if hdr and "ERROR" not in hdr[0]:
                vno, ttid = hdr[0]["VoucherNo"], hdr[0]["TransTypeID"]
                lines = _q(cur, f"""
                    SELECT d.*, p.PartyName, ah.AccountName
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p  ON p.PartyID=d.PartyID
                    LEFT JOIN MsAccountHead ah ON ah.AccountID=d.AccHeadID
                    WHERE d.TransTypeID={ttid} AND d.VoucherNo='{vno}'
                """)
                report[key] = {"header": hdr[0], "lines": lines}

        conn.close()

        def _serial(o):
            return str(o)

        data = json.dumps(report, indent=2, default=_serial).encode("utf-8")
        status.success("✅ Done! Click the button below to download.")
        btn_spot.download_button(
            label="⬇️ Download schema_report.json",
            data=data,
            file_name="schema_report.json",
            mime="application/json",
        )

    except Exception as e:
        status.error(f"❌ Error: {e}")
        st.exception(e)
