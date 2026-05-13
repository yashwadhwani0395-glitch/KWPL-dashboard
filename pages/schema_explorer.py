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
                                             AND h.Cancelled  <> 'Y'
                                             AND vi.FreeItemYN <> 'Y'
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
                                              AND h.Cancelled  <> 'Y'
                                              AND vi.FreeItemYN <> 'Y'
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
        st.subheader("Live Diagnostics — Collections / Sales / Outstanding")
        st.caption("Runs 8 targeted queries. Download all results as Excel for sharing.")

        DIAG_SECTIONS = [
            ("I — MS TransType breakdown (sales by type name)", """
                SELECT t.TransTypeName, t.ShortName, t.id_key AS TransTypeID,
                       COUNT(DISTINCT h.VoucherNo) AS vouchers,
                       SUM(i.TotalAmount)           AS total_amount,
                       MIN(h.VoucherDate)           AS earliest,
                       MAX(h.VoucherDate)           AS latest
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                GROUP BY t.TransTypeName, t.ShortName, t.id_key
                ORDER BY total_amount DESC
            """),
            ("J — MS top 20 parties on DEBIT side (who are the customers?)", """
                SELECT TOP 20 p.PartyName, p.PartyID,
                       COUNT(DISTINCT h.VoucherNo) AS invoices,
                       SUM(d.Amount)               AS total_amount
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND d.DrCrIndicator='D'
                  AND d.PartyID IS NOT NULL
                GROUP BY p.PartyName, p.PartyID
                ORDER BY total_amount DESC
            """),
            ("K — MS FY25-26 total by TransTypeID (to find retail-only type)", """
                SELECT t.id_key AS TransTypeID, t.TransTypeName,
                       COUNT(DISTINCT h.VoucherNo) AS vouchers,
                       SUM(i.TotalAmount)           AS total_amount
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <= '2026-03-31'
                GROUP BY t.id_key, t.TransTypeName
                ORDER BY total_amount DESC
            """),
            ("A — TrVocDetail columns", """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='TrVocDetail'
                ORDER BY ORDINAL_POSITION
            """),
            ("B — Sample BR receipt (TrVocDetail, all columns)", """
                SELECT TOP 20 d.*
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='BR'
                ORDER BY h.VoucherDate DESC
            """),
            ("C — Collections by DrCrIndicator (BR+CR, all time)", """
                SELECT
                    d.DrCrIndicator,
                    COUNT(*)                  AS rows,
                    SUM(d.Amount)             AS total_amount,
                    COUNT(DISTINCT d.PartyID) AS distinct_parties
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName IN ('BR','CR')
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                GROUP BY d.DrCrIndicator
            """),
            ("D — Collections FY 2025-26 by DrCrIndicator", """
                SELECT
                    d.DrCrIndicator,
                    SUM(d.Amount) AS total_amount,
                    COUNT(*)      AS rows
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName IN ('BR','CR')
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <= '2026-03-31'
                GROUP BY d.DrCrIndicator
            """),
            ("E — Sales total: All Time vs FY 2025-26", """
                SELECT 'All Time' AS period,
                    SUM(i.TotalAmount)          AS sales,
                    COUNT(DISTINCT h.VoucherNo) AS vouchers_distinct,
                    COUNT(*)                    AS voucher_rows,
                    MIN(h.VoucherDate)          AS earliest,
                    MAX(h.VoucherDate)          AS latest
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                UNION ALL
                SELECT 'FY 2025-26' AS period,
                    SUM(i.TotalAmount)          AS sales,
                    COUNT(DISTINCT h.VoucherNo) AS vouchers_distinct,
                    COUNT(*)                    AS voucher_rows,
                    MIN(h.VoucherDate)          AS earliest,
                    MAX(h.VoucherDate)          AS latest
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <= '2026-03-31'
            """),
            ("F — RemainingAmt summary (entire TrVocDetail)", """
                SELECT
                    SUM(CASE WHEN d.RemainingAmt > 0   THEN 1 ELSE 0 END) AS rows_with_remaining,
                    SUM(CASE WHEN d.RemainingAmt > 0   THEN d.RemainingAmt ELSE 0 END) AS total_remaining,
                    SUM(CASE WHEN d.RemainingAmt IS NULL THEN 1 ELSE 0 END) AS null_rows,
                    COUNT(*) AS total_rows
                FROM TrVocDetail d
            """),
            ("G — Outstanding: MS + DrCr=D + RemainingAmt > 0", """
                SELECT
                    COUNT(*)                  AS open_lines,
                    COUNT(DISTINCT d.PartyID) AS debtors,
                    SUM(d.RemainingAmt)       AS total_outstanding,
                    MIN(h.VoucherDate)        AS oldest_invoice,
                    MAX(h.VoucherDate)        AS newest_invoice
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND d.DrCrIndicator='D'
                  AND d.RemainingAmt > 0
                  AND d.PartyID IS NOT NULL
            """),
            ("H — Sample MS detail rows (VoucherDate, DrCr, Amount, RemainingAmt, Party)", """
                SELECT TOP 30
                    h.VoucherDate, d.DrCrIndicator, d.Amount, d.RemainingAmt,
                    d.PartyID, p.PartyName
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                ORDER BY h.VoucherDate DESC
            """),
        ]

        import io, zipfile

        col_run, col_dl = st.columns([1, 1])

        with col_run:
            run_clicked = st.button("▶ Run Diagnostics", type="primary", use_container_width=True)

        with col_dl:
            if "diag_results" in st.session_state:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for title, df in st.session_state["diag_results"].items():
                        safe = title.replace(" ", "_").replace("—", "-")[:50]
                        zf.writestr(f"{safe}.csv", df.to_csv(index=False))
                st.download_button(
                    label="⬇️ Download Results (.zip)",
                    data=buf.getvalue(),
                    file_name="kwpl_diagnostics.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            else:
                st.button("⬇️ Download Results (.zip)", disabled=True, use_container_width=True)

        if run_clicked:
            with st.spinner("Running 8 queries…"):
                results = {}
                for title, sql in DIAG_SECTIONS:
                    try:
                        results[title] = query(sql)
                    except Exception as e:
                        results[title] = pd.DataFrame([{"ERROR": str(e)}])
                st.session_state["diag_results"] = results
                st.rerun()

        if "diag_results" in st.session_state:
            st.divider()
            for title, df in st.session_state["diag_results"].items():
                st.markdown(f"### {title}")
                st.dataframe(df, use_container_width=True, hide_index=True)
