import streamlit as st
import json
import pandas as pd
from db import get_connection, query


def render():
    st.header("Database Schema Explorer")

    tab_survey, tab_brands, tab_objects, tab_diag = st.tabs([
        "📋 Full Schema Survey", "Brand / Item Mapping",
        "🗃️ DB Objects", "🔍 Diagnostics",
    ])

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

    # ── Tab 3: DB Objects ─────────────────────────────────────────────────────
    # Discovers every programmatic object in the database: views, stored procs,
    # functions, triggers, indexes, computed columns, identity columns.
    # The SQL definitions of views/SPs are the ERP's own report logic — this is
    # the single most important thing to understand before writing any query.
    with tab_objects:
        st.markdown(
            "Discovers every **programmatic object** the ERP has created: views, stored "
            "procedures, functions, triggers, indexes, computed columns, and identity columns. "
            "**Views and SPs contain the ERP's own report SQL** — the most direct way to "
            "understand what each report reads and how it aggregates."
        )
        col_btn2, col_dl2, _ = st.columns([2, 2, 3])
        with col_btn2:
            run_objects = st.button("▶ Discover DB Objects", type="primary",
                                    use_container_width=True, key="run_obj")
        with col_dl2:
            if "obj_zip" in st.session_state:
                st.download_button(
                    "⬇️ Download Objects (.zip)",
                    data=st.session_state["obj_zip"],
                    file_name="kwpl_db_objects.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="dl_obj",
                )
            else:
                st.button("⬇️ Download Objects (.zip)", disabled=True,
                          use_container_width=True, key="dl_obj_dis")

        if run_objects:
            import io as _io, zipfile as _zf
            prog2 = st.progress(0, text="Scanning DB objects…")
            try:
                conn2 = get_connection()
                c2    = conn2.cursor(as_dict=True)

                def _q2(sql):
                    try:
                        c2.execute(sql)
                        return c2.fetchall() or []
                    except Exception as e:
                        return [{"ERROR": str(e)}]

                # ── Views ────────────────────────────────────────────────────
                prog2.progress(0.05, text="Views…")
                views = _q2("""
                    SELECT v.name AS view_name,
                           m.definition AS view_sql
                    FROM sys.views v
                    JOIN sys.sql_modules m ON m.object_id = v.object_id
                    ORDER BY v.name
                """)

                # ── Stored Procedures ─────────────────────────────────────────
                prog2.progress(0.18, text="Stored procedures…")
                procs = _q2("""
                    SELECT p.name AS proc_name,
                           m.definition AS proc_sql
                    FROM sys.procedures p
                    JOIN sys.sql_modules m ON m.object_id = p.object_id
                    ORDER BY p.name
                """)

                # ── User-Defined Functions ────────────────────────────────────
                prog2.progress(0.28, text="Functions…")
                funcs = _q2("""
                    SELECT o.name AS func_name,
                           o.type_desc,
                           m.definition AS func_sql
                    FROM sys.objects o
                    JOIN sys.sql_modules m ON m.object_id = o.object_id
                    WHERE o.type IN ('FN','IF','TF')
                    ORDER BY o.name
                """)

                # ── Triggers ─────────────────────────────────────────────────
                prog2.progress(0.36, text="Triggers…")
                triggers = _q2("""
                    SELECT t.name AS trigger_name,
                           OBJECT_NAME(t.parent_id) AS on_table,
                           m.definition AS trigger_sql
                    FROM sys.triggers t
                    JOIN sys.sql_modules m ON m.object_id = t.object_id
                    ORDER BY on_table, t.name
                """)

                # ── Indexes ───────────────────────────────────────────────────
                # One row per index column so no STRING_AGG needed.
                prog2.progress(0.46, text="Indexes…")
                indexes = _q2("""
                    SELECT
                        tb.name                AS table_name,
                        i.name                 AS index_name,
                        i.type_desc,
                        i.is_unique,
                        i.is_primary_key,
                        ic.key_ordinal,
                        ic.is_included_column,
                        c.name                 AS column_name
                    FROM sys.indexes i
                    JOIN sys.tables          tb ON tb.object_id = i.object_id
                    JOIN sys.index_columns   ic ON ic.object_id = i.object_id
                                               AND ic.index_id  = i.index_id
                    JOIN sys.columns         c  ON c.object_id  = ic.object_id
                                               AND c.column_id  = ic.column_id
                    WHERE i.type > 0
                    ORDER BY tb.name, i.is_primary_key DESC, i.name, ic.key_ordinal
                """)

                # ── Computed Columns ──────────────────────────────────────────
                prog2.progress(0.62, text="Computed columns…")
                computed = _q2("""
                    SELECT
                        t.name  AS table_name,
                        c.name  AS column_name,
                        cc.definition AS expression,
                        cc.is_persisted
                    FROM sys.computed_columns cc
                    JOIN sys.tables  t ON t.object_id  = cc.object_id
                    JOIN sys.columns c ON c.object_id  = cc.object_id
                                     AND c.column_id   = cc.column_id
                    ORDER BY t.name, c.name
                """)

                # ── Identity Columns ──────────────────────────────────────────
                prog2.progress(0.74, text="Identity columns…")
                identities = _q2("""
                    SELECT
                        t.name  AS table_name,
                        c.name  AS column_name,
                        ic.seed_value,
                        ic.increment_value,
                        ic.last_value
                    FROM sys.identity_columns ic
                    JOIN sys.tables  t ON t.object_id = ic.object_id
                    JOIN sys.columns c ON c.object_id = ic.object_id
                                     AND c.column_id  = ic.column_id
                    ORDER BY t.name
                """)

                # ── Column Defaults ───────────────────────────────────────────
                prog2.progress(0.82, text="Column defaults…")
                defaults = _q2("""
                    SELECT
                        t.name   AS table_name,
                        c.name   AS column_name,
                        d.definition AS default_value,
                        c.is_nullable
                    FROM sys.default_constraints d
                    JOIN sys.tables  t ON t.object_id = d.parent_object_id
                    JOIN sys.columns c ON c.object_id = d.parent_object_id
                                     AND c.column_id  = d.parent_column_id
                    ORDER BY t.name, c.name
                """)

                # ── Check Constraints ─────────────────────────────────────────
                prog2.progress(0.88, text="Check constraints…")
                checks = _q2("""
                    SELECT
                        t.name  AS table_name,
                        cc.name AS constraint_name,
                        cc.definition
                    FROM sys.check_constraints cc
                    JOIN sys.tables t ON t.object_id = cc.parent_object_id
                    ORDER BY t.name
                """)

                # ── Unique Constraints ────────────────────────────────────────
                prog2.progress(0.93, text="Unique constraints…")
                unique_idx = _q2("""
                    SELECT
                        t.name  AS table_name,
                        i.name  AS constraint_name,
                        c.name  AS column_name
                    FROM sys.indexes i
                    JOIN sys.tables        t  ON t.object_id  = i.object_id
                    JOIN sys.index_columns ic ON ic.object_id = i.object_id
                                             AND ic.index_id  = i.index_id
                    JOIN sys.columns       c  ON c.object_id  = ic.object_id
                                             AND c.column_id  = ic.column_id
                    WHERE i.is_unique_constraint = 1
                    ORDER BY t.name, i.name, ic.key_ordinal
                """)

                conn2.close()
                prog2.progress(0.97, text="Building ZIP…")

                # ── Build ZIP ────────────────────────────────────────────────
                buf2 = _io.BytesIO()
                with _zf.ZipFile(buf2, "w", _zf.ZIP_DEFLATED) as z2:
                    def _add(name, data):
                        if data and "ERROR" not in data[0]:
                            z2.writestr(name, pd.DataFrame(data).to_csv(index=False))

                    _add("views.csv",        views)
                    _add("stored_procs.csv", procs)
                    _add("functions.csv",    funcs)
                    _add("triggers.csv",     triggers)
                    _add("indexes.csv",      indexes)
                    _add("computed_cols.csv",computed)
                    _add("identity_cols.csv",identities)
                    _add("col_defaults.csv", defaults)
                    _add("check_constraints.csv", checks)
                    _add("unique_constraints.csv", unique_idx)

                    # Full SQL text files for views and procs
                    if views and "ERROR" not in views[0]:
                        for row in views:
                            safe = row["view_name"].replace("/","_")
                            z2.writestr(f"views/{safe}.sql",
                                        row.get("view_sql") or "")
                    if procs and "ERROR" not in procs[0]:
                        for row in procs:
                            safe = row["proc_name"].replace("/","_")
                            z2.writestr(f"procs/{safe}.sql",
                                        row.get("proc_sql") or "")
                    if funcs and "ERROR" not in funcs[0]:
                        for row in funcs:
                            safe = row["func_name"].replace("/","_")
                            z2.writestr(f"funcs/{safe}.sql",
                                        row.get("func_sql") or "")
                    if triggers and "ERROR" not in triggers[0]:
                        for row in triggers:
                            safe = row["trigger_name"].replace("/","_")
                            z2.writestr(f"triggers/{safe}.sql",
                                        row.get("trigger_sql") or "")

                buf2.seek(0)
                st.session_state["obj_zip"]      = buf2.getvalue()
                st.session_state["obj_views"]     = views
                st.session_state["obj_procs"]     = procs
                st.session_state["obj_funcs"]     = funcs
                st.session_state["obj_triggers"]  = triggers
                st.session_state["obj_indexes"]   = indexes
                st.session_state["obj_computed"]  = computed
                st.session_state["obj_identities"]= identities
                st.session_state["obj_defaults"]  = defaults
                st.session_state["obj_checks"]    = checks
                st.session_state["obj_unique"]    = unique_idx

                prog2.progress(1.0, text="Done.")
                st.rerun()

            except Exception as ex:
                st.error(f"Object scan failed: {ex}")

        # ── Display ───────────────────────────────────────────────────────────
        if "obj_views" in st.session_state:
            views      = st.session_state["obj_views"]
            procs      = st.session_state["obj_procs"]
            funcs      = st.session_state["obj_funcs"]
            triggers   = st.session_state["obj_triggers"]
            indexes    = st.session_state["obj_indexes"]
            computed   = st.session_state["obj_computed"]
            identities = st.session_state["obj_identities"]

            def _safe_df(data):
                return pd.DataFrame(data) if data and "ERROR" not in data[0] else pd.DataFrame()

            # ── Views ─────────────────────────────────────────────────────────
            st.subheader(f"Views ({len([v for v in views if 'ERROR' not in v]) if views else 0})")
            st.caption("If the ERP stores any report logic as views, the full SQL is here.")
            df_v = _safe_df(views)
            if not df_v.empty:
                for _, row in df_v.iterrows():
                    with st.expander(f"📄 {row['view_name']}"):
                        st.code(row.get("view_sql",""), language="sql")
            else:
                st.info("No views found — ERP does not use SQL views for reports.")

            st.divider()

            # ── Stored Procedures ─────────────────────────────────────────────
            st.subheader(f"Stored Procedures ({len([p for p in procs if 'ERROR' not in p]) if procs else 0})")
            st.caption("SP definitions contain the exact SQL the ERP runs for each operation/report.")
            df_p = _safe_df(procs)
            if not df_p.empty:
                for _, row in df_p.iterrows():
                    with st.expander(f"⚙️ {row['proc_name']}"):
                        st.code(row.get("proc_sql",""), language="sql")
            else:
                st.info("No stored procedures found.")

            st.divider()

            # ── Functions ─────────────────────────────────────────────────────
            df_f = _safe_df(funcs)
            st.subheader(f"User-Defined Functions ({len(df_f)})")
            if not df_f.empty:
                for _, row in df_f.iterrows():
                    with st.expander(f"ƒ {row['func_name']} ({row.get('type_desc','')})"):
                        st.code(row.get("func_sql",""), language="sql")
            else:
                st.info("No user-defined functions found.")

            st.divider()

            # ── Triggers ─────────────────────────────────────────────────────
            df_tr = _safe_df(triggers)
            st.subheader(f"Triggers ({len(df_tr)})")
            st.caption("Triggers contain ERP business rules that fire automatically on INSERT/UPDATE/DELETE.")
            if not df_tr.empty:
                for _, row in df_tr.iterrows():
                    with st.expander(f"⚡ {row['trigger_name']}  →  {row.get('on_table','')}"):
                        st.code(row.get("trigger_sql",""), language="sql")
            else:
                st.info("No triggers found.")

            st.divider()

            # ── Indexes ──────────────────────────────────────────────────────
            df_ix = _safe_df(indexes)
            st.subheader(f"Index Inventory ({len(df_ix)} index-column rows)")
            st.caption(
                "Indexed columns reveal the ERP's query patterns — if a column is part of a "
                "composite index it's almost certainly used as a WHERE/JOIN filter in reports."
            )
            if not df_ix.empty:
                tbl_filter = st.selectbox(
                    "Filter by table",
                    options=["All tables"] + sorted(df_ix["table_name"].unique().tolist()),
                    key="ix_tbl_filter",
                )
                df_show = df_ix if tbl_filter == "All tables" else df_ix[df_ix["table_name"] == tbl_filter]
                st.dataframe(df_show, use_container_width=True, hide_index=True)

            st.divider()

            # ── Computed Columns ──────────────────────────────────────────────
            df_cc = _safe_df(computed)
            st.subheader(f"Computed Columns ({len(df_cc)})")
            st.caption("Columns the ERP derives automatically — shows formulas baked into the schema.")
            if not df_cc.empty:
                st.dataframe(df_cc, use_container_width=True, hide_index=True)
            else:
                st.info("No computed columns found.")

            st.divider()

            # ── Identity Columns ──────────────────────────────────────────────
            df_id = _safe_df(identities)
            st.subheader(f"Identity / Auto-Increment Columns ({len(df_id)})")
            st.caption("Auto-generated primary keys — tells us which tables use surrogate PKs.")
            if not df_id.empty:
                st.dataframe(df_id, use_container_width=True, hide_index=True)
            else:
                st.info("No identity columns found.")

    # ── Tab 4: Diagnostics ────────────────────────────────────────────────────
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

                # ══════════════════════════════════════════════════════════════
                # BLOCK P — Complete master table discovery
                #   Find every Ms* table we haven't sampled yet
                # ══════════════════════════════════════════════════════════════
                ("96 — ALL Ms* master tables: name + row count + column count", """
                    SELECT
                        t.TABLE_NAME,
                        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                         WHERE c.TABLE_NAME = t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME LIKE 'Ms%'
                    ORDER BY TABLE_NAME
                """),
                ("97 — ALL Tr* transaction tables: name + col count", """
                    SELECT
                        t.TABLE_NAME,
                        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                         WHERE c.TABLE_NAME = t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME LIKE 'Tr%'
                    ORDER BY TABLE_NAME
                """),
                ("98 — ALL X* config/crossref tables: full dump of each", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME LIKE 'X%'
                    ORDER BY TABLE_NAME
                """),
                ("99 — XMainheadSubhead: full dump (GL sub-head hierarchy)", """
                    SELECT * FROM XMainheadSubhead ORDER BY 1
                """),
                ("100 — XMainheadTypeMainhead: full dump (GL main-head → type map)", """
                    SELECT * FROM XMainheadTypeMainhead ORDER BY 1
                """),
                ("101 — MsAccountHead: full dump with all columns", """
                    SELECT * FROM MsAccountHead ORDER BY 1
                """),
                ("102 — MsAccountHead: columns definition", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsAccountHead'
                    ORDER BY ORDINAL_POSITION
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK Q — Customer / party extended data
                # ══════════════════════════════════════════════════════════════
                ("103 — Customer category/group: discover category-related tables", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Category%'
                          OR TABLE_NAME LIKE '%Group%'
                          OR TABLE_NAME LIKE '%Area%'
                          OR TABLE_NAME LIKE '%Route%'
                          OR TABLE_NAME LIKE '%Zone%'
                          OR TABLE_NAME LIKE '%Region%'
                          OR TABLE_NAME LIKE '%District%'
                          OR TABLE_NAME LIKE '%Location%' )
                    ORDER BY TABLE_NAME
                """),
                ("104 — MsCategoryMaster (or equivalent): all columns + all rows", """
                    SELECT * FROM MsCategoryMaster ORDER BY 1
                """),
                ("105 — MsAreaMaster: all columns + all rows", """
                    SELECT * FROM MsAreaMaster ORDER BY 1
                """),
                ("106 — MsRouteMaster: all columns + all rows", """
                    SELECT * FROM MsRouteMaster ORDER BY 1
                """),
                ("107 — Customer breakdown by category: count + outstanding + sales", """
                    SELECT
                        ISNULL(cat.CategoryName, 'No Category') AS category,
                        COUNT(DISTINCT p.PartyID)               AS customers,
                        SUM(op.CloseBalTmp)                     AS outstanding,
                        SUM(vi.TotalAmount)                     AS fy_sales
                    FROM MsPartyMaster p
                    LEFT JOIN MsCategoryMaster cat ON cat.CategoryID = p.CategoryID
                    LEFT JOIN MsPartyOpening op    ON op.PartyID = p.PartyID
                    LEFT JOIN TrVocDetail d        ON d.PartyID = p.PartyID
                    LEFT JOIN TrVocHead h          ON h.TransTypeID=d.TransTypeID
                                                  AND h.VoucherNo=d.VoucherNo
                                                  AND ISNULL(h.Cancelled,'N')<>'Y'
                                                  AND h.VoucherDate>='2025-04-01'
                                                  AND h.VoucherDate<'2026-04-01'
                    LEFT JOIN TrVocItem vi         ON vi.TransTypeID=d.TransTypeID
                                                  AND vi.VoucherNo=d.VoucherNo
                    WHERE LEFT(p.PartyID,1)='D'
                    GROUP BY ISNULL(cat.CategoryName,'No Category')
                    ORDER BY fy_sales DESC
                """),
                ("108 — Customer area/route breakdown: count + sales", """
                    SELECT
                        ISNULL(a.AreaName,'No Area')   AS area,
                        ISNULL(r.RouteName,'No Route') AS route,
                        COUNT(DISTINCT p.PartyID)      AS customers
                    FROM MsPartyMaster p
                    LEFT JOIN MsAreaMaster a  ON a.AreaID  = p.AreaID
                    LEFT JOIN MsRouteMaster r ON r.RouteID = p.RouteID
                    WHERE LEFT(p.PartyID,1)='D'
                    GROUP BY ISNULL(a.AreaName,'No Area'), ISNULL(r.RouteName,'No Route')
                    ORDER BY customers DESC
                """),
                ("109 — MsPartyMaster: all columns for credit-limit / licence fields", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsPartyMaster'
                    ORDER BY ORDINAL_POSITION
                """),
                ("110 — Customer credit limit utilisation: limit vs outstanding", """
                    SELECT
                        p.PartyID, p.PartyName,
                        p.CreditLimit,
                        p.CreditDays,
                        op.CloseBalTmp          AS current_outstanding,
                        CASE WHEN p.CreditLimit > 0
                             THEN ROUND(op.CloseBalTmp * 100.0 / p.CreditLimit, 1)
                             ELSE NULL END       AS utilisation_pct,
                        p.BannedPartyYN
                    FROM MsPartyMaster p
                    LEFT JOIN MsPartyOpening op ON op.PartyID = p.PartyID
                    WHERE LEFT(p.PartyID,1)='D'
                      AND op.CloseBalTmp > 0
                    ORDER BY current_outstanding DESC
                """),
                ("111 — Customers over credit limit right now", """
                    SELECT
                        p.PartyID, p.PartyName,
                        p.CreditLimit,
                        op.CloseBalTmp AS outstanding,
                        op.CloseBalTmp - p.CreditLimit AS excess
                    FROM MsPartyMaster p
                    JOIN MsPartyOpening op ON op.PartyID=p.PartyID
                    WHERE LEFT(p.PartyID,1)='D'
                      AND p.CreditLimit > 0
                      AND op.CloseBalTmp > p.CreditLimit
                    ORDER BY excess DESC
                """),
                ("112 — MsLicenseMaster or licence fields on MsPartyMaster: discover", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%License%'
                          OR TABLE_NAME LIKE '%Licence%'
                          OR TABLE_NAME LIKE '%Permit%' )
                    ORDER BY TABLE_NAME
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK R — Salesman: targets, routes, customers, performance
                # ══════════════════════════════════════════════════════════════
                ("113 — MsSalesmanMaster: ALL columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsSalesmanMaster'
                    ORDER BY ORDINAL_POSITION
                """),
                ("114 — MsSalesmanMaster: full dump (all rows, all fields)", """
                    SELECT * FROM MsSalesmanMaster ORDER BY SalesManID
                """),
                ("115 — Salesman-related tables discovery", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Salesman%'
                          OR TABLE_NAME LIKE '%SalesMan%'
                          OR TABLE_NAME LIKE '%Sales_Man%'
                          OR TABLE_NAME LIKE '%Target%'
                          OR TABLE_NAME LIKE '%Incentive%'
                          OR TABLE_NAME LIKE '%Beat%' )
                    ORDER BY TABLE_NAME
                """),
                ("116 — MsSalesmanTarget (or equivalent): all columns + all rows", """
                    SELECT * FROM MsSalesmanTarget ORDER BY 1
                """),
                ("117 — Salesman: which customers are assigned to which salesman", """
                    SELECT
                        s.SalesManID, s.FullName AS salesman,
                        COUNT(p.PartyID)          AS customers_assigned,
                        MIN(p.PartyName)           AS sample_customer_1,
                        MAX(p.PartyName)           AS sample_customer_2
                    FROM MsSalesmanMaster s
                    LEFT JOIN MsPartyMaster p ON p.SalesManID=s.SalesManID
                                              AND LEFT(p.PartyID,1)='D'
                    GROUP BY s.SalesManID, s.FullName
                    ORDER BY customers_assigned DESC
                """),
                ("118 — Salesman monthly performance: sales + collections FY25-26", """
                    SELECT
                        s.FullName AS salesman,
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        SUM(i.TotalAmount)  AS sales,
                        SUM(i.TotalBottleQty) AS bottles,
                        COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS invoices
                    FROM TrVocHead h
                    JOIN TrVocItem i    ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY s.FullName, YEAR(h.VoucherDate), MONTH(h.VoucherDate)
                    ORDER BY s.FullName, yr, mo
                """),
                ("119 — Salesman: outstanding + overdue by salesman", """
                    SELECT
                        s.FullName AS salesman,
                        COUNT(DISTINCT op.PartyID) AS debtors,
                        SUM(op.CloseBalTmp)         AS outstanding,
                        SUM(CASE WHEN DATEDIFF(DAY,COALESCE(h.TPDate,h.VoucherDate),GETDATE())>90
                                 THEN d.RemainingAmt ELSE 0 END) AS overdue_90_plus
                    FROM MsSalesmanMaster s
                    JOIN MsPartyMaster p   ON p.SalesManID=s.SalesManID
                    JOIN MsPartyOpening op ON op.PartyID=p.PartyID
                    LEFT JOIN TrVocDetail d ON d.PartyID=p.PartyID AND d.RemainingAmt>0
                    LEFT JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    WHERE LEFT(p.PartyID,1)='D' AND op.CloseBalTmp>0
                      AND s.ResignDate IS NULL
                    GROUP BY s.FullName
                    ORDER BY outstanding DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK S — Expenses: full account hierarchy and all entries
                # ══════════════════════════════════════════════════════════════
                ("120 — Expense account hierarchy: MsAccountHead with parent-child tree", """
                    SELECT
                        a.*,
                        parent.AccHeadName AS parent_name
                    FROM MsAccountHead a
                    LEFT JOIN MsAccountHead parent ON parent.AccHeadID = a.ParentAccHeadID
                    ORDER BY a.ParentAccHeadID, a.AccHeadID
                """),
                ("121 — All expense entries: every non-product BP/CE/JV DR entry by account", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID) AS expense_account,
                        t.ShortName                    AS voucher_type,
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        SUM(d.Amount)  AS amount,
                        COUNT(*)       AS entries,
                        MIN(h.Narration) AS sample_narration
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE','JV')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND d.DrCrIndicator='D'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem vi
                                      WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo)
                    GROUP BY ISNULL(p.PartyName,d.PartyID), t.ShortName,
                             YEAR(h.VoucherDate), MONTH(h.VoucherDate)
                    ORDER BY yr, mo, amount DESC
                """),
                ("122 — Expense totals by account for full FY25-26 (ranked)", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID) AS expense_account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(d.Amount)                   AS total_fy,
                        COUNT(DISTINCT d.VoucherNo)     AS vouchers,
                        MIN(h.Narration)                AS sample_narration
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE','JV')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND d.DrCrIndicator='D'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem vi
                                      WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo)
                    GROUP BY ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY total_fy DESC
                """),
                ("123 — Monthly expense trend by top accounts", """
                    SELECT
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        ISNULL(p.PartyName, d.PartyID) AS expense_account,
                        SUM(d.Amount) AS amount
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE','JV')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND d.DrCrIndicator='D'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem vi
                                      WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo)
                    GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate),
                             ISNULL(p.PartyName,d.PartyID)
                    ORDER BY yr, mo, amount DESC
                """),
                ("124 — Sample 10 expense vouchers with full narration", """
                    SELECT TOP 10
                        h.VoucherDate, h.VoucherNo, t.ShortName,
                        h.Narration,
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        d.Amount
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem vi
                                      WHERE vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo)
                    ORDER BY h.VoucherDate DESC, h.VoucherNo, d.DrCrIndicator
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK T — ERP Settings / configuration tables
                # ══════════════════════════════════════════════════════════════
                ("125 — Settings tables: discover every table with Setting/Config/Setup/Param", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Setting%'
                          OR TABLE_NAME LIKE '%Config%'
                          OR TABLE_NAME LIKE '%Setup%'
                          OR TABLE_NAME LIKE '%Param%'
                          OR TABLE_NAME LIKE '%Option%'
                          OR TABLE_NAME LIKE '%Preference%'
                          OR TABLE_NAME LIKE '%Default%'
                          OR TABLE_NAME LIKE '%FinancialYear%'
                          OR TABLE_NAME LIKE '%FYear%' )
                    ORDER BY TABLE_NAME
                """),
                ("126 — MsCodeMaster: ALL columns + full dump", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsCodeMaster'
                    ORDER BY ORDINAL_POSITION

                    SELECT * FROM MsCodeMaster ORDER BY 1
                """),
                ("127 — MsTransType: all columns + full dump (what config does each type carry?)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsTransType'
                    ORDER BY ORDINAL_POSITION

                    SELECT * FROM MsTransType ORDER BY ShortName, id_key
                """),
                ("128 — Financial year config: how is active FY stored?", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Financial%'
                          OR TABLE_NAME LIKE '%FYear%'
                          OR TABLE_NAME LIKE '%Year%' )
                    ORDER BY TABLE_NAME
                """),
                ("129 — Default accounts per transaction type: which GL accounts are hardwired?", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        t.*
                    FROM MsTransType t
                    ORDER BY t.ShortName, t.id_key
                """),
                ("130 — MsCompanyMaster or company settings: discover and dump", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Company%'
                          OR TABLE_NAME LIKE '%Firm%'
                          OR TABLE_NAME LIKE '%Organisation%'
                          OR TABLE_NAME LIKE '%Organization%' )
                    ORDER BY TABLE_NAME
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK U — Scheme, discount, TCS, excise rate masters
                # ══════════════════════════════════════════════════════════════
                ("131 — All scheme/discount/rate tables: discovery", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Scheme%'
                          OR TABLE_NAME LIKE '%Discount%'
                          OR TABLE_NAME LIKE '%Rate%'
                          OR TABLE_NAME LIKE '%TCS%'
                          OR TABLE_NAME LIKE '%Tax%'
                          OR TABLE_NAME LIKE '%Excise%'
                          OR TABLE_NAME LIKE '%Duty%'
                          OR TABLE_NAME LIKE '%Slab%' )
                    ORDER BY TABLE_NAME
                """),
                ("132 — MsSchemeMaster: all columns + all rows", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsSchemeMaster'
                    ORDER BY ORDINAL_POSITION

                    SELECT * FROM MsSchemeMaster ORDER BY 1
                """),
                ("133 — MsTCSMaster or TCS rate table: all columns + all rows", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME LIKE '%TCS%'

                    SELECT * FROM MsTCSMaster ORDER BY 1
                """),
                ("134 — Scheme usage in FY25-26: which schemes applied to how many invoices", """
                    SELECT
                        i.SchemeID,
                        COUNT(DISTINCT i.VoucherNo)  AS vouchers,
                        SUM(i.TotalBottleQty)        AS free_bottles,
                        SUM(i.TotalAmount)           AS free_mrp_value
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    WHERE ISNULL(i.FreeItemYN,'N')='Y'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY i.SchemeID
                    ORDER BY vouchers DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK V — Vehicle / delivery / logistics masters
                # ══════════════════════════════════════════════════════════════
                ("135 — Vehicle and logistics tables: discovery + dump", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Vehicle%'
                          OR TABLE_NAME LIKE '%Driver%'
                          OR TABLE_NAME LIKE '%Delivery%'
                          OR TABLE_NAME LIKE '%Dispatch%'
                          OR TABLE_NAME LIKE '%Warehouse%'
                          OR TABLE_NAME LIKE '%Godown%'
                          OR TABLE_NAME LIKE '%Stock%' )
                    ORDER BY TABLE_NAME
                """),
                ("136 — MsVehicleMaster: all columns + all rows", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsVehicleMaster'
                    ORDER BY ORDINAL_POSITION

                    SELECT * FROM MsVehicleMaster ORDER BY 1
                """),
                ("137 — Deliveries: invoices vs TPs by month — how many are still undelivered?", """
                    SELECT
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        COUNT(DISTINCT h.VoucherNo)                       AS ms_invoices,
                        COUNT(DISTINCT tp.TPNo)                           AS tps_generated,
                        COUNT(DISTINCT h.VoucherNo) -
                            COUNT(DISTINCT tp.TPNo)                       AS no_tp_yet
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrTPHead tp ON tp.VoucherNo=h.VoucherNo
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
                    ORDER BY yr, mo
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK W — Stock: batch + opening + current position
                # ══════════════════════════════════════════════════════════════
                ("138 — MsItemBatchOpening: columns + total opening value", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsItemBatchOpening'
                    ORDER BY ORDINAL_POSITION

                    SELECT
                        COUNT(*)                          AS total_rows,
                        COUNT(DISTINCT ItemID)            AS distinct_items,
                        SUM(OpeningQty)                   AS total_opening_bottles
                    FROM MsItemBatchOpening
                """),
                ("139 — Current stock: opening + purchases - sales - breakages by item", """
                    SELECT
                        m.ItemDescription,
                        b.BrandName,
                        ISNULL(op.opening_bottles, 0)   AS opening_bottles,
                        ISNULL(pur.bought_bottles, 0)   AS purchased_bottles,
                        ISNULL(sal.sold_bottles,   0)   AS sold_bottles,
                        ISNULL(brk.broken_bottles, 0)   AS breakage_bottles,
                        ISNULL(op.opening_bottles, 0)
                            + ISNULL(pur.bought_bottles, 0)
                            - ISNULL(sal.sold_bottles,   0)
                            - ISNULL(brk.broken_bottles, 0) AS net_stock_bottles,
                        m.MrpBottRate
                    FROM MsItemMaster m
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    LEFT JOIN (
                        SELECT ItemID, SUM(OpeningQty) AS opening_bottles
                        FROM MsItemBatchOpening GROUP BY ItemID
                    ) op ON op.ItemID=m.ItemID
                    LEFT JOIN (
                        SELECT i.ItemID, SUM(i.TotalBottleQty) AS bought_bottles
                        FROM TrVocItem i
                        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                        WHERE h.TransTypeID IN (8,10,14,21,22,27,28,30,31,38,49,53)
                          AND ISNULL(h.Cancelled,'N')<>'Y'
                          AND ISNULL(i.FreeItemYN,'N')<>'Y'
                        GROUP BY i.ItemID
                    ) pur ON pur.ItemID=m.ItemID
                    LEFT JOIN (
                        SELECT i.ItemID, SUM(i.TotalBottleQty) AS sold_bottles
                        FROM TrVocItem i
                        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='MS'
                          AND ISNULL(h.Cancelled,'N')<>'Y'
                        GROUP BY i.ItemID
                    ) sal ON sal.ItemID=m.ItemID
                    LEFT JOIN (
                        SELECT i.ItemID, SUM(i.TotalBottleQty) AS broken_bottles
                        FROM TrVocItem i
                        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='SA'
                          AND ISNULL(h.Cancelled,'N')<>'Y'
                        GROUP BY i.ItemID
                    ) brk ON brk.ItemID=m.ItemID
                    WHERE ISNULL(op.opening_bottles,0)+ISNULL(pur.bought_bottles,0)
                          -ISNULL(sal.sold_bottles,0)-ISNULL(brk.broken_bottles,0) > 0
                    ORDER BY net_stock_bottles DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK X — TCS: where it is charged and posted
                # ══════════════════════════════════════════════════════════════
                ("140 — TCS: total collected in FY25-26 (from TrVocDetail — look for TCS account)", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        d.DrCrIndicator,
                        SUM(d.Amount) AS total,
                        COUNT(DISTINCT d.VoucherNo) AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND (  UPPER(ISNULL(p.PartyName,'')) LIKE '%TCS%'
                          OR UPPER(ISNULL(p.PartyName,'')) LIKE '%TAX COLLECTED%'
                          OR UPPER(d.PartyID) LIKE '%TCS%' )
                    GROUP BY ISNULL(p.PartyName,d.PartyID), d.DrCrIndicator
                    ORDER BY total DESC
                """),
                ("141 — Handling charges + other service charges on MS invoices", """
                    SELECT
                        s.ServiceItemName,
                        COUNT(DISTINCT i.VoucherNo) AS invoices,
                        SUM(i.TotalAmount)          AS total_charged,
                        AVG(i.TotalAmount)          AS avg_per_invoice
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsServiceItemMaster s ON s.ServiceItemID=i.ServiceItemID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY s.ServiceItemName
                    ORDER BY total_charged DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK Y — Pending / order management
                # ══════════════════════════════════════════════════════════════
                ("142 — Sales Orders (SO) vs invoices: fulfilment rate", """
                    SELECT
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        COUNT(DISTINCT h.VoucherNo)  AS orders,
                        SUM(i.TotalAmount)           AS order_value,
                        SUM(i.TotalBottleQty)        AS order_bottles
                    FROM TrVocHead h
                    JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='SO'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
                    ORDER BY yr, mo
                """),
                ("143 — Receipt Orders (RO): full structure", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='RO'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
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
                # BLOCK Z — Catch-all: every remaining table not yet covered
                # ══════════════════════════════════════════════════════════════
                ("144 — COMPLETE TABLE INVENTORY: every table + row count via dynamic SQL", """
                    SELECT
                        t.TABLE_NAME,
                        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                         WHERE c.TABLE_NAME=t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                    ORDER BY TABLE_NAME
                """),
                ("145 — Tables with data but not yet studied (row count > 0, not in Tr/Ms/X prefix)", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME NOT LIKE 'Tr%'
                      AND TABLE_NAME NOT LIKE 'Ms%'
                      AND TABLE_NAME NOT LIKE 'X%'
                      AND TABLE_NAME NOT LIKE 'sys%'
                    ORDER BY TABLE_NAME
                """),
                ("146 — CE (cash payment) entries: full account breakdown all FY25-26", """
                    SELECT
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(d.Amount)                   AS total,
                        COUNT(DISTINCT d.VoucherNo)     AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='CE'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY d.DrCrIndicator, ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY d.DrCrIndicator, total DESC
                """),
                ("147 — BP (bank payment) entries: full account breakdown all FY25-26", """
                    SELECT
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(d.Amount)                   AS total,
                        COUNT(DISTINCT d.VoucherNo)     AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY d.DrCrIndicator, ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY d.DrCrIndicator, total DESC
                """),
                ("148 — JV (journal entry) entries: full account breakdown all FY25-26", """
                    SELECT
                        d.DrCrIndicator,
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(d.Amount)                   AS total,
                        COUNT(DISTINCT d.VoucherNo)     AS vouchers,
                        MIN(h.Narration)                AS sample_narration
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='JV'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY d.DrCrIndicator, ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY d.DrCrIndicator, total DESC
                """),
                ("149 — Sales with discount/net: if TrVocItem has gross+discount columns show them", """
                    SELECT TOP 30
                        h.VoucherDate, h.VoucherNo,
                        m.ItemDescription, b.BrandName,
                        i.*
                    FROM TrVocItem i
                    JOIN TrVocHead h   ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    LEFT JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY h.VoucherDate DESC, i.VoucherNo, i.SerialNo
                """),
                ("150 — CE: complete sample voucher with all detail (cash payment anatomy)", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CE'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
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

                # ══════════════════════════════════════════════════════════════
                # BLOCK AA — Item pricing: rate masters, excise rates, MRP
                # ══════════════════════════════════════════════════════════════
                ("151 — MsItemMaster: all 30 rows with every column (pricing, excise, size)", """
                    SELECT TOP 30 * FROM MsItemMaster ORDER BY ItemID
                """),
                ("152 — Rate/pricing tables: discover any rate master tables", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Rate%'
                          OR TABLE_NAME LIKE '%Price%'
                          OR TABLE_NAME LIKE '%MRP%'
                          OR TABLE_NAME LIKE '%Tariff%'
                          OR TABLE_NAME LIKE '%Duty%'
                          OR TABLE_NAME LIKE '%Excise%' )
                    ORDER BY TABLE_NAME
                """),
                ("153 — How CaseRate/BottleRate on TrVocItem compares to MsItemMaster MRP", """
                    SELECT TOP 20
                        m.ItemDescription,
                        m.MrpBottRate  AS master_mrp_bott,
                        m.MrpCaseRate  AS master_mrp_case,
                        AVG(i.BottleRate)   AS avg_billed_bott,
                        AVG(i.CaseRate)     AS avg_billed_case,
                        MIN(i.BottleRate)   AS min_billed_bott,
                        MAX(i.BottleRate)   AS max_billed_bott,
                        COUNT(DISTINCT i.VoucherNo) AS invoices
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY m.ItemDescription, m.MrpBottRate, m.MrpCaseRate
                    ORDER BY invoices DESC
                """),
                ("154 — Items where billed rate differs from MRP (discount/surcharge detection)", """
                    SELECT TOP 30
                        m.ItemDescription, b.BrandName,
                        m.MrpBottRate,
                        i.BottleRate AS billed_rate,
                        m.MrpBottRate - i.BottleRate AS diff,
                        h.VoucherDate, h.VoucherNo,
                        p.PartyName AS customer
                    FROM TrVocItem i
                    JOIN TrVocHead h   ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    LEFT JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID
                                           AND d.VoucherNo=h.VoucherNo
                                           AND d.DrCrIndicator='D'
                                           AND LEFT(d.PartyID,1)='D'
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND i.BottleRate <> m.MrpBottRate
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY ABS(m.MrpBottRate - i.BottleRate) DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AB — Batch management: how stock batches are tracked
                # ══════════════════════════════════════════════════════════════
                ("155 — MsBatchMaster: ALL columns + 20 sample rows", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsBatchMaster'
                    ORDER BY ORDINAL_POSITION

                    SELECT TOP 20 b.*, m.ItemDescription
                    FROM MsBatchMaster b
                    LEFT JOIN MsItemMaster m ON m.ItemID=b.ItemID
                    ORDER BY b.BatchID DESC
                """),
                ("156 — Batch flow: same BatchID traced from purchase through sale", """
                    SELECT TOP 20
                        t.ShortName, h.VoucherDate, h.VoucherNo,
                        i.BatchID, i.TotalBottleQty,
                        m.ItemDescription, b.BrandName
                    FROM TrVocItem i
                    JOIN TrVocHead h   ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE i.BatchID IS NOT NULL AND i.BatchID <> 0
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY i.BatchID, h.VoucherDate
                """),
                ("157 — Batch-wise stock: net bottles per BatchID (positive = still in stock)", """
                    SELECT
                        i.BatchID,
                        m.ItemDescription, b.BrandName,
                        SUM(CASE WHEN h.TransTypeID IN (8,10,14,21,22,27,28,30,31,38,49,53)
                                 THEN i.TotalBottleQty
                                 ELSE -i.TotalBottleQty END) AS net_bottles,
                        MIN(pur_date.VoucherDate) AS purchase_date
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    LEFT JOIN (
                        SELECT TransTypeID, VoucherNo, VoucherDate FROM TrVocHead
                    ) pur_date ON pur_date.TransTypeID=h.TransTypeID
                               AND pur_date.VoucherNo=h.VoucherNo
                    WHERE ISNULL(h.Cancelled,'N')<>'Y'
                      AND i.BatchID IS NOT NULL AND i.BatchID<>0
                    GROUP BY i.BatchID, m.ItemDescription, b.BrandName
                    HAVING SUM(CASE WHEN h.TransTypeID IN (8,10,14,21,22,27,28,30,31,38,49,53)
                                    THEN i.TotalBottleQty ELSE -i.TotalBottleQty END) > 0
                    ORDER BY net_bottles DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AC — Bank/cheque details on receipts and payments
                # ══════════════════════════════════════════════════════════════
                ("158 — BR/CR receipts: what extra columns does TrVocHead have for cheque details?", """
                    SELECT TOP 10 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BR'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),
                ("159 — Bounced cheques: RO (Return Order / Return Cheque) entries", """
                    SELECT
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        COUNT(DISTINCT h.VoucherNo) AS vouchers,
                        SUM(d.Amount)               AS bounced_amount
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                    WHERE t.ShortName IN ('RO','BP')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND (  UPPER(ISNULL(h.Narration,'')) LIKE '%BOUNCE%'
                          OR UPPER(ISNULL(h.Narration,'')) LIKE '%RETURN%'
                          OR UPPER(ISNULL(h.Narration,'')) LIKE '%DISHON%' )
                    GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate)
                    ORDER BY yr, mo
                """),
                ("160 — Bank accounts in use: all accounts that appear in BR/BP entries", """
                    SELECT
                        t.ShortName,
                        ISNULL(p.PartyName, d.PartyID) AS bank_account,
                        d.DrCrIndicator,
                        SUM(d.Amount)               AS total,
                        COUNT(DISTINCT d.VoucherNo) AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BR','BP')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND LEFT(d.PartyID,1) NOT IN ('D','C')
                    GROUP BY t.ShortName, ISNULL(p.PartyName,d.PartyID), d.DrCrIndicator
                    ORDER BY t.ShortName, total DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AD — Customer ledger: exact statement logic
                # ══════════════════════════════════════════════════════════════
                ("161 — Customer statement simulation: pick top debtor, show running ledger", """
                    SELECT TOP 1 op.PartyID INTO #top_debtor
                    FROM MsPartyOpening op WHERE LEFT(op.PartyID,1)='D'
                    ORDER BY op.CloseBalTmp DESC

                    SELECT
                        h.VoucherDate,
                        t.ShortName AS type,
                        h.VoucherNo,
                        h.Narration,
                        CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END AS debit,
                        CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END AS credit,
                        d.RemainingAmt AS balance_on_line
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN #top_debtor td ON td.PartyID=d.PartyID
                    WHERE ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    ORDER BY h.VoucherDate, h.VoucherNo

                    DROP TABLE #top_debtor
                """),
                ("162 — Outstanding per invoice: RemainingAmt > 0 with age for top customer", """
                    SELECT TOP 50
                        p.PartyName AS customer,
                        h.VoucherDate,
                        COALESCE(h.TPDate, h.VoucherDate) AS dispatch_date,
                        t.ShortName,
                        h.VoucherNo,
                        d.Amount           AS invoice_amount,
                        d.RemainingAmt     AS still_outstanding,
                        DATEDIFF(DAY, COALESCE(h.TPDate,h.VoucherDate), GETDATE()) AS days_outstanding
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE LEFT(d.PartyID,1)='D'
                      AND d.DrCrIndicator='D'
                      AND d.RemainingAmt > 0
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND t.ShortName NOT IN ('BR','CR')
                    ORDER BY days_outstanding DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AE — Returns: CN to customer, DN from supplier
                # ══════════════════════════════════════════════════════════════
                ("163 — CN type breakdown: customer returns vs supplier CN", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        CASE WHEN LEFT(d.PartyID,1)='D' THEN 'To Customer'
                             WHEN LEFT(d.PartyID,1)='C' THEN 'From Supplier'
                             ELSE 'GL' END AS direction,
                        d.DrCrIndicator,
                        COUNT(*) AS rows,
                        SUM(d.Amount) AS total,
                        COUNT(DISTINCT d.VoucherNo) AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CN'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName,
                        CASE WHEN LEFT(d.PartyID,1)='D' THEN 'To Customer'
                             WHEN LEFT(d.PartyID,1)='C' THEN 'From Supplier'
                             ELSE 'GL' END,
                        d.DrCrIndicator
                    ORDER BY total DESC
                """),
                ("164 — DN type breakdown: debit note to customer vs from supplier", """
                    SELECT
                        t.ShortName, t.TransTypeName,
                        CASE WHEN LEFT(d.PartyID,1)='D' THEN 'On Customer'
                             WHEN LEFT(d.PartyID,1)='C' THEN 'From Supplier'
                             ELSE 'GL' END AS direction,
                        d.DrCrIndicator,
                        COUNT(*) AS rows,
                        SUM(d.Amount) AS total,
                        COUNT(DISTINCT d.VoucherNo) AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='DN'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName,
                        CASE WHEN LEFT(d.PartyID,1)='D' THEN 'On Customer'
                             WHEN LEFT(d.PartyID,1)='C' THEN 'From Supplier'
                             ELSE 'GL' END,
                        d.DrCrIndicator
                    ORDER BY total DESC
                """),
                ("165 — CN to customer: do they reverse TrVocItem lines (stock goes back)?", """
                    SELECT
                        CASE WHEN vi.VoucherNo IS NOT NULL THEN 'Has item lines'
                             ELSE 'No item lines' END AS has_items,
                        COUNT(DISTINCT h.VoucherNo)   AS vouchers,
                        SUM(vi.TotalBottleQty)        AS bottles,
                        SUM(vi.TotalAmount)           AS value
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrVocItem vi ON vi.TransTypeID=h.TransTypeID AND vi.VoucherNo=h.VoucherNo
                    WHERE t.ShortName='CN'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY CASE WHEN vi.VoucherNo IS NOT NULL THEN 'Has item lines'
                                  ELSE 'No item lines' END
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AF — Supplier/creditor ledger and payables
                # ══════════════════════════════════════════════════════════════
                ("166 — Supplier statement simulation: top creditor running ledger", """
                    SELECT TOP 50
                        h.VoucherDate,
                        t.ShortName,
                        h.VoucherNo,
                        h.Narration,
                        CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END AS debit,
                        CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END AS credit,
                        d.RemainingAmt
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE d.PartyID = (
                        SELECT TOP 1 d2.PartyID
                        FROM TrVocDetail d2
                        JOIN TrVocHead h2 ON h2.TransTypeID=d2.TransTypeID AND h2.VoucherNo=d2.VoucherNo
                        WHERE LEFT(d2.PartyID,1)='C'
                          AND d2.DrCrIndicator='C' AND d2.RemainingAmt>0
                          AND ISNULL(h2.Cancelled,'N')<>'Y'
                        GROUP BY d2.PartyID
                        ORDER BY SUM(d2.RemainingAmt) DESC
                    )
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    ORDER BY h.VoucherDate, h.VoucherNo
                """),
                ("167 — Supplier payables ageing (mirror of debtors ageing)", """
                    SELECT
                        p.PartyName AS supplier,
                        SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) BETWEEN  0 AND  30
                                 THEN d.RemainingAmt ELSE 0 END) AS d0_30,
                        SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) BETWEEN 31 AND  60
                                 THEN d.RemainingAmt ELSE 0 END) AS d31_60,
                        SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE()) BETWEEN 61 AND  90
                                 THEN d.RemainingAmt ELSE 0 END) AS d61_90,
                        SUM(CASE WHEN DATEDIFF(DAY,h.VoucherDate,GETDATE())  > 90
                                 THEN d.RemainingAmt ELSE 0 END) AS d90_plus,
                        SUM(d.RemainingAmt) AS total_payable
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE LEFT(d.PartyID,1)='C'
                      AND d.DrCrIndicator='C'
                      AND d.RemainingAmt>0
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND t.ShortName IN ('PU','BP','CE')
                    GROUP BY p.PartyName
                    ORDER BY total_payable DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AG — TCS: threshold detection and invoice-level posting
                # ══════════════════════════════════════════════════════════════
                ("168 — TCS: which customers were charged TCS in FY25-26", """
                    SELECT
                        p.PartyName AS customer,
                        si.ServiceItemName,
                        COUNT(DISTINCT i.VoucherNo) AS invoices_with_tcs,
                        SUM(i.TotalAmount)          AS total_tcs_charged
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsServiceItemMaster si ON si.ServiceItemID=i.ServiceItemID
                    LEFT JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID
                                           AND d.VoucherNo=h.VoucherNo
                                           AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND UPPER(si.ServiceItemName) LIKE '%TCS%'
                    GROUP BY p.PartyName, si.ServiceItemName
                    ORDER BY total_tcs_charged DESC
                """),
                ("169 — TCS: cumulative sales per customer to find who crossed ₹50L threshold", """
                    SELECT
                        p.PartyName AS customer,
                        SUM(i.TotalAmount)          AS fy_sales,
                        COUNT(DISTINCT h.VoucherNo) AS invoices
                    FROM TrVocItem i
                    JOIN TrVocHead h   ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID
                                           AND d.VoucherNo=h.VoucherNo
                                           AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY p.PartyName
                    HAVING SUM(i.TotalAmount) >= 5000000
                    ORDER BY fy_sales DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AH — Excise on sales: exact posting per invoice
                # ══════════════════════════════════════════════════════════════
                ("170 — Excise on MS invoices: what accounts are credited (where excise goes)", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(d.Amount)                   AS total,
                        COUNT(DISTINCT d.VoucherNo)     AS vouchers
                    FROM TrVocDetail d
                    JOIN TrVocHead h   ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND d.DrCrIndicator='C'
                      AND LEFT(d.PartyID,1) NOT IN ('D')
                    GROUP BY ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY total DESC
                """),
                ("171 — MS invoice: customer DR total vs sum of all CR accounts (should balance)", """
                    SELECT
                        h.VoucherNo,
                        h.VoucherDate,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_dr,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_cr,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END)
                        - SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS diff
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY h.VoucherNo, h.VoucherDate
                    HAVING ABS(SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END)
                               - SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END)) > 0.01
                    ORDER BY diff DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AI — Salesman targets and incentive structure
                # ══════════════════════════════════════════════════════════════
                ("172 — MsSalesmanMaster: all rows with all columns", """
                    SELECT * FROM MsSalesmanMaster ORDER BY SalesManID
                """),
                ("173 — Salesman area/route assignment table discovery", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%SalesmanArea%'
                          OR TABLE_NAME LIKE '%SalesmanRoute%'
                          OR TABLE_NAME LIKE '%SalesmanCustomer%'
                          OR TABLE_NAME LIKE '%ManArea%'
                          OR TABLE_NAME LIKE '%ManRoute%' )
                    ORDER BY TABLE_NAME
                """),
                ("174 — Salesman: brand-wise sales performance in FY25-26", """
                    SELECT
                        s.FullName AS salesman,
                        b.BrandName,
                        SUM(i.TotalBottleQty) AS bottles,
                        SUM(i.TotalAmount)    AS value
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY s.FullName, b.BrandName
                    ORDER BY s.FullName, value DESC
                """),
                ("175 — Salesman: new customers acquired in FY25-26 (first invoice date)", """
                    SELECT
                        s.FullName AS salesman,
                        COUNT(DISTINCT p.PartyID) AS new_customers
                    FROM MsPartyMaster p
                    JOIN MsSalesmanMaster s ON s.SalesManID=p.SalesManID
                    WHERE LEFT(p.PartyID,1)='D'
                      AND EXISTS (
                          SELECT 1 FROM TrVocHead h
                          JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                          JOIN MsTransType t ON t.id_key=h.TransTypeID
                          WHERE t.ShortName='MS'
                            AND d.PartyID=p.PartyID
                            AND ISNULL(h.Cancelled,'N')<>'Y'
                            AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM TrVocHead h2
                          JOIN TrVocDetail d2 ON d2.TransTypeID=h2.TransTypeID AND d2.VoucherNo=h2.VoucherNo
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='MS'
                            AND d2.PartyID=p.PartyID
                            AND ISNULL(h2.Cancelled,'N')<>'Y'
                            AND h2.VoucherDate<'2025-04-01'
                      )
                    GROUP BY s.FullName
                    ORDER BY new_customers DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AJ — User access: what each user ID can do
                # ══════════════════════════════════════════════════════════════
                ("176 — MsUserMaster: all columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsUserMaster'
                    ORDER BY ORDINAL_POSITION
                """),
                ("177 — MsUserMaster: full dump (who are the users?)", """
                    SELECT * FROM MsUserMaster ORDER BY 1
                """),
                ("178 — MsUserRights: all columns + full dump", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsUserRights'
                    ORDER BY ORDINAL_POSITION

                    SELECT * FROM MsUserRights ORDER BY 1
                """),
                ("179 — User-TransType access: which users can post which transaction types", """
                    SELECT
                        u.UserName,
                        t.ShortName, t.TransTypeName,
                        r.*
                    FROM MsUserRights r
                    JOIN MsUserMaster u ON u.UserID=r.UserID
                    JOIN MsTransType  t ON t.id_key=r.TransTypeID
                    ORDER BY u.UserName, t.ShortName
                """),
                ("180 — Audit: who posted the most vouchers in FY25-26", """
                    SELECT
                        ISNULL(h.CreatedBy, h.UserID) AS user_id,
                        t.ShortName,
                        COUNT(DISTINCT h.VoucherNo)   AS vouchers,
                        SUM(i.TotalAmount)            AS total_value
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    WHERE ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY ISNULL(h.CreatedBy, h.UserID), t.ShortName
                    ORDER BY vouchers DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AK — "LIVE TEST" capture queries
                #   Run these BEFORE and AFTER doing something on the ERP
                #   front-end, then compare to see exactly what changed.
                # ══════════════════════════════════════════════════════════════
                ("181 — [LIVE TEST] Most recent 5 vouchers across ALL types (run after any entry)", """
                    SELECT TOP 5
                        h.VoucherDate, h.VoucherNo,
                        t.ShortName, t.TransTypeName,
                        h.Narration,
                        h.Cancelled,
                        h.VoucherFlag
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC
                """),
                ("182 — [LIVE TEST] Latest MS invoice: complete head + item + detail", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS' AND ISNULL(h.Cancelled,'N')<>'Y'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC

                    SELECT 'HEAD' AS s, h.* FROM TrVocHead h
                    WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS s, i.*, m.ItemDescription, b.BrandName, sv.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m        ON m.ItemID=i.ItemID
                    LEFT JOIN MsBrandMaster b        ON b.BrandID=m.BrandID
                    LEFT JOIN MsServiceItemMaster sv ON sv.ServiceItemID=i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS s, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),
                ("183 — [LIVE TEST] What changed in last 30 minutes (any new/modified rows)", """
                    SELECT TOP 20
                        h.VoucherDate,
                        CAST(h.VoucherNo AS VARCHAR) AS VoucherNo,
                        t.ShortName,
                        h.Narration,
                        h.Cancelled,
                        h.VoucherFlag
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= CAST(GETDATE() AS DATE)
                    ORDER BY h.VoucherNo DESC
                """),
                ("184 — [LIVE TEST] Latest BP/CE voucher: excise or expense?", """
                    DECLARE @tid INT, @vno VARCHAR(50)
                    SELECT TOP 1 @tid=h.TransTypeID, @vno=h.VoucherNo
                    FROM TrVocHead h JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName IN ('BP','CE') AND ISNULL(h.Cancelled,'N')<>'Y'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC

                    SELECT 'HEAD' AS s, h.* FROM TrVocHead h
                    WHERE h.TransTypeID=@tid AND h.VoucherNo=@vno

                    SELECT 'ITEM' AS s, i.*, m.ItemDescription, sv.ServiceItemName
                    FROM TrVocItem i
                    LEFT JOIN MsItemMaster m        ON m.ItemID=i.ItemID
                    LEFT JOIN MsServiceItemMaster sv ON sv.ServiceItemID=i.ServiceItemID
                    WHERE i.TransTypeID=@tid AND i.VoucherNo=@vno

                    SELECT 'DETAIL' AS s, d.*, p.PartyName AS account_name
                    FROM TrVocDetail d
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE d.TransTypeID=@tid AND d.VoucherNo=@vno
                    ORDER BY d.DrCrIndicator DESC, d.Amount DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AL — ERP reports: replicate each standard report
                # ══════════════════════════════════════════════════════════════
                ("185 — ERP Sales Register equivalent: party+brand+size+qty+value FY25-26", """
                    SELECT
                        p.PartyName                             AS customer,
                        b.BrandName,
                        sz.SizeType,
                        lt.LiquorType,
                        SUM(i.CaseQty)          AS cases,
                        SUM(i.TotalBottleQty)   AS bottles,
                        SUM(i.TotalAmount)      AS gross_value,
                        COUNT(DISTINCT h.VoucherNo) AS invoices
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    LEFT JOIN MsSizeType sz  ON sz.SizeTypeID=m.SizeTypeID
                    LEFT JOIN MsLiquorType lt ON lt.LiquorTypeID=m.LiquorTypeID
                    LEFT JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID
                                           AND d.VoucherNo=h.VoucherNo
                                           AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY p.PartyName, b.BrandName, sz.SizeType, lt.LiquorType
                    ORDER BY gross_value DESC
                """),
                ("186 — ERP Purchase Register equivalent: supplier+brand+qty+value FY25-26", """
                    SELECT
                        p.PartyName    AS supplier,
                        b.BrandName,
                        sz.SizeType,
                        SUM(i.CaseQty)        AS cases,
                        SUM(i.TotalBottleQty) AS bottles,
                        SUM(i.TotalAmount)    AS value,
                        COUNT(DISTINCT h.VoucherNo) AS invoices
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsItemMaster m  ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    LEFT JOIN MsSizeType sz ON sz.SizeTypeID=m.SizeTypeID
                    LEFT JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID
                                           AND d.VoucherNo=h.VoucherNo
                                           AND d.DrCrIndicator='C' AND LEFT(d.PartyID,1)='C'
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE h.TransTypeID IN (8,10,14,21,22,27,28,30,31,38,49,53)
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY p.PartyName, b.BrandName, sz.SizeType
                    ORDER BY value DESC
                """),
                ("187 — ERP Collection Report equivalent: collections by salesman by month", """
                    SELECT
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        s.FullName AS salesman,
                        SUM(d.Amount) AS collected,
                        COUNT(DISTINCT h.VoucherNo) AS receipts
                    FROM TrVocDetail d
                    JOIN TrVocHead h    ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    LEFT JOIN MsSalesmanMaster s ON s.SalesManID=h.SalesManID
                    WHERE t.ShortName IN ('BR','CR')
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND d.DrCrIndicator='D' AND LEFT(d.PartyID,1)='D'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate), s.FullName
                    ORDER BY yr, mo, collected DESC
                """),
                ("188 — ERP Stock Report equivalent: current stock brand-size-wise with value", """
                    SELECT
                        b.BrandName,
                        sz.SizeType,
                        lt.LiquorType,
                        COUNT(DISTINCT m.ItemID)  AS skus,
                        SUM(ISNULL(op.opening_bottles,0)
                            + ISNULL(pur.bought,0)
                            - ISNULL(sal.sold,0)
                            - ISNULL(brk.broken,0)) AS net_bottles,
                        SUM((ISNULL(op.opening_bottles,0)
                            + ISNULL(pur.bought,0)
                            - ISNULL(sal.sold,0)
                            - ISNULL(brk.broken,0)) * m.MrpBottRate) AS mrp_value
                    FROM MsItemMaster m
                    JOIN MsBrandMaster b   ON b.BrandID=m.BrandID
                    LEFT JOIN MsSizeType sz ON sz.SizeTypeID=m.SizeTypeID
                    LEFT JOIN MsLiquorType lt ON lt.LiquorTypeID=m.LiquorTypeID
                    LEFT JOIN (SELECT ItemID, SUM(OpeningQty) AS opening_bottles
                               FROM MsItemBatchOpening GROUP BY ItemID) op ON op.ItemID=m.ItemID
                    LEFT JOIN (SELECT ItemID, SUM(TotalBottleQty) AS bought FROM TrVocItem vi
                               JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                               WHERE h.TransTypeID IN (8,10,14,21,22,27,28,30,31,38,49,53)
                                 AND ISNULL(h.Cancelled,'N')<>'Y'
                               GROUP BY ItemID) pur ON pur.ItemID=m.ItemID
                    LEFT JOIN (SELECT ItemID, SUM(TotalBottleQty) AS sold FROM TrVocItem vi
                               JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                               JOIN MsTransType t ON t.id_key=h.TransTypeID
                               WHERE t.ShortName='MS' AND ISNULL(h.Cancelled,'N')<>'Y'
                               GROUP BY ItemID) sal ON sal.ItemID=m.ItemID
                    LEFT JOIN (SELECT ItemID, SUM(TotalBottleQty) AS broken FROM TrVocItem vi
                               JOIN TrVocHead h ON h.TransTypeID=vi.TransTypeID AND h.VoucherNo=vi.VoucherNo
                               JOIN MsTransType t ON t.id_key=h.TransTypeID
                               WHERE t.ShortName='SA' AND ISNULL(h.Cancelled,'N')<>'Y'
                               GROUP BY ItemID) brk ON brk.ItemID=m.ItemID
                    GROUP BY b.BrandName, sz.SizeType, lt.LiquorType
                    HAVING SUM(ISNULL(op.opening_bottles,0)+ISNULL(pur.bought,0)
                               -ISNULL(sal.sold,0)-ISNULL(brk.broken,0)) > 0
                    ORDER BY mrp_value DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AM — P&L, balance sheet, trial balance logic
                # ══════════════════════════════════════════════════════════════
                ("189 — Trial balance: net balance per account across all vouchers FY25-26", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_dr,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_cr
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY ABS(SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END)) DESC
                """),
                ("190 — P&L accounts: revenue and expense totals (all non-D%, non-C% accounts)", """
                    SELECT
                        ISNULL(p.PartyName, d.PartyID) AS account,
                        LEFT(d.PartyID,2)               AS prefix,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount
                                 ELSE -d.Amount END) AS net_credit,
                        SUM(d.Amount) AS gross_activity
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND LEFT(d.PartyID,1) NOT IN ('D','C')
                      AND ISNULL(d.PartyID,'')<>''
                    GROUP BY ISNULL(p.PartyName,d.PartyID), LEFT(d.PartyID,2)
                    ORDER BY gross_activity DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AN — Cancelled vouchers analysis
                # ══════════════════════════════════════════════════════════════
                ("191 — Cancelled vouchers: how many, which types, by month", """
                    SELECT
                        YEAR(h.VoucherDate) AS yr, MONTH(h.VoucherDate) AS mo,
                        t.ShortName,
                        COUNT(*) AS cancelled_vouchers,
                        SUM(i.TotalAmount) AS cancelled_value
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    WHERE ISNULL(h.Cancelled,'N')='Y'
                      AND h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY YEAR(h.VoucherDate), MONTH(h.VoucherDate), t.ShortName
                    ORDER BY yr, mo, t.ShortName
                """),
                ("192 — VoucherFlag: count per flag value per type — what each flag means", """
                    SELECT
                        ISNULL(NULLIF(RTRIM(h.VoucherFlag),''),'(blank)') AS flag,
                        t.ShortName,
                        COUNT(*) AS vouchers,
                        MIN(h.Narration) AS sample_narration
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY ISNULL(NULLIF(RTRIM(h.VoucherFlag),''),'(blank)'), t.ShortName
                    ORDER BY flag, t.ShortName
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AO — Anything else: exhaustive final sweep
                # ══════════════════════════════════════════════════════════════
                ("193 — All distinct Narration patterns in TrVocHead (shows workflow vocabulary)", """
                    SELECT TOP 100
                        t.ShortName,
                        LEFT(RTRIM(h.Narration),80) AS narration_sample,
                        COUNT(*)                    AS frequency
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                      AND h.Narration IS NOT NULL AND RTRIM(h.Narration)<>''
                    GROUP BY t.ShortName, LEFT(RTRIM(h.Narration),80)
                    ORDER BY frequency DESC
                """),
                ("194 — MsPartyOpening: all columns + 10 sample rows", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsPartyOpening'
                    ORDER BY ORDINAL_POSITION

                    SELECT TOP 10 * FROM MsPartyOpening ORDER BY 1
                """),
                ("195 — CloseBal vs CloseBalTmp: how different are they right now?", """
                    SELECT
                        COUNT(*) AS parties,
                        SUM(CloseBal)      AS fy_end_bal,
                        SUM(CloseBalTmp)   AS live_bal,
                        SUM(CloseBalTmp) - SUM(CloseBal) AS difference
                    FROM MsPartyOpening
                    WHERE LEFT(PartyID,1)='D'
                """),
                ("196 — InvoiceNo vs VoucherNo vs TPNo: which is used for what", """
                    SELECT TOP 20
                        h.VoucherNo, h.InvoiceNo, h.TPNo, h.TPDate,
                        t.ShortName, h.VoucherDate, h.Narration
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),
                ("197 — All tables prefixed with anything other than Tr/Ms/X — full list", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND LEFT(TABLE_NAME,2) NOT IN ('Tr','Ms','X_','XM')
                      AND LEFT(TABLE_NAME,1) <> 'X'
                    ORDER BY TABLE_NAME
                """),
                ("198 — How many vouchers have BOTH a linked parent doc (ParentDocDet set)?", """
                    SELECT
                        t.ShortName,
                        COUNT(CASE WHEN h.ParentDocDet IS NOT NULL
                                    AND RTRIM(h.ParentDocDet)<>'' THEN 1 END) AS with_parent,
                        COUNT(*) AS total,
                        MIN(h.ParentDocDet) AS sample_parent
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY t.ShortName
                    ORDER BY with_parent DESC
                """),
                ("199 — GSTNo field on TrVocHead: populated on which transaction types?", """
                    SELECT
                        t.ShortName,
                        COUNT(CASE WHEN h.GSTNo IS NOT NULL AND h.GSTNo<>'' THEN 1 END) AS with_gst,
                        COUNT(*) AS total,
                        MIN(h.GSTNo) AS sample_gst
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY t.ShortName
                    ORDER BY with_gst DESC
                """),
                ("200 — FINAL: complete voucher count and value summary across all types FY25-26", """
                    SELECT
                        t.ShortName,
                        t.TransTypeName,
                        COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                        COUNT(DISTINCT CASE WHEN ISNULL(h.Cancelled,'N')='Y'
                              THEN CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo END) AS cancelled,
                        SUM(ISNULL(i.TotalAmount,0))    AS item_total,
                        SUM(ISNULL(i.TotalBottleQty,0)) AS bottles,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_dr,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_cr
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN TrVocItem i   ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                    LEFT JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                    WHERE h.VoucherDate>='2025-04-01' AND h.VoucherDate<'2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName
                    ORDER BY item_total DESC
                """),

                # ══════════════════════════════════════════════════════════════
                # BLOCK AP — Item rates: find the exact stored rate columns
                #   The ERP stores purchase rate, sale rate, valuation rate as
                #   columns on MsItemMaster (and possibly MsBatchMaster).
                #   We read them directly — no calculation needed.
                # ══════════════════════════════════════════════════════════════
                ("201 — MsItemMaster: ALL columns with type — find every rate field", """
                    SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsItemMaster'
                    ORDER BY ORDINAL_POSITION
                """),
                ("202 — MsItemMaster: TOP 30 rows — all stored rates as-is", """
                    SELECT TOP 30 * FROM MsItemMaster ORDER BY ItemID
                """),
                ("203 — MsItemMaster: purchase rate, sale rate, valuation rate — all numeric fields", """
                    SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsItemMaster'
                      AND DATA_TYPE IN ('decimal','numeric','float','money','smallmoney','int','bigint')
                    ORDER BY ORDINAL_POSITION
                """),
                ("204 — MsItemMaster: all items with every rate column (read stored values directly)", """
                    SELECT
                        m.ItemID, m.ItemDescription,
                        b.BrandName,
                        lt.LiquorType,
                        sz.SizeType,
                        m.*
                    FROM MsItemMaster m
                    LEFT JOIN MsBrandMaster b  ON b.BrandID=m.BrandID
                    LEFT JOIN MsLiquorType lt  ON lt.LiquorTypeID=m.LiquorTypeID
                    LEFT JOIN MsSizeType sz    ON sz.SizeTypeID=m.SizeTypeID
                    ORDER BY b.BrandName, m.ItemDescription
                """),
                ("205 — MsBatchMaster: all numeric columns — does each batch carry its own rates?", """
                    SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsBatchMaster'
                      AND DATA_TYPE IN ('decimal','numeric','float','money','smallmoney','int','bigint')
                    ORDER BY ORDINAL_POSITION
                """),
                ("206 — MsBatchMaster: full dump of all rows with item names", """
                    SELECT b.*, m.ItemDescription, br.BrandName
                    FROM MsBatchMaster b
                    LEFT JOIN MsItemMaster m  ON m.ItemID=b.ItemID
                    LEFT JOIN MsBrandMaster br ON br.BrandID=m.BrandID
                    ORDER BY b.BatchID DESC
                """),
                ("207 — TrVocItem: all numeric columns — what rate/amount fields are on each line?", """
                    SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocItem'
                      AND DATA_TYPE IN ('decimal','numeric','float','money','smallmoney','int','bigint')
                    ORDER BY ORDINAL_POSITION
                """),
                ("208 — Purchase bill line items: all columns as stored (read exactly what ERP saved)", """
                    SELECT TOP 30
                        h.VoucherDate, h.VoucherNo,
                        t.ShortName,
                        i.*,
                        m.ItemDescription, b.BrandName
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    JOIN MsItemMaster m ON m.ItemID=i.ItemID
                    JOIN MsBrandMaster b ON b.BrandID=m.BrandID
                    WHERE h.TransTypeID IN (8,10,14,21,22,27,28,30,31,38,49,53)
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY h.VoucherDate DESC, i.VoucherNo, i.SerialNo
                """),
                ("209 — Sale invoice line items: all columns as stored (read exactly what ERP saved)", """
                    SELECT TOP 30
                        h.VoucherDate, h.VoucherNo,
                        i.*,
                        m.ItemDescription, b.BrandName,
                        sv.ServiceItemName
                    FROM TrVocItem i
                    JOIN TrVocHead h    ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t  ON t.id_key=h.TransTypeID
                    LEFT JOIN MsItemMaster m        ON m.ItemID=i.ItemID
                    LEFT JOIN MsBrandMaster b        ON b.BrandID=m.BrandID
                    LEFT JOIN MsServiceItemMaster sv ON sv.ServiceItemID=i.ServiceItemID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N')<>'Y'
                      AND ISNULL(i.FreeItemYN,'N')<>'Y'
                      AND h.VoucherDate>='2025-04-01'
                    ORDER BY h.VoucherDate DESC, i.VoucherNo, i.SerialNo
                """),
                ("210 — Stock valuation as the ERP computes it: read from MsPartyOpening equivalent for stock", """
                    -- Check if there is a dedicated stock valuation table
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (  TABLE_NAME LIKE '%Stock%'
                          OR TABLE_NAME LIKE '%Valuation%'
                          OR TABLE_NAME LIKE '%Inventory%'
                          OR TABLE_NAME LIKE '%Closing%'
                          OR TABLE_NAME LIKE '%Opening%' )
                    ORDER BY TABLE_NAME
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK Q — Chart of Accounts / Account Group Hierarchy
                # ════════════════════════════════════════════════════════════
                ("211 — All tables whose name contains Account / Group / Head / Ledger", """
                    SELECT TABLE_NAME,
                           (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                            WHERE TABLE_NAME = t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Account%'
                           OR TABLE_NAME LIKE '%Group%'
                           OR TABLE_NAME LIKE '%Head%'
                           OR TABLE_NAME LIKE '%Ledger%'
                           OR TABLE_NAME LIKE '%COA%'
                           OR TABLE_NAME LIKE '%Chart%')
                    ORDER BY TABLE_NAME
                """),

                ("212 — MsAccountHead: all columns + every row (account master)", """
                    SELECT * FROM MsAccountHead ORDER BY 1
                """),

                ("213 — Account group hierarchy: does MsAccountHead have a parent/group column?", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'MsAccountHead'
                    ORDER BY ORDINAL_POSITION
                """),

                ("214 — MsGroupMaster or equivalent: find any group/nature hierarchy table", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%MsGroup%'
                           OR TABLE_NAME LIKE '%AccountGroup%'
                           OR TABLE_NAME LIKE '%AccGroup%'
                           OR TABLE_NAME LIKE '%NatureMaster%'
                           OR TABLE_NAME LIKE '%AccountNature%')
                    ORDER BY TABLE_NAME
                """),

                ("215 — All distinct account types / natures in MsAccountHead (Nature/Type/Category col)", """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsAccountHead'
                      AND (COLUMN_NAME LIKE '%Nature%'
                           OR COLUMN_NAME LIKE '%Type%'
                           OR COLUMN_NAME LIKE '%Category%'
                           OR COLUMN_NAME LIKE '%Group%'
                           OR COLUMN_NAME LIKE '%Parent%'
                           OR COLUMN_NAME LIKE '%Head%')
                    ORDER BY ORDINAL_POSITION
                """),

                ("216 — TrVocDetail: all distinct AccountID / PartyID patterns (which accounts get hit)", """
                    SELECT TOP 200
                        d.PartyID,
                        LEFT(d.PartyID,1) AS prefix,
                        d.DrCrIndicator,
                        t.ShortName,
                        COUNT(*) AS entries
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= '2025-04-01' AND h.VoucherDate < '2026-04-01'
                    GROUP BY d.PartyID, LEFT(d.PartyID,1), d.DrCrIndicator, t.ShortName
                    ORDER BY entries DESC
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK R — ERP Configuration & Settings Tables
                # ════════════════════════════════════════════════════════════
                ("217 — All settings / config / company tables", """
                    SELECT TABLE_NAME,
                           (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                            WHERE TABLE_NAME = t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Setting%'
                           OR TABLE_NAME LIKE '%Config%'
                           OR TABLE_NAME LIKE '%Company%'
                           OR TABLE_NAME LIKE '%Parameter%'
                           OR TABLE_NAME LIKE '%Option%'
                           OR TABLE_NAME LIKE '%Control%'
                           OR TABLE_NAME LIKE '%MsSystem%'
                           OR TABLE_NAME LIKE '%MsSetup%')
                    ORDER BY TABLE_NAME
                """),

                ("218 — Company master: dump every row", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Company%' OR TABLE_NAME LIKE '%MsOrg%'
                           OR TABLE_NAME LIKE '%MsFirm%')
                    ORDER BY TABLE_NAME
                """),

                ("219 — Financial year / period definition table", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%FinYear%'
                           OR TABLE_NAME LIKE '%FYear%'
                           OR TABLE_NAME LIKE '%Period%'
                           OR TABLE_NAME LIKE '%Year%')
                    ORDER BY TABLE_NAME
                """),

                ("220 — Voucher number series / prefix configuration", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Series%'
                           OR TABLE_NAME LIKE '%Prefix%'
                           OR TABLE_NAME LIKE '%Numbering%'
                           OR TABLE_NAME LIKE '%VoucherSeries%'
                           OR TABLE_NAME LIKE '%AutoNumber%')
                    ORDER BY TABLE_NAME
                """),

                ("221 — All tables with 'Rate' OR 'Tax' OR 'Duty' in name", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Rate%'
                           OR TABLE_NAME LIKE '%Tax%'
                           OR TABLE_NAME LIKE '%Duty%'
                           OR TABLE_NAME LIKE '%TCS%'
                           OR TABLE_NAME LIKE '%GST%'
                           OR TABLE_NAME LIKE '%Excise%')
                    ORDER BY TABLE_NAME
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK S — Complete Voucher Anatomy (head + item + detail)
                # One real voucher of each type — every column as-stored
                # ════════════════════════════════════════════════════════════
                ("222 — Full anatomy: most recent MS sale voucher (TrVocHead)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC
                """),

                ("223 — Full anatomy: most recent MS sale voucher (TrVocItem — all lines)", """
                    SELECT i.*
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate)
                          FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='MS' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY i.SrNo
                """),

                ("224 — Full anatomy: most recent MS sale voucher (TrVocDetail — all debit/credit legs)", """
                    SELECT d.*
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate)
                          FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='MS' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY d.SrNo
                """),

                ("225 — Full anatomy: most recent PU purchase (TrVocHead + both detail tables)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC
                """),

                ("226 — Full anatomy: most recent PU purchase (TrVocItem)", """
                    SELECT i.*
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate)
                          FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='PU' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY i.SrNo
                """),

                ("227 — Full anatomy: most recent PU purchase (TrVocDetail)", """
                    SELECT d.*
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate)
                          FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='PU' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY d.SrNo
                """),

                ("228 — Full anatomy: most recent BP with TrVocItem (excise payment)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND EXISTS (SELECT 1 FROM TrVocItem i
                                  WHERE i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo)
                    ORDER BY h.VoucherDate DESC
                """),

                ("229 — TrVocItem for that BP with items (excise payment item rows)", """
                    SELECT i.*
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate) FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='BP' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                            AND EXISTS (SELECT 1 FROM TrVocItem ix
                                        WHERE ix.TransTypeID=h2.TransTypeID AND ix.VoucherNo=h2.VoucherNo)
                      )
                    ORDER BY i.SrNo
                """),

                ("230 — Full anatomy: most recent BP without TrVocItem (pure expense payment)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem i
                                      WHERE i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo)
                    ORDER BY h.VoucherDate DESC
                """),

                ("231 — TrVocDetail for that pure expense BP (all legs)", """
                    SELECT d.*
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BP'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem i
                                      WHERE i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo)
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate) FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='BP' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                            AND NOT EXISTS (SELECT 1 FROM TrVocItem ix
                                            WHERE ix.TransTypeID=h2.TransTypeID AND ix.VoucherNo=h2.VoucherNo)
                      )
                    ORDER BY d.SrNo
                """),

                ("232 — Full anatomy: most recent BR bank receipt (TrVocHead + TrVocDetail)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BR'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),

                ("233 — TrVocDetail for most recent BR (how customer debit and bank credit appear)", """
                    SELECT d.*
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='BR'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate) FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='BR' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY d.SrNo
                """),

                ("234 — Full anatomy: most recent CN credit note (TrVocHead)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),

                ("235 — TrVocItem for most recent CN (does stock reverse?)", """
                    SELECT i.*
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, i.SrNo
                """),

                ("236 — TrVocDetail for most recent CN (all accounting legs)", """
                    SELECT d.*
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='CN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate) FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='CN' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY d.SrNo
                """),

                ("237 — Full anatomy: most recent DN debit note (all three tables)", """
                    SELECT TOP 1 h.*
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='DN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),

                ("238 — TrVocDetail for most recent DN (shows who is debited/credited)", """
                    SELECT d.*
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='DN'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate = (
                          SELECT MAX(h2.VoucherDate) FROM TrVocHead h2
                          JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                          WHERE t2.ShortName='DN' AND ISNULL(h2.Cancelled,'N') <> 'Y'
                            AND h2.VoucherDate >= '2025-04-01'
                      )
                    ORDER BY d.SrNo
                """),

                ("239 — Full anatomy: most recent JV journal voucher", """
                    SELECT TOP 1 h.*, d.SrNo, d.PartyID, d.DrCrIndicator, d.Amount, d.Narration
                    FROM TrVocHead h
                    JOIN TrVocDetail d ON d.TransTypeID=h.TransTypeID AND d.VoucherNo=h.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='JV'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK T — Bill-Wise Outstanding / Reference Allocation
                # ════════════════════════════════════════════════════════════
                ("240 — TrVocDetail: all columns including Reference / BillNo / AgainstVoucher", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocDetail'
                    ORDER BY ORDINAL_POSITION
                """),

                ("241 — TrVocDetail: distinct values in any Reference / BillNo column (top 30)", """
                    SELECT TOP 30 *
                    FROM TrVocDetail
                    WHERE TransTypeID IN (SELECT id_key FROM MsTransType WHERE ShortName IN ('BR','CR'))
                      AND DrCrIndicator='D'
                    ORDER BY 1 DESC
                """),

                ("242 — All tables with Allocation / Adjust / Settlement / BillRef in name", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Alloc%'
                           OR TABLE_NAME LIKE '%Adjust%'
                           OR TABLE_NAME LIKE '%Settle%'
                           OR TABLE_NAME LIKE '%BillRef%'
                           OR TABLE_NAME LIKE '%Against%'
                           OR TABLE_NAME LIKE '%Receipt%'
                           OR TABLE_NAME LIKE '%Payment%')
                    ORDER BY TABLE_NAME
                """),

                ("243 — TrVocHead: all columns (checking for DueDate, CreditDays, RefNo)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocHead'
                    ORDER BY ORDINAL_POSITION
                """),

                ("244 — MS vouchers: show DueDate / CreditDays if those columns exist", """
                    SELECT TOP 20
                        h.VoucherNo, h.VoucherDate,
                        p.PartyName,
                        h.TotalAmount
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID = h.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC
                """),

                ("245 — MsPartyMaster: columns related to credit limit / credit days", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsPartyMaster'
                      AND (COLUMN_NAME LIKE '%Credit%'
                           OR COLUMN_NAME LIKE '%Limit%'
                           OR COLUMN_NAME LIKE '%Days%'
                           OR COLUMN_NAME LIKE '%Due%')
                    ORDER BY ORDINAL_POSITION
                """),

                ("246 — MsPartyMaster: sample row for a D% customer (all columns)", """
                    SELECT TOP 1 * FROM MsPartyMaster
                    WHERE LEFT(PartyID,1)='D'
                    ORDER BY PartyID
                """),

                ("247 — MsPartyMaster: sample row for a C% supplier (all columns)", """
                    SELECT TOP 1 * FROM MsPartyMaster
                    WHERE LEFT(PartyID,1)='C'
                    ORDER BY PartyID
                """),

                ("248 — MsPartyMaster: sample row for a GL/expense account (not D or C prefix)", """
                    SELECT TOP 5 * FROM MsPartyMaster
                    WHERE LEFT(PartyID,1) NOT IN ('D','C')
                    ORDER BY PartyID
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK U — Tax Rate Storage (TCS, Excise, Duties)
                # ════════════════════════════════════════════════════════════
                ("249 — MsServiceItemMaster: all columns + all rows", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsServiceItemMaster'
                    ORDER BY ORDINAL_POSITION
                """),

                ("250 — MsServiceItemMaster: full data dump", """
                    SELECT * FROM MsServiceItemMaster ORDER BY 1
                """),

                ("251 — Service item rows on MS sale invoices (excise, TCS, handling, discount)", """
                    SELECT TOP 50
                        h.VoucherNo, h.VoucherDate,
                        i.SrNo, i.ItemID, i.ItemDescription,
                        i.TotalAmount, i.TotalBottleQty,
                        i.FreeItemYN
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND (i.ItemID NOT IN (SELECT ItemID FROM MsItemMaster)
                           OR i.TotalBottleQty = 0
                           OR i.TotalAmount < 0)
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC, i.SrNo
                """),

                ("252 — TrVocItem: all service-type rows (zero bottle qty or negative amount = charges)", """
                    SELECT TOP 100
                        t.ShortName, i.ItemID, i.ItemDescription,
                        i.TotalAmount, i.TotalBottleQty, i.FreeItemYN,
                        COUNT(*) OVER (PARTITION BY i.ItemID) AS occurrences
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate < '2026-04-01'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND (i.TotalBottleQty = 0 OR i.TotalBottleQty IS NULL)
                    ORDER BY occurrences DESC
                """),

                ("253 — MsItemMaster: all rate / price / duty / tax columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsItemMaster'
                      AND (COLUMN_NAME LIKE '%Rate%'
                           OR COLUMN_NAME LIKE '%Price%'
                           OR COLUMN_NAME LIKE '%MRP%'
                           OR COLUMN_NAME LIKE '%Duty%'
                           OR COLUMN_NAME LIKE '%Tax%'
                           OR COLUMN_NAME LIKE '%TCS%'
                           OR COLUMN_NAME LIKE '%Excise%'
                           OR COLUMN_NAME LIKE '%Val%'
                           OR COLUMN_NAME LIKE '%Cost%'
                           OR COLUMN_NAME LIKE '%Landing%')
                    ORDER BY ORDINAL_POSITION
                """),

                ("254 — MsItemMaster: full dump of rate/price columns for 20 items", """
                    SELECT TOP 20
                        i.ItemID, i.ItemDescription,
                        i.MrpBottRate, i.MrpCaseRate,
                        b.BrandName, lt.LiquorType, st.SizeType
                    FROM MsItemMaster i
                    LEFT JOIN MsBrandMaster b  ON b.BrandID      = i.BrandID
                    LEFT JOIN MsLiquorType lt  ON lt.LiquorTypeID = i.LiquorTypeID
                    LEFT JOIN MsSizeType   st  ON st.SizeTypeID   = i.SizeTypeID
                    ORDER BY i.ItemID
                """),

                ("255 — MsBatchMaster: all columns (batch-level rates)", """
                    SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsBatchMaster'
                    ORDER BY ORDINAL_POSITION
                """),

                ("256 — MsBatchMaster: full dump (batch rates, dates, quantities)", """
                    SELECT TOP 30 * FROM MsBatchMaster ORDER BY 1 DESC
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK V — Ageing & Credit Limit
                # ════════════════════════════════════════════════════════════
                ("257 — MsPartyOpening: all columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsPartyOpening'
                    ORDER BY ORDINAL_POSITION
                """),

                ("258 — MsPartyOpening: sample rows for D% customers (CloseBal vs CloseBalTmp)", """
                    SELECT TOP 20 *
                    FROM MsPartyOpening
                    WHERE LEFT(PartyID,1)='D'
                    ORDER BY PartyID
                """),

                ("259 — Outstanding: all TrVocDetail DR entries for one busy customer this FY", """
                    SELECT TOP 1 PartyID FROM MsPartyOpening
                    WHERE LEFT(PartyID,1)='D'
                    ORDER BY ISNULL(CloseBalTmp,CloseBal) DESC
                """),

                ("260 — All TrVocDetail entries for the top-outstanding customer (full ledger)", """
                    SELECT
                        h.VoucherDate, t.ShortName, h.VoucherNo,
                        d.DrCrIndicator, d.Amount, d.Narration,
                        d.PartyID
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE d.PartyID = (
                        SELECT TOP 1 PartyID FROM MsPartyOpening
                        WHERE LEFT(PartyID,1)='D'
                        ORDER BY ISNULL(CloseBalTmp,CloseBal) DESC
                    )
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate, h.VoucherNo
                """),

                ("261 — Does TrVocDetail have a ReferenceVoucher / AgainstBill column?", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocDetail'
                      AND (COLUMN_NAME LIKE '%Ref%'
                           OR COLUMN_NAME LIKE '%Against%'
                           OR COLUMN_NAME LIKE '%Bill%'
                           OR COLUMN_NAME LIKE '%Invoice%'
                           OR COLUMN_NAME LIKE '%Adjust%')
                    ORDER BY ORDINAL_POSITION
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK W — Scheme / Free Goods Logic
                # ════════════════════════════════════════════════════════════
                ("262 — All tables with Scheme / Offer / Promotion / Free in name", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Scheme%'
                           OR TABLE_NAME LIKE '%Offer%'
                           OR TABLE_NAME LIKE '%Promo%'
                           OR TABLE_NAME LIKE '%Free%'
                           OR TABLE_NAME LIKE '%Bonus%'
                           OR TABLE_NAME LIKE '%Discount%')
                    ORDER BY TABLE_NAME
                """),

                ("263 — Free goods invoices: which items appear as FreeItemYN='Y'", """
                    SELECT TOP 50
                        i.ItemID, i.ItemDescription,
                        COUNT(DISTINCT h.VoucherNo) AS vouchers,
                        SUM(i.TotalBottleQty) AS free_bottles
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N')='Y'
                      AND h.VoucherDate >= '2025-04-01'
                    GROUP BY i.ItemID, i.ItemDescription
                    ORDER BY free_bottles DESC
                """),

                ("264 — Free goods: same voucher showing paid item alongside free item", """
                    SELECT
                        h.VoucherNo, h.VoucherDate,
                        i.SrNo, i.ItemDescription,
                        i.TotalBottleQty, i.TotalAmount, i.FreeItemYN
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherNo IN (
                          SELECT VoucherNo FROM TrVocItem
                          WHERE ISNULL(FreeItemYN,'N')='Y'
                            AND TransTypeID IN (SELECT id_key FROM MsTransType WHERE ShortName='MS')
                      )
                    ORDER BY h.VoucherNo, i.SrNo
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK X — Transport Permit (TP) complete structure
                # ════════════════════════════════════════════════════════════
                ("265 — All TP tables: columns and row counts", """
                    SELECT TABLE_NAME,
                           (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                            WHERE c.TABLE_NAME=t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%TP%'
                           OR TABLE_NAME LIKE '%Transport%'
                           OR TABLE_NAME LIKE '%Permit%'
                           OR TABLE_NAME LIKE '%Pass%')
                    ORDER BY TABLE_NAME
                """),

                ("266 — TrTPHead: all columns", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrTPHead'
                    ORDER BY ORDINAL_POSITION
                """),

                ("267 — TrTPHead sample + linkage to TrVocHead (TPNo / VoucherNo)", """
                    SELECT TOP 10 * FROM TrTPHead ORDER BY 1 DESC
                """),

                ("268 — TrTPItem: all columns + sample rows", """
                    SELECT TOP 20 i.*
                    FROM TrTPItem i
                    ORDER BY 1 DESC
                """),

                ("269 — TP to Invoice linkage: does TrVocHead.TPNo reference TrTPHead?", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocHead'
                      AND (COLUMN_NAME LIKE '%TP%'
                           OR COLUMN_NAME LIKE '%Permit%'
                           OR COLUMN_NAME LIKE '%Transport%')
                    ORDER BY ORDINAL_POSITION
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK Y — Salesman, Customer Category, Discount Structure
                # ════════════════════════════════════════════════════════════
                ("270 — MsSalesmanMaster: all columns + all rows", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsSalesmanMaster'
                    ORDER BY ORDINAL_POSITION
                """),

                ("271 — MsSalesmanMaster: full dump", """
                    SELECT * FROM MsSalesmanMaster ORDER BY 1
                """),

                ("272 — Salesman → customer assignment: does MsPartyMaster have SalesmanID?", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsPartyMaster'
                      AND (COLUMN_NAME LIKE '%Salesman%'
                           OR COLUMN_NAME LIKE '%Sales%'
                           OR COLUMN_NAME LIKE '%Agent%'
                           OR COLUMN_NAME LIKE '%Rep%')
                    ORDER BY ORDINAL_POSITION
                """),

                ("273 — TrVocHead: does it carry SalesmanID per voucher?", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocHead'
                      AND (COLUMN_NAME LIKE '%Salesman%'
                           OR COLUMN_NAME LIKE '%Agent%'
                           OR COLUMN_NAME LIKE '%Rep%')
                    ORDER BY ORDINAL_POSITION
                """),

                ("274 — Salesman target tables (if any)", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Target%'
                           OR TABLE_NAME LIKE '%Quota%'
                           OR TABLE_NAME LIKE '%Budget%'
                           OR TABLE_NAME LIKE '%SalesTarget%')
                    ORDER BY TABLE_NAME
                """),

                ("275 — Customer category master: all tables with Category in name", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND TABLE_NAME LIKE '%Category%'
                    ORDER BY TABLE_NAME
                """),

                ("276 — MsPartyCategory or equivalent: full dump", """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME IN (
                        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                        WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE '%Category%'
                    )
                    ORDER BY TABLE_NAME, ORDINAL_POSITION
                """),

                ("277 — Sales by customer category this FY", """
                    SELECT
                        cat.CategoryName,
                        COUNT(DISTINCT p.PartyID) AS customers,
                        SUM(i.TotalAmount)        AS sales_amount,
                        SUM(i.TotalBottleQty)     AS bottles
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsPartyMaster p ON p.PartyID=h.PartyID
                    LEFT JOIN MsPartyCategory cat ON cat.CategoryID=p.CategoryID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY cat.CategoryName
                    ORDER BY sales_amount DESC
                """),

                # ════════════════════════════════════════════════════════════
                # BLOCK Z — Complete Master Reference (every lookup table)
                # ════════════════════════════════════════════════════════════
                ("278 — All Ms* master tables: names + row counts", """
                    SELECT TABLE_NAME,
                           (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                            WHERE c.TABLE_NAME=t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE 'Ms%'
                    ORDER BY TABLE_NAME
                """),

                ("279 — All Tr* transaction tables: names + row counts", """
                    SELECT TABLE_NAME,
                           (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS c
                            WHERE c.TABLE_NAME=t.TABLE_NAME) AS col_count
                    FROM INFORMATION_SCHEMA.TABLES t
                    WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE 'Tr%'
                    ORDER BY TABLE_NAME
                """),

                ("280 — MsLiquorType: full dump (all liquor types)", """
                    SELECT * FROM MsLiquorType ORDER BY 1
                """),

                ("281 — MsSizeType: full dump (bottle sizes)", """
                    SELECT * FROM MsSizeType ORDER BY 1
                """),

                ("282 — MsPackType / MsPackMaster: full dump (case/pack config)", """
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%Pack%' OR TABLE_NAME LIKE '%Case%')
                    ORDER BY TABLE_NAME
                """),

                ("283 — MsTransType: full dump (all transaction type definitions)", """
                    SELECT * FROM MsTransType ORDER BY id_key
                """),

                ("284 — MsTransType: all columns (checking for VoucherFlag, StockEffect, AccountingEffect)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsTransType'
                    ORDER BY ORDINAL_POSITION
                """),

                ("285 — MsUserMaster: all columns (user access structure)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME IN (
                        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                        WHERE TABLE_TYPE='BASE TABLE'
                          AND (TABLE_NAME LIKE '%User%' OR TABLE_NAME LIKE '%Login%'
                               OR TABLE_NAME LIKE '%Access%' OR TABLE_NAME LIKE '%Role%'
                               OR TABLE_NAME LIKE '%Rights%' OR TABLE_NAME LIKE '%Permission%')
                    )
                    ORDER BY TABLE_NAME, ORDINAL_POSITION
                """),

                ("286 — MsUserMaster: sample rows (who has access, roles)", """
                    SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE='BASE TABLE'
                      AND (TABLE_NAME LIKE '%User%' OR TABLE_NAME LIKE '%Login%'
                           OR TABLE_NAME LIKE '%Role%')
                    ORDER BY TABLE_NAME
                """),

                ("287 — VoucherFlag values in TrVocHead: all distinct values + transaction types", """
                    SELECT h.VoucherFlag, t.ShortName, t.TransTypeName,
                           COUNT(*) AS vouchers
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= '2025-04-01'
                    GROUP BY h.VoucherFlag, t.ShortName, t.TransTypeName
                    ORDER BY t.ShortName, h.VoucherFlag
                """),

                ("288 — TrVocHead: every column present (final full list)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocHead'
                    ORDER BY ORDINAL_POSITION
                """),

                ("289 — TrVocItem: every column present (final full list)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='TrVocItem'
                    ORDER BY ORDINAL_POSITION
                """),

                ("290 — Identify which transaction types actually write TrVocItem rows", """
                    SELECT t.ShortName, t.TransTypeName,
                           COUNT(DISTINCT i.VoucherNo) AS vouchers_with_items
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE h.VoucherDate >= '2025-04-01'
                    GROUP BY t.ShortName, t.TransTypeName
                    ORDER BY vouchers_with_items DESC
                """),

                ("291 — MsItemBatchOpening: all columns + sample (opening stock structure)", """
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME='MsItemBatchOpening'
                    ORDER BY ORDINAL_POSITION
                """),

                ("292 — MsItemBatchOpening: full dump (TOP 30)", """
                    SELECT TOP 30 * FROM MsItemBatchOpening ORDER BY 1
                """),

                ("293 — Stock as computed: opening + PU purchases - MS sales - SA breakage per item", """
                    SELECT
                        m.ItemID,
                        m.ItemDescription,
                        ISNULL(op.OpeningQty, 0)   AS opening_bottles,
                        ISNULL(pu.pur_bottles, 0)  AS purchased_bottles,
                        ISNULL(ms.sale_bottles, 0) AS sold_bottles,
                        ISNULL(sa.brk_bottles, 0)  AS breakage_bottles,
                        ISNULL(op.OpeningQty,0)
                          + ISNULL(pu.pur_bottles,0)
                          - ISNULL(ms.sale_bottles,0)
                          - ISNULL(sa.brk_bottles,0) AS closing_bottles
                    FROM MsItemMaster m
                    LEFT JOIN (
                        SELECT ItemID, SUM(OpeningQty) AS OpeningQty
                        FROM MsItemBatchOpening GROUP BY ItemID
                    ) op ON op.ItemID = m.ItemID
                    LEFT JOIN (
                        SELECT i.ItemID, SUM(i.TotalBottleQty) AS pur_bottles
                        FROM TrVocItem i
                        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='PU'
                          AND ISNULL(h.Cancelled,'N') <> 'Y'
                          AND h.VoucherDate >= '2025-04-01'
                        GROUP BY i.ItemID
                    ) pu ON pu.ItemID = m.ItemID
                    LEFT JOIN (
                        SELECT i.ItemID, SUM(i.TotalBottleQty) AS sale_bottles
                        FROM TrVocItem i
                        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='MS'
                          AND ISNULL(h.Cancelled,'N') <> 'Y'
                          AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                          AND h.VoucherDate >= '2025-04-01'
                        GROUP BY i.ItemID
                    ) ms ON ms.ItemID = m.ItemID
                    LEFT JOIN (
                        SELECT i.ItemID, SUM(i.TotalBottleQty) AS brk_bottles
                        FROM TrVocItem i
                        JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='SA'
                          AND ISNULL(h.Cancelled,'N') <> 'Y'
                          AND h.VoucherDate >= '2025-04-01'
                        GROUP BY i.ItemID
                    ) sa ON sa.ItemID = m.ItemID
                    ORDER BY closing_bottles DESC
                """),

                ("294 — Expense GL accounts: all TrVocDetail entries where PartyID is not D% or C%", """
                    SELECT
                        d.PartyID AS gl_account,
                        p.PartyName,
                        t.ShortName,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS debit_total,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS credit_total,
                        COUNT(*) AS entries
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate < '2026-04-01'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND LEFT(d.PartyID,1) NOT IN ('D','C')
                      AND d.PartyID IS NOT NULL AND d.PartyID <> ''
                    GROUP BY d.PartyID, p.PartyName, t.ShortName
                    ORDER BY debit_total DESC
                """),

                ("295 — Expense summary: total expenses by GL account (BP + CE, no TrVocItem)", """
                    SELECT
                        d.PartyID AS expense_account,
                        p.PartyName,
                        SUM(d.Amount) AS total_expense
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                      AND d.DrCrIndicator='D'
                      AND LEFT(d.PartyID,1) NOT IN ('D','C')
                      AND NOT EXISTS (SELECT 1 FROM TrVocItem i
                                      WHERE i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo)
                    GROUP BY d.PartyID, p.PartyName
                    ORDER BY total_expense DESC
                """),

                ("296 — Trial balance: every GL account DR/CR total this FY", """
                    SELECT
                        d.PartyID,
                        p.PartyName,
                        LEFT(d.PartyID,1) AS prefix,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_debit,
                        SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_credit,
                        SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY d.PartyID, p.PartyName
                    ORDER BY total_debit DESC
                """),

                ("297 — Sales Register anatomy: all MS voucher lines joined to item/customer/salesman", """
                    SELECT TOP 50
                        h.VoucherDate, h.VoucherNo,
                        p.PartyName AS customer,
                        p.CategoryID,
                        i.ItemDescription, i.TotalBottleQty, i.TotalAmount,
                        i.FreeItemYN
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    JOIN MsPartyMaster p ON p.PartyID=h.PartyID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC
                """),

                ("298 — Purchase Register anatomy: all PU lines joined to supplier/item", """
                    SELECT TOP 50
                        h.VoucherDate, h.VoucherNo,
                        p.PartyName AS supplier,
                        i.ItemDescription, i.TotalBottleQty, i.TotalAmount
                    FROM TrVocItem i
                    JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=h.PartyID
                    WHERE t.ShortName='PU'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                    ORDER BY h.VoucherDate DESC, h.VoucherNo DESC
                """),

                ("299 — Day Book: all voucher types in a single day (latest day with activity)", """
                    SELECT
                        h.VoucherDate, t.ShortName, h.VoucherNo,
                        h.PartyID, p.PartyName,
                        h.TotalAmount, h.Narration, h.Cancelled
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    LEFT JOIN MsPartyMaster p ON p.PartyID=h.PartyID
                    WHERE h.VoucherDate = (
                        SELECT MAX(VoucherDate) FROM TrVocHead
                        WHERE VoucherDate >= '2025-04-01' AND ISNULL(Cancelled,'N') <> 'Y'
                    )
                    ORDER BY t.ShortName, h.VoucherNo
                """),

                ("300 — Complete ERP summary: voucher count and total amount per type FY25-26", """
                    SELECT
                        t.ShortName,
                        t.TransTypeName,
                        COUNT(DISTINCT h.VoucherNo) AS voucher_count,
                        SUM(h.TotalAmount)           AS total_amount,
                        MIN(h.VoucherDate)           AS first_date,
                        MAX(h.VoucherDate)           AS last_date
                    FROM TrVocHead h
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName
                    ORDER BY total_amount DESC
                """),
            ]

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
                import io as _dio, zipfile as _dzf
                buf = _dio.BytesIO()
                with _dzf.ZipFile(buf, "w", _dzf.ZIP_DEFLATED) as zf:
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

        st.divider()

        # ── Front-end test guide ──────────────────────────────────────────────
        with st.expander("📋 Front-End Tests — What to do on the ERP to reveal the backend", expanded=False):
            st.markdown("""
**How to use this guide:**
Do each action on the ERP front-end, then immediately run the highlighted
diagnostic query (or use the Live-Test queries 181-184) and compare before/after.
Share the results and I will map the exact tables and columns.

---

### TEST 1 — Complete sale invoice with all charges
Create one MS invoice manually with:
- At least 2 product lines (different brands)
- Excise duty visible as a line
- TCS if applicable
- A handling charge
- A trade discount

**Then run:** Diag 182 (latest MS voucher complete anatomy)

**What I need to know:** What does each line in TrVocItem look like?
Does excise appear as a separate row with ServiceItemID?
Does discount appear as a negative TotalAmount or a separate column?

---

### TEST 2 — Expense payment (BP or CE)
Post one BP voucher for a non-goods expense — e.g. license fee, rent,
salesman salary, or vehicle running expense.

**Then run:** Diag 184 (latest BP/CE voucher)

**What I need to know:** What account (PartyID) is debited?
What is the narration convention? Is there a head like "License Fees" or
"Administrative Expenses" that I can use to classify expenses?

---

### TEST 3 — Credit note to a customer (sales return)
Issue a CN to one customer for returned goods.

**Then run:** Diag 66 (CN anatomy) and Diag 165 (CN with item lines check)

**What I need to know:** Does stock go back (TrVocItem present)?
Which account is debited — Sales or a separate Returns account?
Does RemainingAmt on the original MS voucher reduce?

---

### TEST 4 — Credit note from supplier (supplier CN)
Enter a CN received from a principal/supplier (price reduction or return).

**Then run:** Diag 66 then Diag 163

**What I need to know:** Is this a different TransTypeID to customer CN?
Which account is credited — Purchase or a separate account?

---

### TEST 5 — Customer with credit limit exceeded
Find a customer who is over their credit limit and try to raise an invoice.

**What I need to know:** Does the ERP block the invoice or just warn?
Is there an override field in TrVocHead?

---

### TEST 6 — Scheme / free goods
Raise a sale invoice that triggers a scheme (e.g. buy 5 cases get 1 free).

**Then run:** Diag 86 (free goods) and Diag 134 (scheme usage)

**What I need to know:** Is the free case on the same VoucherNo with
FreeItemYN='Y'? Or is it a separate LD voucher?
Does SchemeID in TrVocItem match MsSchemeMaster?

---

### TEST 7 — Change a master setting
Change any setting in the ERP configuration (e.g. credit days for a customer,
or a default account for a transaction type).

**Then run:** Diag 127 (MsTransType), Diag 126 (MsCodeMaster)

**What I need to know:** Which table changes? Which column?
Is there an audit log table that records who changed what?

---

### TEST 8 — TP generation
After billing, generate a TP for the invoice at the warehouse.

**Then run:** Diag 82 (TrTPHead sample) and Diag 84 (TP coverage)

**What I need to know:** Does TrVocHead.TPNo get populated when TP is
generated? Or does it get populated when the invoice is saved?
What is the exact link between TrTPHead and TrVocHead?

---

### TEST 9 — New customer master
Create a new customer in the party master.

**Then run:** Diag 93 (MsPartyMaster sample)

**What I need to know:** Which fields are mandatory? What does the
CategoryID map to? Is there a separate opening balance entry?

---

### STANDING QUESTION — Tell me the exact breakdown for one invoice
Pick any recent MS invoice from the ERP screen. Tell me:
1. The VoucherNo
2. The printed amounts: product value, excise duty, TCS, handling, discount, net total
3. What the customer was charged per bottle vs MRP

This single data point will let me verify whether my queries are computing
the same number as the ERP report.

---

### TEST 10 — Item rate maintenance screen
Open any item in the item master and tell me what rate fields appear:
- Purchase Rate / Landing Cost
- Sale Rate / MRP (bottle and case)
- Valuation Rate
- Excise Rate per bottle
- Any other rate fields visible on screen

**Then run:** Diag 201 and 202

**What I need to know:** Are purchase rate and valuation rate stored on the
item master or computed from purchase bills? Is MrpBottRate the MRP the
customer pays, or the price KWPL receives from the principal?

---

### TEST 11 — Purchase bill with rate variance
Enter a PU invoice where the rate on the bill differs from the master purchase
rate (e.g. principal revised prices mid-year).

**Then run:** Diag 207 (purchase rate variance)

**What I need to know:** Does the ERP flag the discrepancy? Does it update
the master rate automatically or keep the old one?
            """)

