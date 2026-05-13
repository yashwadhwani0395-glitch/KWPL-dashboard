import streamlit as st
import json
from db import get_connection


def render():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.header("Database Schema Explorer")
    with col2:
        generate = st.button("Generate Report", type="primary", use_container_width=True)

    if generate:
        with st.spinner("Querying database, please wait..."):
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
                data["MsAccountHead_columns"] = q("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MsAccountHead' ORDER BY ORDINAL_POSITION")
                data["XMainheadSubhead_all"] = q("SELECT * FROM XMainheadSubhead")
                data["XMainheadTypeMainhead_all"] = q("SELECT * FROM XMainheadTypeMainhead")
                data["MsTransType_all"] = q("SELECT * FROM MsTransType ORDER BY ShortName")
                data["MsItemBatchOpening_cols"] = q("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='MsItemBatchOpening' ORDER BY ORDINAL_POSITION")
                data["MsItemBatchOpening_sample"] = q("SELECT TOP 5 * FROM MsItemBatchOpening")
                data["MsSalesmanMaster_all"] = q("SELECT * FROM MsSalesmanMaster")

                for tbl in ["MsBrandMaster", "MsLiquorType", "MsSizeType", "MsServiceItemMaster", "MsCodeMaster"]:
                    data[f"{tbl}_sample"] = q(f"SELECT TOP 5 * FROM {tbl}")
                    data[f"{tbl}_cols"] = q(f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{tbl}' ORDER BY ORDINAL_POSITION")

                # Sample BR voucher
                br = q("SELECT TOP 1 h.VoucherNo, h.TransTypeID FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID WHERE t.ShortName='BR' AND h.Cancelled<>'Y'")
                if br and "ERROR" not in br[0]:
                    data["sample_BR_lines"] = q(f"SELECT * FROM TrVocDetail WHERE TransTypeID={br[0]['TransTypeID']} AND VoucherNo='{br[0]['VoucherNo']}'")

                # Sample MS voucher
                ms = q("SELECT TOP 1 h.VoucherNo, h.TransTypeID FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID WHERE t.ShortName='MS' AND h.Cancelled<>'Y'")
                if ms and "ERROR" not in ms[0]:
                    data["sample_MS_lines"] = q(f"SELECT * FROM TrVocDetail WHERE TransTypeID={ms[0]['TransTypeID']} AND VoucherNo='{ms[0]['VoucherNo']}'")

                conn.close()
                st.session_state["schema_json"] = json.dumps(data, indent=2, default=str).encode()

            except Exception as e:
                st.error(f"Error: {e}")
                return

    if "schema_json" in st.session_state:
        st.success("Ready!")
        st.download_button(
            label="⬇️ Download schema_report.json",
            data=st.session_state["schema_json"],
            file_name="schema_report.json",
            mime="application/json",
        )
