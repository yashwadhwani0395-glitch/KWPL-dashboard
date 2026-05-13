import streamlit as st
import json
from db import get_connection


def render():
    st.header("DB Schema Report")

    if "schema_json" not in st.session_state:
        if st.button("Generate Report"):
            with st.spinner("Querying database..."):
                try:
                    conn = get_connection()
                    cur = conn.cursor(as_dict=True)

                    def q(sql):
                        try:
                            cur.execute(sql)
                            return cur.fetchall() or []
                        except Exception as e:
                            return [{"ERROR": str(e)}]

                    data = {}
                    data["tables"] = q("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
                    data["MsPartyMaster_columns"] = q("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MsPartyMaster' ORDER BY ORDINAL_POSITION")
                    data["MsPartyMaster_sample"] = q("SELECT TOP 10 * FROM MsPartyMaster")
                    data["MsAccountHead_all"] = q("SELECT * FROM MsAccountHead")
                    data["MsTransType_all"] = q("SELECT * FROM MsTransType ORDER BY ShortName")
                    data["MsItemBatchOpening_cols"] = q("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MsItemBatchOpening' ORDER BY ORDINAL_POSITION")
                    data["MsItemBatchOpening_sample"] = q("SELECT TOP 3 * FROM MsItemBatchOpening")

                    for tbl in ["MsAccountHead", "MsSalesmanMaster", "MsBrandMaster", "MsLiquorType", "MsCodeMaster", "MsCodeTypeMaster"]:
                        data[f"{tbl}_cols"] = q(f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tbl}' ORDER BY ORDINAL_POSITION")
                        data[f"{tbl}_sample"] = q(f"SELECT TOP 5 * FROM {tbl}")

                    data["sample_BR"] = q("""
                        SELECT TOP 1 h.VoucherNo, h.TransTypeID FROM TrVocHead h
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='BR' AND h.Cancelled<>'Y'
                    """)
                    if data["sample_BR"] and "ERROR" not in data["sample_BR"][0]:
                        vno = data["sample_BR"][0]["VoucherNo"]
                        tid = data["sample_BR"][0]["TransTypeID"]
                        data["sample_BR_lines"] = q(f"SELECT * FROM TrVocDetail WHERE TransTypeID={tid} AND VoucherNo='{vno}'")

                    data["sample_MS"] = q("""
                        SELECT TOP 1 h.VoucherNo, h.TransTypeID FROM TrVocHead h
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='MS' AND h.Cancelled<>'Y'
                    """)
                    if data["sample_MS"] and "ERROR" not in data["sample_MS"][0]:
                        vno = data["sample_MS"][0]["VoucherNo"]
                        tid = data["sample_MS"][0]["TransTypeID"]
                        data["sample_MS_lines"] = q(f"SELECT * FROM TrVocDetail WHERE TransTypeID={tid} AND VoucherNo='{vno}'")

                    conn.close()
                    st.session_state["schema_json"] = json.dumps(data, indent=2, default=str).encode()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    else:
        st.success("Report ready!")
        st.download_button(
            label="⬇️ Download schema_report.json",
            data=st.session_state["schema_json"],
            file_name="schema_report.json",
            mime="application/json",
        )
        if st.button("Regenerate"):
            del st.session_state["schema_json"]
            st.rerun()
