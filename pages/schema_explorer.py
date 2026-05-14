import streamlit as st
import json
import pandas as pd
from db import get_connection, query


def render():
    st.header("Database Schema Explorer")

    tab_survey, tab_brands, tab_diag = st.tabs(["📋 Full Schema Survey", "Brand / Item Mapping", "🔍 Diagnostics"])

    # ── Tab 1: Full Schema Survey ─────────────────────────────────────────────
    # Auto-discovers every table, row counts, all columns, TOP 5 sample rows.
    # Downloads as a ZIP (one CSV per table for columns, one for samples).
    with tab_survey:
        st.markdown(
            "Discovers **every table** in the ERP database: row counts, column types, "
            "and sample rows. Use this to map the full schema before writing any queries."
        )

        col_btn, col_dl, _ = st.columns([2, 2, 3])
        with col_btn:
            run_survey = st.button("▶ Run Full Survey", type="primary", use_container_width=True)
        with col_dl:
            if "survey_zip" in st.session_state:
                st.download_button(
                    "⬇️ Download Survey (.zip)",
                    data=st.session_state["survey_zip"],
                    file_name="kwpl_full_schema_survey.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            else:
                st.button("⬇️ Download Survey (.zip)", disabled=True, use_container_width=True)

        if run_survey:
            import io, zipfile as zf
            progress = st.progress(0, text="Discovering tables…")
            try:
                conn = get_connection()
                cur  = conn.cursor(as_dict=True)

                def _q(sql):
                    try:
                        cur.execute(sql)
                        return cur.fetchall() or []
                    except Exception as e:
                        return [{"ERROR": str(e)}]

                # ── Step 1: all tables ────────────────────────────────────────
                tables_raw = _q(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
                )
                tables = [r["TABLE_NAME"] for r in tables_raw if "ERROR" not in r]
                progress.progress(0.05, text=f"Found {len(tables)} tables. Fetching row counts…")

                # ── Step 2: row counts for every table ───────────────────────
                row_counts = {}
                for i, tbl in enumerate(tables):
                    rc = _q(f"SELECT COUNT(*) AS n FROM [{tbl}]")
                    row_counts[tbl] = rc[0].get("n", 0) if rc and "ERROR" not in rc[0] else "ERR"
                    progress.progress(0.05 + 0.30 * (i + 1) / len(tables),
                                      text=f"Row counts: {tbl}")

                # ── Step 3: columns for every table ──────────────────────────
                all_columns = {}
                for i, tbl in enumerate(tables):
                    cols = _q(
                        f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, "
                        f"NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE "
                        f"FROM INFORMATION_SCHEMA.COLUMNS "
                        f"WHERE TABLE_NAME='{tbl}' ORDER BY ORDINAL_POSITION"
                    )
                    all_columns[tbl] = cols
                    progress.progress(0.35 + 0.30 * (i + 1) / len(tables),
                                      text=f"Columns: {tbl}")

                # ── Step 4: TOP 5 sample rows for every table ─────────────────
                all_samples = {}
                for i, tbl in enumerate(tables):
                    rows = _q(f"SELECT TOP 5 * FROM [{tbl}]")
                    all_samples[tbl] = rows
                    progress.progress(0.65 + 0.30 * (i + 1) / len(tables),
                                      text=f"Samples: {tbl}")

                # ── Step 5: FK relationships ──────────────────────────────────
                fks = _q("""
                    SELECT
                        fk.name                              AS fk_name,
                        tp.name                              AS parent_table,
                        cp.name                              AS parent_column,
                        tr.name                              AS ref_table,
                        cr.name                              AS ref_column
                    FROM sys.foreign_keys fk
                    JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
                    JOIN sys.tables  tp ON tp.object_id = fkc.parent_object_id
                    JOIN sys.columns cp ON cp.object_id = fkc.parent_object_id
                                       AND cp.column_id = fkc.parent_column_id
                    JOIN sys.tables  tr ON tr.object_id = fkc.referenced_object_id
                    JOIN sys.columns cr ON cr.object_id = fkc.referenced_object_id
                                       AND cr.column_id = fkc.referenced_column_id
                    ORDER BY tp.name, fk.name
                """)

                conn.close()
                progress.progress(0.97, text="Building ZIP…")

                # ── Build ZIP ────────────────────────────────────────────────
                buf = io.BytesIO()
                with zf.ZipFile(buf, "w", zf.ZIP_DEFLATED) as z:
                    # Summary: table name + row count
                    summary_rows = [{"table": t, "row_count": row_counts.get(t, "?")}
                                    for t in tables]
                    z.writestr("_summary.csv",
                               pd.DataFrame(summary_rows).to_csv(index=False))

                    # FK relationships
                    if fks and "ERROR" not in fks[0]:
                        z.writestr("_foreign_keys.csv",
                                   pd.DataFrame(fks).to_csv(index=False))

                    # Per-table: columns + samples
                    for tbl in tables:
                        cols = all_columns.get(tbl, [])
                        if cols and "ERROR" not in cols[0]:
                            z.writestr(f"{tbl}__columns.csv",
                                       pd.DataFrame(cols).to_csv(index=False))
                        samp = all_samples.get(tbl, [])
                        if samp and "ERROR" not in samp[0]:
                            z.writestr(f"{tbl}__sample.csv",
                                       pd.DataFrame(samp).to_csv(index=False))

                buf.seek(0)
                st.session_state["survey_zip"]     = buf.getvalue()
                st.session_state["survey_tables"]  = tables
                st.session_state["survey_counts"]  = row_counts
                st.session_state["survey_columns"] = all_columns
                st.session_state["survey_samples"] = all_samples
                st.session_state["survey_fks"]     = fks

                progress.progress(1.0, text="Done.")
                st.rerun()

            except Exception as e:
                st.error(f"Survey failed: {e}")

        # ── Display results ───────────────────────────────────────────────────
        if "survey_tables" in st.session_state:
            tables      = st.session_state["survey_tables"]
            row_counts  = st.session_state["survey_counts"]
            all_columns = st.session_state["survey_columns"]
            all_samples = st.session_state["survey_samples"]
            fks         = st.session_state["survey_fks"]

            # Summary table
            st.subheader(f"All Tables ({len(tables)} found)")
            df_sum = pd.DataFrame([
                {"Table": t, "Rows": row_counts.get(t, "?"),
                 "Prefix": t[:2] if len(t) >= 2 else t}
                for t in tables
            ])
            df_sum = df_sum.sort_values("Rows", ascending=False, key=lambda x: pd.to_numeric(x, errors="coerce"))
            st.dataframe(df_sum[["Table", "Rows", "Prefix"]], use_container_width=True, hide_index=True)

            st.divider()

            # FK map
            if fks and "ERROR" not in fks[0]:
                with st.expander("Foreign Key Relationships"):
                    st.dataframe(pd.DataFrame(fks), use_container_width=True, hide_index=True)

            st.divider()

            # Per-table drill-down
            st.subheader("Table Detail")
            selected = st.selectbox(
                "Select a table to inspect",
                options=tables,
                format_func=lambda t: f"{t}  ({row_counts.get(t, '?')} rows)"
            )
            if selected:
                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown(f"**Columns — {selected}**")
                    cols = all_columns.get(selected, [])
                    if cols and "ERROR" not in cols[0]:
                        st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)
                    else:
                        st.warning("No column data.")
                with col_r:
                    st.markdown(f"**Sample rows (TOP 5) — {selected}**")
                    samp = all_samples.get(selected, [])
                    if samp and "ERROR" not in samp[0]:
                        st.dataframe(pd.DataFrame(samp), use_container_width=True, hide_index=True)
                    else:
                        st.info("No rows / error.")

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
                ("11 — Items in PURCHASE JD (TransTypeID=53) via MsItemMaster: BrandIDs", """
                    SELECT TOP 30
                        i.ItemID,
                        m.BrandID,
                        b.BrandName,
                        i.ItemDescription,
                        SUM(vi.TotalAmount)    AS total_amount,
                        SUM(vi.TotalBottleQty) AS total_bottles
                    FROM TrVocItem vi
                    JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    LEFT JOIN MsItemMaster m ON m.ItemID=vi.ItemID
                    LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    LEFT JOIN MsItemMaster i ON i.ItemID=vi.ItemID
                    WHERE vi.TransTypeID=53
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY i.ItemID, m.BrandID, b.BrandName, i.ItemDescription
                    ORDER BY total_amount DESC
                """),
                ("12 — Find Jack Daniels / Brown Forman in MsItemMaster by description", """
                    SELECT i.ItemID, i.ItemDescription, i.BrandID, b.BrandName,
                           b.CompanyID, p.PartyName AS principal
                    FROM MsItemMaster i
                    LEFT JOIN MsBrandMaster b ON b.BrandID=i.BrandID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
                    WHERE i.ItemDescription LIKE 'JACK%'
                       OR i.ItemDescription LIKE '%JACK DANIEL%'
                       OR i.ItemDescription LIKE '%WOODFORD%'
                       OR i.ItemDescription LIKE '%GLEN DRONACH%'
                       OR i.ItemDescription LIKE '%GLENDRONACH%'
                    ORDER BY i.BrandID
                """),
                ("13 — ALL MS TrVocItem: total that joins vs drops MsItemMaster FY25-26", """
                    SELECT
                        'Joined MsItemMaster'  AS status,
                        COUNT(*)               AS line_count,
                        SUM(vi.TotalAmount)    AS total_amount,
                        SUM(vi.TotalBottleQty) AS total_bottles
                    FROM TrVocItem vi
                    JOIN TrVocHead h   ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=vi.ItemID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    UNION ALL
                    SELECT
                        'No MsItemMaster match' AS status,
                        COUNT(*),
                        SUM(vi.TotalAmount),
                        SUM(vi.TotalBottleQty)
                    FROM TrVocItem vi
                    JOIN TrVocHead h   ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND NOT EXISTS (SELECT 1 FROM MsItemMaster mx WHERE mx.ItemID=vi.ItemID)
                """),
                ("14 — LD LOAD (TransTypeID=39): top brands via MsItemMaster FY25-26", """
                    SELECT TOP 30
                        m.BrandID,
                        b.BrandName,
                        COUNT(DISTINCT CAST(vi.TransTypeID AS VARCHAR)+'|'+vi.VoucherNo) AS vouchers,
                        SUM(vi.TotalAmount)    AS total_amount,
                        SUM(vi.TotalBottleQty) AS total_bottles
                    FROM TrVocItem vi
                    JOIN TrVocHead h   ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    JOIN MsItemMaster m ON m.ItemID=vi.ItemID
                    LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE vi.TransTypeID=39
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY m.BrandID, b.BrandName
                    ORDER BY total_amount DESC
                """),
                ("16 — BF (JD/Woodford/GlenDronach) sales across ALL transaction types FY25-26", """
                    SELECT
                        t.ShortName, t.TransTypeName, t.id_key AS TransTypeID,
                        b.BrandName,
                        SUM(vi.TotalAmount)    AS total_amount,
                        SUM(vi.TotalBottleQty) AS total_bottles,
                        COUNT(*)               AS lines
                    FROM TrVocItem vi
                    JOIN TrVocHead h    ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=vi.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE m.BrandID IN (576,577,578,579,580,583,585,588,592)
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName, t.id_key, b.BrandName
                    ORDER BY t.ShortName, total_amount DESC
                """),
                ("17 — BP + CE TrVocItem by principal (excise on which brands?) FY25-26", """
                    SELECT TOP 30
                        t.ShortName, t.TransTypeName,
                        CASE
                            WHEN m.BrandID IN (277,278,279,284,286,292,293,294,295,296,
                                297,305,342,345,346,371,372,373,375,376,379,388,396,401,
                                417,437,445,458,568,266,269,270,271,273,274,275,276,353,
                                354,355,356,368,419,432,561,563,565,287,382,394,522,523,
                                282,283,288,289,290,298,330,335,389,428,429,433,446,390,
                                391,392,434,435,436,535,280,481,542,567,285,380,430,475,
                                476,541,560,224,281,291,381,463,464,482,589,590,593)
                                THEN 'Diageo'
                            WHEN m.BrandID IN (213,217,223,555,556,559,569,570,582,591,
                                594,218,360,323,487,90,110,450,215,225,331,332,272,333,
                                358,265,267,334,477)
                                THEN 'United Spirits'
                            WHEN m.BrandID IN (78,80,109,126,189,329,483,486,557,586,595,
                                84,112,214,327,344,378,479,478,573,574,571,572,38,219,
                                448,552,566,443,558,77,554)
                                THEN 'United Breweries'
                            WHEN m.BrandID IN (576,577,578,579,580,583,585,588,592)
                                THEN 'Brown-Forman'
                            ELSE 'Others'
                        END AS principal,
                        SUM(vi.TotalAmount)    AS excise_amount,
                        SUM(vi.TotalBottleQty) AS bottles
                    FROM TrVocItem vi
                    JOIN TrVocHead h    ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=vi.ItemID
                    WHERE h.TransTypeID IN (40,18)
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName, CASE
                            WHEN m.BrandID IN (277,278,279,284,286,292,293,294,295,296,
                                297,305,342,345,346,371,372,373,375,376,379,388,396,401,
                                417,437,445,458,568,266,269,270,271,273,274,275,276,353,
                                354,355,356,368,419,432,561,563,565,287,382,394,522,523,
                                282,283,288,289,290,298,330,335,389,428,429,433,446,390,
                                391,392,434,435,436,535,280,481,542,567,285,380,430,475,
                                476,541,560,224,281,291,381,463,464,482,589,590,593)
                                THEN 'Diageo'
                            WHEN m.BrandID IN (213,217,223,555,556,559,569,570,582,591,
                                594,218,360,323,487,90,110,450,215,225,331,332,272,333,
                                358,265,267,334,477)
                                THEN 'United Spirits'
                            WHEN m.BrandID IN (78,80,109,126,189,329,483,486,557,586,595,
                                84,112,214,327,344,378,479,478,573,574,571,572,38,219,
                                448,552,566,443,558,77,554)
                                THEN 'United Breweries'
                            WHEN m.BrandID IN (576,577,578,579,580,583,585,588,592)
                                THEN 'Brown-Forman'
                            ELSE 'Others'
                        END
                    ORDER BY excise_amount DESC
                """),
                ("18 — RO (Receipt Order) party breakdown: what does it DR/CR?", """
                    SELECT
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
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    WHERE h.TransTypeID=54
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Creditor (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL/Blank'
                            ELSE 'Other'
                        END
                    ORDER BY d.DrCrIndicator, total_amount DESC
                """),
                ("19 — ALL TransTypes that DR Customer D% accounts (complete outward billing picture)", """
                    SELECT
                        t.ShortName, t.TransTypeName, t.id_key AS TransTypeID,
                        SUM(d.Amount)  AS dr_to_customers,
                        COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='D'
                      AND LEFT(d.PartyID,1)='D'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName, t.id_key
                    ORDER BY dr_to_customers DESC
                """),
                ("20 — Principal-wise total billing to customers across ALL transaction types FY25-26", """
                    SELECT principal, SUM(total_amount) AS total_billed, SUM(total_bottles) AS bottles
                    FROM (
                        SELECT
                            CASE
                                WHEN m.BrandID IN (277,278,279,284,286,292,293,294,295,296,
                                    297,305,342,345,346,371,372,373,375,376,379,388,396,401,
                                    417,437,445,458,568,266,269,270,271,273,274,275,276,353,
                                    354,355,356,368,419,432,561,563,565,287,382,394,522,523,
                                    282,283,288,289,290,298,330,335,389,428,429,433,446,390,
                                    391,392,434,435,436,535,280,481,542,567,285,380,430,475,
                                    476,541,560,224,281,291,381,463,464,482,589,590,593)
                                    THEN 'Diageo'
                                WHEN m.BrandID IN (213,217,223,555,556,559,569,570,582,591,
                                    594,218,360,323,487,90,110,450,215,225,331,332,272,333,
                                    358,265,267,334,477)
                                    THEN 'United Spirits'
                                WHEN m.BrandID IN (78,80,109,126,189,329,483,486,557,586,595,
                                    84,112,214,327,344,378,479,478,573,574,571,572,38,219,
                                    448,552,566,443,558,77,554)
                                    THEN 'United Breweries'
                                WHEN m.BrandID IN (576,577,578,579,580,583,585,588,592)
                                    THEN 'Brown-Forman'
                                ELSE 'Others'
                            END AS principal,
                            vi.TotalAmount AS total_amount,
                            vi.TotalBottleQty AS total_bottles
                        FROM TrVocItem vi
                        JOIN TrVocHead h    ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                        JOIN MsItemMaster m ON m.ItemID=vi.ItemID
                        WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                          AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                          AND h.VoucherDate >= '2025-04-01'
                          AND h.VoucherDate <  '2026-04-01'
                    ) x
                    GROUP BY principal
                    ORDER BY total_billed DESC
                """),
                ("21 — Complete sales picture by TransType: which types DR customers AND have TrVocItem?", """
                    SELECT
                        t.ShortName, t.TransTypeName, t.id_key AS TransTypeID,
                        SUM(vi.TotalAmount)    AS item_total,
                        SUM(vi.TotalBottleQty) AS item_bottles,
                        COUNT(DISTINCT CAST(vi.TransTypeID AS VARCHAR)+'|'+vi.VoucherNo) AS vouchers
                    FROM TrVocItem vi
                    JOIN TrVocHead h   ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(vi.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND EXISTS (
                          SELECT 1 FROM TrVocDetail d2
                          WHERE d2.TransTypeID=h.TransTypeID AND d2.VoucherNo=h.VoucherNo
                            AND d2.DrCrIndicator='D' AND LEFT(d2.PartyID,1)='D'
                      )
                    GROUP BY t.ShortName, t.TransTypeName, t.id_key
                    ORDER BY item_total DESC
                """),
                ("22 — DN (Debit Note) full accounting breakdown: what exactly does each DR/CR?", """
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
                    WHERE t.ShortName='DN'
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
                    ORDER BY t.TransTypeName, d.DrCrIndicator, total_amount DESC
                """),
                ("15 — LD LOAD party breakdown: does it debit customers (= customer billing)?", """
                    SELECT
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
                    WHERE h.TransTypeID=39
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Creditor (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL/Blank'
                            ELSE 'Other'
                        END
                    ORDER BY d.DrCrIndicator, total_amount DESC
                """),
                ("23 — TrVocHead: all column names (find TP No + TP Date fields)", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'TrVocHead'
                    ORDER BY ORDINAL_POSITION
                """),
                ("24 — TrVocHead sample: VoucherNo vs TP fields on MS invoices (spot Voucher vs TP date gap)", """
                    SELECT TOP 30 *
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    ORDER BY h.VoucherDate DESC
                """),
                ("26 — BR/CR voucher both sides: what DR/CR entries exist? (find correct collections query)", """
                    SELECT TOP 5
                        h.VoucherNo,
                        CAST(h.VoucherDate AS DATE) AS vdate,
                        d.DrCrIndicator,
                        d.PartyID,
                        LEFT(d.PartyID,1) AS party_prefix,
                        d.Amount,
                        d.Narration
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BR'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo, d.DrCrIndicator
                """),
                ("25 — Any separate TP / Transport Permit tables in the database?", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (
                          TABLE_NAME LIKE '%TP%'
                       OR TABLE_NAME LIKE '%Transport%'
                       OR TABLE_NAME LIKE '%Permit%'
                       OR TABLE_NAME LIKE '%Dispatch%'
                       OR TABLE_NAME LIKE '%Challan%'
                       OR TABLE_NAME LIKE '%Batch%'
                      )
                    ORDER BY TABLE_NAME
                """),
                ("27 — ALL account prefixes in TrVocDetail: full universe of account types FY25-26", """
                    SELECT
                        LEFT(d.PartyID,1)  AS prefix,
                        LEFT(d.PartyID,3)  AS sample_prefix,
                        d.DrCrIndicator,
                        COUNT(*)           AS rows,
                        SUM(d.Amount)      AS total_amount,
                        MIN(d.PartyID)     AS sample_id_min,
                        MAX(d.PartyID)     AS sample_id_max
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY LEFT(d.PartyID,1), LEFT(d.PartyID,3), d.DrCrIndicator
                    ORDER BY total_amount DESC
                """),
                ("28 — Full double-entry for ONE MS sales voucher (both DR and CR sides)", """
                    SELECT
                        d.DrCrIndicator,
                        d.PartyID,
                        LEFT(d.PartyID,1)  AS prefix,
                        p.PartyName,
                        d.Amount,
                        d.Narration
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND h.VoucherNo IN (
                          SELECT TOP 1 h2.VoucherNo
                          FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='MS'
                            AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                            AND h2.VoucherDate <  '2026-04-01'
                          ORDER BY h2.VoucherDate, h2.VoucherNo
                      )
                    ORDER BY d.DrCrIndicator, d.Amount DESC
                """),
                ("29 — Full double-entry for ONE PU purchase voucher (both DR and CR sides)", """
                    SELECT
                        d.DrCrIndicator,
                        d.PartyID,
                        LEFT(d.PartyID,1)  AS prefix,
                        p.PartyName,
                        d.Amount,
                        d.Narration
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND h.VoucherNo IN (
                          SELECT TOP 1 h2.VoucherNo
                          FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='PU'
                            AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                            AND h2.VoucherDate <  '2026-04-01'
                          ORDER BY h2.VoucherDate, h2.VoucherNo
                      )
                    ORDER BY d.DrCrIndicator, d.Amount DESC
                """),
                ("30 — What accounts get CREDITED in MS/LD/PU53 outward vouchers? (the revenue-side accounts)", """
                    SELECT
                        t.ShortName,
                        LEFT(d.PartyID,1)  AS cr_prefix,
                        LEFT(d.PartyID,4)  AS cr_sample,
                        p.PartyName        AS account_name,
                        COUNT(*)           AS rows,
                        SUM(d.Amount)      AS total_credited
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('MS','LD')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='C'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, LEFT(d.PartyID,1), LEFT(d.PartyID,4), p.PartyName
                    ORDER BY total_credited DESC
                """),
                ("31 — What accounts get DEBITED in PU/BP/CE inward vouchers? (the purchase-side accounts)", """
                    SELECT
                        t.ShortName,
                        LEFT(d.PartyID,1)  AS dr_prefix,
                        LEFT(d.PartyID,4)  AS dr_sample,
                        p.PartyName        AS account_name,
                        COUNT(*)           AS rows,
                        SUM(d.Amount)      AS total_debited
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('PU','BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='D'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, LEFT(d.PartyID,1), LEFT(d.PartyID,4), p.PartyName
                    ORDER BY total_debited DESC
                """),
                ("32 — Invoice count: distinct TPNo vs VoucherNo for all outward vouchers FY25-26", """
                    SELECT
                        t.ShortName,
                        t.TransTypeName,
                        COUNT(DISTINCT h.VoucherNo)                   AS distinct_voucher_nos,
                        COUNT(DISTINCT NULLIF(CAST(h.TPNo AS VARCHAR),'0'))  AS distinct_tp_nos,
                        COUNT(DISTINCT h.InvoiceNo)                   AS distinct_invoice_nos,
                        MIN(CAST(h.VoucherDate AS DATE))              AS earliest,
                        MAX(CAST(h.VoucherDate AS DATE))              AS latest
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName
                    ORDER BY distinct_voucher_nos DESC
                """),
                ("33 — MsPartyMaster: all distinct PartyID prefixes and counts (full account type list)", """
                    SELECT
                        LEFT(PartyID,1)  AS prefix,
                        COUNT(*)         AS party_count,
                        MIN(PartyID)     AS sample_min,
                        MAX(PartyID)     AS sample_max,
                        MIN(PartyName)   AS sample_name_1,
                        MAX(PartyName)   AS sample_name_2
                    FROM MsPartyMaster
                    GROUP BY LEFT(PartyID,1)
                    ORDER BY party_count DESC
                """),
                ("34 — MsAccountHead: full account hierarchy (GL account types)", """
                    SELECT * FROM MsAccountHead ORDER BY 1
                """),
                ("35 — CR side of ALL BR/CR receipts: which accounts are credited?", """
                    SELECT
                        t.ShortName,
                        LEFT(d.PartyID,1)  AS prefix,
                        LEFT(d.PartyID,4)  AS sample,
                        p.PartyName        AS account_name,
                        COUNT(*)           AS rows,
                        SUM(d.Amount)      AS total_amount
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BR','CR')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='C'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, LEFT(d.PartyID,1), LEFT(d.PartyID,4), p.PartyName
                    ORDER BY total_amount DESC
                """),

                # ── BLOCK A: BP/CE — excise-on-goods vs expense vouchers ─────────────
                ("36 — BP/CE WITH product lines (excise duty on goods): account breakdown", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        d.DrCrIndicator,
                        LEFT(d.PartyID,1)               AS party_prefix,
                        ISNULL(p.PartyName, d.PartyID)  AS account_name,
                        COUNT(*)                         AS rows,
                        SUM(d.Amount)                    AS total
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND EXISTS (
                          SELECT 1 FROM TrVocItem vi
                          WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo
                      )
                    GROUP BY t.ShortName, t.TransTypeName, d.DrCrIndicator,
                             LEFT(d.PartyID,1), ISNULL(p.PartyName, d.PartyID)
                    ORDER BY t.ShortName, d.DrCrIndicator, total DESC
                """),
                ("37 — BP/CE WITHOUT product lines (pure expense payments): account breakdown", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        d.DrCrIndicator,
                        LEFT(d.PartyID,1)               AS party_prefix,
                        ISNULL(p.PartyName, d.PartyID)  AS account_name,
                        COUNT(*)                         AS rows,
                        SUM(d.Amount)                    AS total
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND NOT EXISTS (
                          SELECT 1 FROM TrVocItem vi
                          WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo
                      )
                    GROUP BY t.ShortName, t.TransTypeName, d.DrCrIndicator,
                             LEFT(d.PartyID,1), ISNULL(p.PartyName, d.PartyID)
                    ORDER BY t.ShortName, d.DrCrIndicator, total DESC
                """),
                ("38 — Sample expense BP/CE voucher (no product lines): full detail lines", """
                    SELECT TOP 20
                        h.VoucherDate, h.VoucherNo, t.ShortName, t.TransTypeName,
                        h.Narration,
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        d.Amount
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND NOT EXISTS (
                          SELECT 1 FROM TrVocItem vi
                          WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo
                      )
                    ORDER BY h.VoucherDate DESC, h.VoucherNo
                """),

                # ── BLOCK B: VoucherFlag values ───────────────────────────────────────
                ("39 — VoucherFlag: all distinct values, counts, and date ranges", """
                    SELECT
                        CASE WHEN VoucherFlag IS NULL THEN 'NULL'
                             WHEN VoucherFlag = ''    THEN 'EMPTY'
                             ELSE VoucherFlag
                        END                         AS flag_value,
                        t.ShortName,
                        COUNT(*)                    AS vouchers,
                        MIN(CAST(h.VoucherDate AS DATE)) AS earliest,
                        MAX(CAST(h.VoucherDate AS DATE)) AS latest,
                        MIN(h.VoucherNo)            AS sample_voucher
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY
                        CASE WHEN VoucherFlag IS NULL THEN 'NULL'
                             WHEN VoucherFlag = ''    THEN 'EMPTY'
                             ELSE VoucherFlag END,
                        t.ShortName
                    ORDER BY vouchers DESC
                """),
                ("40 — VoucherFlag: sample voucher detail for each non-empty flag", """
                    SELECT TOP 30
                        h.VoucherFlag, h.VoucherNo, h.VoucherDate,
                        t.ShortName, t.TransTypeName,
                        h.Narration,
                        h.Cancelled
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND h.VoucherFlag NOT IN ('', ' ')
                      AND h.VoucherFlag IS NOT NULL
                    ORDER BY h.VoucherFlag, h.VoucherDate DESC
                """),

                # ── BLOCK C: MsItemBatchOpening — opening stock ───────────────────────
                ("41 — MsItemBatchOpening: all columns and data types", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'MsItemBatchOpening'
                    ORDER BY ORDINAL_POSITION
                """),
                ("42 — MsItemBatchOpening: row count, distinct items, total qty and MRP value", """
                    SELECT
                        COUNT(*)                             AS total_rows,
                        COUNT(DISTINCT o.ItemID)             AS distinct_items,
                        SUM(o.OpeningQty)                    AS total_opening_qty,
                        SUM(o.OpeningQty * m.MrpBottRate)    AS opening_mrp_value,
                        MIN(o.OpeningQty)                    AS min_qty,
                        MAX(o.OpeningQty)                    AS max_qty
                    FROM MsItemBatchOpening o
                    JOIN MsItemMaster m ON m.ItemID = o.ItemID
                """),
                ("43 — MsItemBatchOpening: top 20 items by opening qty", """
                    SELECT TOP 20
                        m.ItemDescription, b.BrandName,
                        SUM(o.OpeningQty)                    AS opening_bottles,
                        SUM(o.OpeningQty * m.MrpBottRate)    AS mrp_value
                    FROM MsItemBatchOpening o
                    JOIN MsItemMaster m   ON m.ItemID   = o.ItemID
                    JOIN MsBrandMaster b  ON b.BrandID  = m.BrandID
                    GROUP BY m.ItemDescription, b.BrandName
                    ORDER BY opening_bottles DESC
                """),

                # ── BLOCK D: CN/DN — credit notes and debit notes ─────────────────────
                ("44 — CN/DN: DR/CR breakdown by party type — who are they between?", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Supplier (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL / No party'
                            ELSE 'Other: ' + LEFT(d.PartyID,2)
                        END                           AS party_type,
                        COUNT(*)                      AS rows,
                        SUM(d.Amount)                 AS total,
                        COUNT(DISTINCT d.VoucherNo)   AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName IN ('CN','DN')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName, d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Supplier (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL / No party'
                            ELSE 'Other: ' + LEFT(d.PartyID,2)
                        END
                    ORDER BY t.ShortName, total DESC
                """),
                ("45 — CN/DN: do they carry product lines (TrVocItem)?", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        COUNT(DISTINCT h.VoucherNo)    AS total_vouchers,
                        SUM(CASE WHEN vi.VoucherNo IS NOT NULL THEN 1 ELSE 0 END) AS vouchers_with_items,
                        SUM(vi.TotalAmount)             AS item_total_amount,
                        SUM(vi.TotalBottleQty)          AS item_total_bottles
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrVocItem vi ON vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo
                    WHERE t.ShortName IN ('CN','DN')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName
                """),
                ("46 — CN/DN: sample voucher — full header + detail + items for one CN and one DN", """
                    SELECT
                        h.VoucherDate, h.VoucherNo, t.ShortName,
                        h.Narration,
                        'DETAIL'                           AS line_type,
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, d.PartyID)     AS account,
                        d.Amount,
                        NULL                               AS item_desc,
                        NULL                               AS bottles
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE h.VoucherNo IN (
                        SELECT TOP 1 VoucherNo FROM TrVocHead hh
                        JOIN MsTransType tt ON tt.id_key=hh.TransTypeID
                        WHERE tt.ShortName='CN' AND ISNULL(hh.Cancelled,'N')<>'Y'
                          AND hh.VoucherDate >= '2025-04-01' AND hh.VoucherDate < '2026-04-01'
                        UNION ALL
                        SELECT TOP 1 VoucherNo FROM TrVocHead hh
                        JOIN MsTransType tt ON tt.id_key=hh.TransTypeID
                        WHERE tt.ShortName='DN' AND ISNULL(hh.Cancelled,'N')<>'Y'
                          AND hh.VoucherDate >= '2025-04-01' AND hh.VoucherDate < '2026-04-01'
                    )
                    ORDER BY h.VoucherDate, h.VoucherNo, d.DrCrIndicator
                """),

                # ── BLOCK E: Expenses ─────────────────────────────────────────────────
                ("47 — All expense accounts: MsAccountHead rows that look like P&L expenses", """
                    SELECT * FROM MsAccountHead
                    ORDER BY 1
                """),
                ("48 — JV (Journal Entries): DR/CR breakdown by party type and account", """
                    SELECT
                        d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Supplier (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL / No party'
                            ELSE 'Other: ' + LEFT(d.PartyID,2)
                        END                           AS party_type,
                        ISNULL(p.PartyName, d.PartyID) AS account_name,
                        COUNT(*)                       AS rows,
                        SUM(d.Amount)                  AS total,
                        COUNT(DISTINCT d.VoucherNo)    AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='JV'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY d.DrCrIndicator,
                        CASE
                            WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Supplier (C%)'
                            WHEN ISNULL(d.PartyID,'')='' THEN 'GL / No party'
                            ELSE 'Other: ' + LEFT(d.PartyID,2)
                        END,
                        ISNULL(p.PartyName, d.PartyID)
                    ORDER BY total DESC
                """),
                ("49 — Total spend by expense account: all non-product BP/CE + JV DR entries", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID)  AS account_name,
                        LEFT(d.PartyID,1)                AS prefix,
                        t.ShortName                      AS trans_code,
                        SUM(d.Amount)                    AS total_debit,
                        COUNT(DISTINCT d.VoucherNo)       AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE','JV')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='D'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND NOT EXISTS (
                          SELECT 1 FROM TrVocItem vi
                          WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo
                      )
                    GROUP BY ISNULL(p.PartyName, d.PartyID), LEFT(d.PartyID,1), t.ShortName
                    ORDER BY total_debit DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK F — Full column maps for every core table
                # ══════════════════════════════════════════════════════════════
                ("50 — TrVocHead: ALL columns (every field in invoice header)", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'TrVocHead'
                    ORDER BY ORDINAL_POSITION
                """),
                ("51 — TrVocItem: ALL columns (every field in invoice product/service lines)", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'TrVocItem'
                    ORDER BY ORDINAL_POSITION
                """),
                ("52 — TrVocDetail: ALL columns (every field in accounting entry lines)", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'TrVocDetail'
                    ORDER BY ORDINAL_POSITION
                """),
                ("53 — MsItemMaster: ALL columns (every field on a product/SKU)", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'MsItemMaster'
                    ORDER BY ORDINAL_POSITION
                """),
                ("54 — MsPartyMaster: ALL columns (every field on a party/account)", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'MsPartyMaster'
                    ORDER BY ORDINAL_POSITION
                """),
                ("55 — MsServiceItemMaster: ALL columns + all rows", """
                    SELECT * FROM MsServiceItemMaster ORDER BY 1
                """),
                ("56 — MsCodeMaster: ALL columns + all rows (lookup/config codes)", """
                    SELECT * FROM MsCodeMaster ORDER BY 1
                """),
                ("57 — All tables that contain 'User' or 'Access' or 'Role' or 'Permission'", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%User%'
                          OR TABLE_NAME LIKE '%Access%'
                          OR TABLE_NAME LIKE '%Role%'
                          OR TABLE_NAME LIKE '%Permission%'
                          OR TABLE_NAME LIKE '%Login%'
                          OR TABLE_NAME LIKE '%Auth%' )
                    ORDER BY TABLE_NAME
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK G — Complete voucher anatomy: full head+item+detail
                #   for every transaction type. This reveals the exact double-
                #   entry logic including excise, TCS, handling, discounts.
                # ══════════════════════════════════════════════════════════════
                ("58 — COMPLETE MS SALE VOUCHER: every TrVocItem column + every TrVocDetail line", """
                    -- Step 1: pick the most recent non-cancelled MS voucher
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC

                    -- Header
                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    -- All item lines (products AND service items)
                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, m.MrpBottRate, m.MrpCaseRate,
                           b.BrandName,
                           s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m     ON m.ItemID     = i.ItemID
                    LEFT JOIN MsBrandMaster b    ON b.BrandID    = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    -- All accounting entries
                    SELECT 'DETAIL' AS section, d.*,
                           p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("59 — COMPLETE PU PURCHASE VOUCHER: head + items + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, b.BrandName,
                           s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("60 — COMPLETE BP VOUCHER (WITH items = excise on goods): head + items + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND EXISTS (SELECT 1 FROM TrVocItem vi
                                  WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo)
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, b.BrandName, s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("61 — COMPLETE BP VOUCHER (WITHOUT items = expense payment): head + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem vi
                                      WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo)
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("62 — COMPLETE BR RECEIPT VOUCHER: head + detail (no items expected)", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BR'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*, s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("63 — COMPLETE CR CASH RECEIPT VOUCHER: head + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CR'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("64 — COMPLETE LD LOAD/DEMO VOUCHER: head + items + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='LD'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, b.BrandName, s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("65 — COMPLETE SA BREAKAGE VOUCHER: head + items + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='SA'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, b.BrandName, s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("66 — COMPLETE CN CREDIT NOTE: head + items + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, b.BrandName, s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("67 — COMPLETE DN DEBIT NOTE: head + items + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='DN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*,
                           m.ItemDescription, b.BrandName, s.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("68 — COMPLETE JV JOURNAL ENTRY: head + detail (no items)", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='JV'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK H — Service items & charge breakdown on a sale invoice
                # ══════════════════════════════════════════════════════════════
                ("69 — TrVocItem rows with ServiceItemID set (non-product lines on invoices)", """
                    SELECT TOP 50
                        t.ShortName, h.VoucherDate, h.VoucherNo,
                        i.*,
                        s.ServiceItemName,
                        m.ItemDescription
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    LEFT JOIN MsItemMaster m         ON m.ItemID       = i.ItemID
                    WHERE i.ServiceItemID IS NOT NULL
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo, i.SerialNo
                """),
                ("70 — All distinct ServiceItemIDs used in FY25-26 with totals", """
                    SELECT
                        i.ServiceItemID,
                        s.ServiceItemName,
                        t.ShortName,
                        COUNT(DISTINCT i.VoucherNo) AS vouchers,
                        SUM(i.TotalAmount)          AS total_amount,
                        SUM(i.TotalBottleQty)       AS total_bottles
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE i.ServiceItemID IS NOT NULL
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY i.ServiceItemID, s.ServiceItemName, t.ShortName
                    ORDER BY total_amount DESC
                """),
                ("71 — MS sale invoice: product lines vs service lines — amounts per component", """
                    SELECT
                        CASE WHEN i.ItemID IS NOT NULL AND i.ServiceItemID IS NULL
                             THEN 'Product'
                             WHEN i.ServiceItemID IS NOT NULL
                             THEN ISNULL(s.ServiceItemName,'Service #'+CAST(i.ServiceItemID AS VARCHAR))
                             ELSE 'Unknown'
                        END                                  AS line_type,
                        COUNT(*)                             AS line_rows,
                        COUNT(DISTINCT i.VoucherNo)          AS vouchers,
                        SUM(i.TotalAmount)                   AS total_amount,
                        SUM(i.TotalBottleQty)                AS total_bottles,
                        AVG(i.TotalAmount)                   AS avg_per_line
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY
                        CASE WHEN i.ItemID IS NOT NULL AND i.ServiceItemID IS NULL THEN 'Product'
                             WHEN i.ServiceItemID IS NOT NULL
                             THEN ISNULL(s.ServiceItemName,'Service #'+CAST(i.ServiceItemID AS VARCHAR))
                             ELSE 'Unknown' END
                    ORDER BY total_amount DESC
                """),
                ("72 — MS sale: total per TrVocDetail account — where does each rupee go?", """
                    SELECT
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, ISNULL(d.PartyID,'(blank)')) AS account_name,
                        LEFT(d.PartyID,2)  AS prefix,
                        COUNT(*)           AS rows,
                        COUNT(DISTINCT d.VoucherNo) AS vouchers,
                        SUM(d.Amount)      AS total_amount
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY d.DrCrIndicator,
                             ISNULL(p.PartyName, ISNULL(d.PartyID,'(blank)')),
                             LEFT(d.PartyID,2)
                    ORDER BY d.DrCrIndicator DESC, total_amount DESC
                """),
                ("73 — Discount: does TrVocItem have discount columns? Sample with non-zero values", """
                    -- Show all TrVocItem columns for rows where any likely discount
                    -- column (DiscountAmt, Discount, SchemeAmt, FreeBottles) is non-zero
                    SELECT TOP 30 i.*,
                           m.ItemDescription, b.BrandName, t.ShortName,
                           s.ServiceItemName
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    LEFT JOIN MsItemMaster m       ON m.ItemID       = i.ItemID
                    LEFT JOIN MsBrandMaster b      ON b.BrandID      = m.BrandID
                    LEFT JOIN MsServiceItemMaster s ON s.ServiceItemID = i.ServiceItemID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND i.FreeItemYN = 'Y'
                    ORDER BY h.VoucherDate DESC, i.VoucherNo, i.SerialNo
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK I — GL account universe: every account that ever appears
                # ══════════════════════════════════════════════════════════════
                ("74 — Every distinct PartyID/account that appears in TrVocDetail with totals", """
                    SELECT
                        d.PartyID,
                        ISNULL(p.PartyName,'(no name)') AS account_name,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_dr,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_cr,
                        COUNT(DISTINCT d.VoucherNo) AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY d.PartyID, ISNULL(p.PartyName,'(no name)'), LEFT(d.PartyID,2)
                    ORDER BY total_cr DESC
                """),
                ("75 — ALL MsPartyMaster rows that are NOT D% customers or C% suppliers (GL accounts)", """
                    SELECT PartyID, PartyName, Address,
                           LEFT(PartyID,1) AS prefix
                    FROM MsPartyMaster
                    WHERE LEFT(PartyID,1) NOT IN ('D','C')
                    ORDER BY PartyID
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK J — User & access tables
                # ══════════════════════════════════════════════════════════════
                ("76 — User tables: list all tables found + row counts", """
                    SELECT t.TABLE_NAME,
                           (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                            WHERE c.TABLE_NAME = t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%User%'
                          OR TABLE_NAME LIKE '%Access%'
                          OR TABLE_NAME LIKE '%Role%'
                          OR TABLE_NAME LIKE '%Login%'
                          OR TABLE_NAME LIKE '%Auth%'
                          OR TABLE_NAME LIKE '%Right%'
                          OR TABLE_NAME LIKE '%Privilege%' )
                    ORDER BY TABLE_NAME
                """),
                ("77 — MsUserMaster (or equivalent): all columns + all rows", """
                    SELECT * FROM MsUserMaster ORDER BY 1
                """),
                ("78 — User access/rights table: all columns + all rows", """
                    SELECT * FROM MsUserRights ORDER BY 1
                """),
                ("79 — User form/menu access: all columns + all rows", """
                    SELECT * FROM MsUserFormAccess ORDER BY 1
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK K — Transport Permits (TrTPHead / TrTPDetail)
                # ══════════════════════════════════════════════════════════════
                ("80 — TrTPHead: ALL columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'TrTPHead'
                    ORDER BY ORDINAL_POSITION
                """),
                ("81 — TrTPDetail: ALL columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'TrTPDetail'
                    ORDER BY ORDINAL_POSITION
                """),
                ("82 — TrTPHead: sample 5 rows with linked invoice", """
                    SELECT TOP 5 tp.*,
                           h.VoucherDate AS invoice_date,
                           t.ShortName   AS invoice_type
                    FROM TrTPHead tp
                    LEFT JOIN TrVocHead h ON h.VoucherNo=tp.VoucherNo
                    LEFT JOIN MsTransType t ON t.id_key=h.TransTypeID
                    ORDER BY tp.TPDate DESC
                """),
                ("83 — TrTPDetail: sample 10 rows with item names", """
                    SELECT TOP 10 d.*,
                           m.ItemDescription, b.BrandName
                    FROM TrTPDetail d
                    LEFT JOIN MsItemMaster m ON m.ItemID=d.ItemID
                    LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    ORDER BY d.TPDate DESC
                """),
                ("84 — TP coverage: how many sale invoices have a TP vs do not", """
                    SELECT
                        CASE WHEN h.TPNo IS NOT NULL AND h.TPNo <> '' THEN 'Has TPNo on head'
                             ELSE 'No TPNo on head' END AS tp_status,
                        COUNT(*) AS vouchers,
                        MIN(h.VoucherDate) AS earliest,
                        MAX(h.VoucherDate) AS latest
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY
                        CASE WHEN h.TPNo IS NOT NULL AND h.TPNo <> '' THEN 'Has TPNo on head'
                             ELSE 'No TPNo on head' END
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK L — Scheme / discount / free goods logic
                # ══════════════════════════════════════════════════════════════
                ("85 — MsScheme or scheme-related tables: discovery", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Scheme%'
                          OR TABLE_NAME LIKE '%Discount%'
                          OR TABLE_NAME LIKE '%Free%'
                          OR TABLE_NAME LIKE '%Promo%' )
                    ORDER BY TABLE_NAME
                """),
                ("86 — Free-goods invoices: how many bottles given free vs sold in FY25-26", """
                    SELECT
                        b.BrandName,
                        SUM(CASE WHEN ISNULL(i.FreeItemYN,'N')='Y' THEN i.TotalBottleQty ELSE 0 END) AS free_bottles,
                        SUM(CASE WHEN ISNULL(i.FreeItemYN,'N')<>'Y' THEN i.TotalBottleQty ELSE 0 END) AS sold_bottles,
                        SUM(CASE WHEN ISNULL(i.FreeItemYN,'N')='Y' THEN i.TotalAmount ELSE 0 END) AS free_mrp_value
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY b.BrandName
                    ORDER BY free_bottles DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK M — MsItemMaster extra: rates, excise, import flag
                # ══════════════════════════════════════════════════════════════
                ("87 — MsItemMaster: full sample 10 rows (all columns)", """
                    SELECT TOP 10 * FROM MsItemMaster ORDER BY ItemID
                """),
                ("88 — MsItemMaster: imported vs domestic item count and total stock", """
                    SELECT
                        ISNULL(ImportedYN,'N')        AS imported,
                        lt.LiquorType,
                        COUNT(DISTINCT m.ItemID)      AS sku_count,
                        AVG(m.MrpBottRate)            AS avg_mrp,
                        MAX(m.MrpBottRate)            AS max_mrp
                    FROM MsItemMaster m
                    LEFT JOIN MsLiquorType lt ON lt.LiquorTypeID = m.LiquorTypeID
                    GROUP BY ISNULL(ImportedYN,'N'), lt.LiquorType
                    ORDER BY sku_count DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK N — Sales order (SO) and receipt order (RO)
                # ══════════════════════════════════════════════════════════════
                ("89 — SO Sales Order: complete sample voucher", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='SO'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC

                    SELECT 'HEADER' AS section, h.*
                    FROM TrVocHead h WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS section, i.*, m.ItemDescription, b.BrandName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS section, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK O — Any tables we have not yet seen at all
                # ══════════════════════════════════════════════════════════════
                ("90 — All tables NOT in (TrVoc*, TrTP*, Ms*, X*) — any unknown prefixes?", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME NOT LIKE 'TrVoc%'
                      AND TABLE_NAME NOT LIKE 'TrTP%'
                      AND TABLE_NAME NOT LIKE 'Ms%'
                      AND TABLE_NAME NOT LIKE 'X%'
                    ORDER BY TABLE_NAME
                """),
                ("91 — Row counts for ALL tables sorted descending (full picture at a glance)", """
                    SELECT
                        t.TABLE_NAME,
                        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                         WHERE c.TABLE_NAME=t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                    ORDER BY TABLE_NAME
                """),
                ("92 — MsBatchMaster: all columns + sample rows", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsBatchMaster'
                    ORDER BY ORDINAL_POSITION

                    SELECT TOP 10 b.*, m.ItemDescription
                    FROM MsBatchMaster b
                    LEFT JOIN MsItemMaster m ON m.ItemID=b.ItemID
                    ORDER BY b.BatchID DESC
                """),
                ("93 — MsPartyMaster: full sample 20 rows — see all fields", """
                    SELECT TOP 20 * FROM MsPartyMaster ORDER BY PartyID
                """),
                ("94 — MsBrandMaster + MsItemMaster join: see CompanyID and all fields", """
                    SELECT TOP 20
                        b.BrandID, b.BrandName, b.CompanyID,
                        p.PartyName AS company_name,
                        m.ItemID, m.ItemDescription, m.MrpBottRate,
                        m.ImportedYN, m.LiquorTypeID, m.SizeTypeID
                    FROM MsBrandMaster b
                    LEFT JOIN MsPartyMaster p ON p.PartyID=b.CompanyID
                    LEFT JOIN MsItemMaster m ON m.BrandID=b.BrandID
                    ORDER BY b.BrandID, m.ItemID
                """),
                ("95 — MsTransType: FULL table (all transaction type definitions)", """
                    SELECT * FROM MsTransType ORDER BY ShortName, id_key
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
