import streamlit as st
import json
import pandas as pd
from db import get_connection, query


def render():
    st.header("Database Schema Explorer")

    tab_schema, tab_brands, tab_diag = st.tabs(["Schema Report", "Brand / Item Mapping", "🔍 Diagnostics"])

    # ── Tab 1: full schema JSON dump ──────────────────────────────────────────
    with tab_schema:
        col1, col2 = st.columns([3, 1])
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

                    br = q("SELECT TOP 1 h.VoucherNo, h.TransTypeID FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID WHERE t.ShortName='BR' AND h.Cancelled<>'Y'")
                    if br and "ERROR" not in br[0]:
                        data["sample_BR_lines"] = q(f"SELECT * FROM TrVocDetail WHERE TransTypeID={br[0]['TransTypeID']} AND VoucherNo='{br[0]['VoucherNo']}'")

                    ms = q("SELECT TOP 1 h.VoucherNo, h.TransTypeID FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID WHERE t.ShortName='MS' AND h.Cancelled<>'Y'")
                    if ms and "ERROR" not in ms[0]:
                        data["sample_MS_lines"] = q(f"SELECT * FROM TrVocDetail WHERE TransTypeID={ms[0]['TransTypeID']} AND VoucherNo='{ms[0]['VoucherNo']}'")

                    conn.close()
                    st.session_state["schema_json"] = json.dumps(data, indent=2, default=str).encode()

                except Exception as e:
                    st.error(f"Error: {e}")

        if "schema_json" in st.session_state:
            st.success("Ready!")
            st.download_button(
                label="⬇️ Download schema_report.json",
                data=st.session_state["schema_json"],
                file_name="schema_report.json",
                mime="application/json",
            )

    # ── Tab 2: Brand / Item mapping dump ─────────────────────────────────────
    with tab_brands:
        st.subheader("All Brands & Items")
        st.caption("Fetch every brand and item from the database to review the principal mapping.")

        if st.button("Load Brands & Items", type="primary"):
            with st.spinner("Fetching..."):
                # All brands with total sales and bottles
                df_brands = query("""
                    SELECT
                        b.BrandID,
                        b.BrandName,
                        lt.LiquorType,
                        COUNT(DISTINCT i.ItemID)    AS item_count,
                        SUM(vi.TotalAmount)         AS total_sales,
                        SUM(vi.TotalBottleQty)      AS total_bottles
                    FROM MsBrandMaster b
                    LEFT JOIN MsItemMaster i  ON i.BrandID = b.BrandID
                    LEFT JOIN MsLiquorType lt ON lt.LiquorTypeID = i.LiquorTypeID
                    LEFT JOIN TrVocItem vi    ON vi.ItemID = i.ItemID
                    LEFT JOIN TrVocHead h     ON h.TransTypeID = vi.TransTypeID
                                             AND h.VoucherNo   = vi.VoucherNo
                                             AND ISNULL(h.Cancelled,'N') <> 'Y'
                                             AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                                             AND h.VoucherDate >= '2025-04-01'
                                             AND h.VoucherDate <  '2026-04-01'
                    GROUP BY b.BrandID, b.BrandName, lt.LiquorType
                    ORDER BY total_sales DESC
                """)

                # All items with brand, liquor type, size
                df_items = query("""
                    SELECT
                        i.ItemID,
                        i.ItemDescription,
                        b.BrandName,
                        lt.LiquorType,
                        st.SizeType,
                        i.MrpBottRate,
                        i.MrpCaseRate,
                        i.ImportedYN,
                        SUM(vi.TotalAmount)      AS total_sales,
                        SUM(vi.TotalBottleQty)   AS total_bottles
                    FROM MsItemMaster i
                    LEFT JOIN MsBrandMaster b  ON b.BrandID      = i.BrandID
                    LEFT JOIN MsLiquorType lt  ON lt.LiquorTypeID = i.LiquorTypeID
                    LEFT JOIN MsSizeType st    ON st.SizeTypeID   = i.SizeTypeID
                    LEFT JOIN TrVocItem vi     ON vi.ItemID = i.ItemID
                    LEFT JOIN TrVocHead h      ON h.TransTypeID = vi.TransTypeID
                                              AND h.VoucherNo   = vi.VoucherNo
                                              AND ISNULL(h.Cancelled,'N') <> 'Y'
                                              AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                                              AND h.VoucherDate >= '2025-04-01'
                                              AND h.VoucherDate <  '2026-04-01'
                    GROUP BY i.ItemID, i.ItemDescription, b.BrandName,
                             lt.LiquorType, st.SizeType, i.MrpBottRate,
                             i.MrpCaseRate, i.ImportedYN
                    ORDER BY total_sales DESC
                """)

                st.session_state["df_brands"] = df_brands
                st.session_state["df_items"]  = df_items

        if "df_brands" in st.session_state:
            df_brands = st.session_state["df_brands"]
            df_items  = st.session_state["df_items"]

            st.markdown(f"**{len(df_brands)} brands &nbsp;·&nbsp; {len(df_items)} items**")

            st.subheader("Brands")
            st.dataframe(df_brands, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download brands.csv",
                df_brands.to_csv(index=False).encode(),
                "brands.csv", "text/csv",
                key="dl_brands"
            )

            st.subheader("Items")
            st.dataframe(df_items, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download items.csv",
                df_items.to_csv(index=False).encode(),
                "items.csv", "text/csv",
                key="dl_items"
            )

    # ── Tab 3: Diagnostics ────────────────────────────────────────────────────
    with tab_diag:

        @st.fragment
        def _diag_panel():
            st.subheader("Live Diagnostics — FY 2025-26")
            st.caption("All queries scoped to 01-Apr-2025 → 31-Mar-2026. Results open in expandable sections.")

            DIAG_SECTIONS = [
                ("01 — All transaction types: ShortName + TrVocItem totals FY25-26", """
                    SELECT
                        t.ShortName, t.TransTypeName, t.id_key AS TransTypeID,
                        COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                        SUM(i.TotalAmount)    AS total_amount,
                        SUM(i.TotalBottleQty) AS total_bottles
                    FROM TrVocHead h
                    JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName, t.id_key
                    ORDER BY t.ShortName, total_amount DESC
                """),
                ("02 — MS sales total FY25-26 (TrVocItem)", """
                    SELECT
                        SUM(i.TotalAmount)    AS total_sales,
                        SUM(i.TotalBottleQty) AS total_bottles,
                        COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS invoices
                    FROM TrVocHead h
                    JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                """),
                ("03 — PU purchases total FY25-26 (TrVocItem, per type)", """
                    SELECT
                        t.id_key AS TransTypeID, t.TransTypeName,
                        COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                        SUM(i.TotalAmount)    AS total_amount,
                        SUM(i.TotalBottleQty) AS total_bottles
                    FROM TrVocHead h
                    JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.id_key, t.TransTypeName
                    ORDER BY total_amount DESC
                """),
                ("04 — LD (Load/Demo) TrVocItem + party breakdown FY25-26", """
                    SELECT
                        t.TransTypeName,
                        d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Creditor (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL/Blank'
                            ELSE 'Other'
                        END AS party_type,
                        COUNT(*) AS rows,
                        SUM(d.Amount) AS total_amount
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='LD'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.TransTypeName, d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Creditor (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL/Blank'
                            ELSE 'Other'
                        END
                    ORDER BY t.TransTypeName, d.DrCrIndicator, total_amount DESC
                """),
                ("05 — Top 50 brands by sales FY25-26 (via MsItemMaster)", """
                    SELECT TOP 50
                        m.BrandID,
                        b.BrandName,
                        SUM(i.TotalAmount)    AS sales,
                        SUM(i.TotalBottleQty) AS bottles
                    FROM TrVocHead h
                    JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY m.BrandID, b.BrandName
                    ORDER BY sales DESC
                """),
                ("06 — Items in MS invoices NOT in MsItemMaster (S-items etc.)", """
                    SELECT
                        i.ItemID,
                        h.TransTypeID,
                        t.TransTypeName,
                        COUNT(*) AS line_count,
                        SUM(i.TotalAmount) AS total_amount,
                        SUM(i.TotalBottleQty) AS total_bottles
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND NOT EXISTS (SELECT 1 FROM MsItemMaster m WHERE m.ItemID=i.ItemID)
                    GROUP BY i.ItemID, h.TransTypeID, t.TransTypeName
                    ORDER BY total_amount DESC
                """),
                ("07 — MsServiceItemMaster sample (S00xxx items)", """
                    SELECT TOP 30 * FROM MsServiceItemMaster ORDER BY 1
                """),
                ("08 — BP/CE TrVocItem: are these goods or payments? (party breakdown)", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Creditor (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL/Blank'
                            ELSE 'Other'
                        END AS party_type,
                        COUNT(*) AS rows,
                        SUM(d.Amount) AS total_amount
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName, d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Creditor (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL/Blank'
                            ELSE 'Other'
                        END
                    ORDER BY t.ShortName, d.DrCrIndicator, total_amount DESC
                """),
                ("09 — DN SALES summary: total charged to customers FY25-26", """
                    SELECT
                        COUNT(DISTINCT CAST(d.TransTypeID AS VARCHAR)+'|'+d.VoucherNo) AS vouchers,
                        SUM(CASE WHEN d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
                                 THEN d.Amount ELSE 0 END) AS charged_to_customers,
                        SUM(CASE WHEN d.DrCrIndicator='C' AND LEFT(d.PartyID,1)='C'
                                 THEN d.Amount ELSE 0 END) AS claimed_from_principals
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='DN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                """),
                ("10 — Debtors outstanding as on 31-Mar-2026 (MsPartyOpening)", """
                    SELECT
                        SUM(CloseBal)    AS total_closing_balance,
                        SUM(CloseBalTmp) AS total_running_balance,
                        COUNT(*)         AS customer_count
                    FROM MsPartyOpening
                    WHERE LEFT(PartyID,1)='D'
                """),
            ]
            import io, zipfile

            col_run, col_dl, col_clr = st.columns([2, 2, 1])
            with col_run:
                run_clicked = st.button("▶ Run Diagnostics", type="primary", use_container_width=True)
            with col_dl:
                if "diag_zip" in st.session_state:
                    st.download_button(
                        label="⬇️ Download Results (.zip)",
                        data=st.session_state["diag_zip"],
                        file_name="kwpl_diagnostics.zip",
                        mime="application/zip",
                        use_container_width=True,
                    )
                else:
                    st.button("⬇️ Download Results (.zip)", disabled=True, use_container_width=True)
            with col_clr:
                if st.button("🗑 Clear", use_container_width=True):
                    st.session_state.pop("diag_results", None)
                    st.session_state.pop("diag_zip", None)
                    st.rerun()

            if run_clicked:
                progress = st.progress(0, text="Starting…")
                results = {}
                for idx, (title, sql) in enumerate(DIAG_SECTIONS):
                    progress.progress((idx + 1) / len(DIAG_SECTIONS),
                                      text=f"Running {idx+1}/{len(DIAG_SECTIONS)}: {title[:40]}…")
                    try:
                        results[title] = query(sql)
                    except Exception as e:
                        results[title] = pd.DataFrame([{"ERROR": str(e)}])
                progress.empty()
                st.session_state["diag_results"] = results
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for title, df in results.items():
                        safe = title.replace(" ", "_").replace("—", "-")[:50]
                        zf.writestr(f"{safe}.csv", df.to_csv(index=False))
                st.session_state["diag_zip"] = buf.getvalue()
                st.rerun()

            if "diag_results" in st.session_state:
                st.divider()
                for title, df in st.session_state["diag_results"].items():
                    rows_label = f"{len(df)} rows" if len(df) > 1 else (
                        "ERROR" if "ERROR" in df.columns else "1 row"
                    )
                    with st.expander(f"{title}  —  {rows_label}", expanded=False):
                        st.dataframe(df, use_container_width=True, hide_index=True)

        _diag_panel()
