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

        @st.fragment
        def _diag_panel():
            st.subheader("Live Diagnostics — Collections / Sales / Outstanding")
            st.caption("Runs targeted queries. Download all results as ZIP.")

            DIAG_SECTIONS = [
                ("M — BP/CE party+DrCr breakdown FY25-26 (find collections)", """
                    SELECT t.ShortName, d.DrCrIndicator,
                           CASE WHEN d.PartyID LIKE 'D%' THEN 'Customer (D-prefix)'
                                WHEN d.PartyID LIKE 'C%' THEN 'Supplier (C-prefix)'
                                WHEN d.PartyID IS NULL   THEN 'No Party (Bank/GL)'
                                ELSE 'Other: '+LEFT(d.PartyID,1) END AS party_type,
                           COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                           SUM(d.Amount) AS total_amount
                    FROM TrVocDetail d
                    JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName IN ('BP','CE')
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, d.DrCrIndicator,
                             CASE WHEN d.PartyID LIKE 'D%' THEN 'Customer (D-prefix)'
                                  WHEN d.PartyID LIKE 'C%' THEN 'Supplier (C-prefix)'
                                  WHEN d.PartyID IS NULL   THEN 'No Party (Bank/GL)'
                                  ELSE 'Other: '+LEFT(d.PartyID,1) END
                    ORDER BY total_amount DESC
                """),
                ("P — ALL credits to customer (D%) accounts FY25-26 by type (= TRUE collections)", """
                    SELECT t.ShortName, t.TransTypeName,
                           COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                           SUM(d.Amount) AS amount_credited_to_customers
                    FROM TrVocDetail d
                    JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='C'
                      AND d.PartyID LIKE 'D%'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                    GROUP BY t.ShortName, t.TransTypeName
                    ORDER BY amount_credited_to_customers DESC
                """),
                ("Q — Net ledger balance (DR-CR) per D% customer as on 31.03.2026 (= true debtors)", """
                    SELECT TOP 30 p.PartyName, sub.PartyID,
                           sub.total_dr, sub.total_cr, sub.net_balance
                    FROM (
                        SELECT d.PartyID,
                               SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_dr,
                               SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_cr,
                               SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance
                        FROM TrVocDetail d
                        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                        WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                          AND d.PartyID LIKE 'D%'
                          AND h.VoucherDate < '2026-04-01'
                        GROUP BY d.PartyID
                        HAVING SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) > 0
                    ) sub
                    JOIN MsPartyMaster p ON p.PartyID=sub.PartyID
                    ORDER BY sub.net_balance DESC
                """),
                ("R — Total debtors summary as on 31.03.2026 (net ledger vs RemainingAmt)", """
                    SELECT
                        ledger.debtor_count_ledger,
                        ledger.total_outstanding_ledger,
                        ra.total_outstanding_remaining_amt
                    FROM (
                        SELECT COUNT(*) AS debtor_count_ledger,
                               SUM(net_balance) AS total_outstanding_ledger
                        FROM (
                            SELECT d.PartyID,
                                   SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance
                            FROM TrVocDetail d
                            JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                            WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                              AND d.PartyID LIKE 'D%'
                              AND h.VoucherDate < '2026-04-01'
                            GROUP BY d.PartyID
                            HAVING SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) > 0
                        ) sub
                    ) ledger
                    CROSS JOIN (
                        SELECT SUM(d.RemainingAmt) AS total_outstanding_remaining_amt
                        FROM TrVocDetail d
                        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                        JOIN MsTransType t ON t.id_key=h.TransTypeID
                        WHERE t.ShortName='MS'
                          AND ISNULL(h.Cancelled,'N') <> 'Y'
                          AND d.DrCrIndicator='D' AND d.RemainingAmt > 0
                          AND d.PartyID LIKE 'D%'
                    ) ra
                """),
                ("N — RemainingAmt collection analysis — customer MS invoices FY25-26", """
                    SELECT
                        SUM(d.Amount)                                              AS total_invoiced,
                        SUM(ISNULL(d.RemainingAmt,0))                             AS still_outstanding,
                        SUM(d.Amount - ISNULL(d.RemainingAmt,0))                  AS collected,
                        COUNT(*)                                                   AS invoice_lines,
                        COUNT(CASE WHEN ISNULL(d.RemainingAmt,0)=0 THEN 1 END)    AS fully_paid_lines,
                        COUNT(CASE WHEN ISNULL(d.RemainingAmt,0)>0 THEN 1 END)    AS partly_outstanding_lines
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    JOIN MsTransType t ON t.id_key=h.TransTypeID
                    WHERE t.ShortName='MS'
                      AND ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.DrCrIndicator='D'
                      AND d.PartyID LIKE 'D%'
                      AND h.VoucherDate >= '2025-04-01'
                      AND h.VoucherDate <  '2026-04-01'
                """),
            ("L — ALL transaction types with totals FY25-26 (find collections)", """
                SELECT t.ShortName, t.TransTypeName,
                       COUNT(DISTINCT h.VoucherNo)                                   AS vouchers,
                       SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END)  AS dr_total,
                       SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END)  AS cr_total
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY t.ShortName, t.TransTypeName
                ORDER BY dr_total DESC
            """),
            ("I — MS TransType breakdown by name", """
                SELECT t.TransTypeName, t.id_key AS TransTypeID,
                       COUNT(DISTINCT h.VoucherNo) AS vouchers,
                       SUM(i.TotalAmount)           AS total_amount
                FROM TrVocHead h
                JOIN TrVocItem i ON i.TransTypeID=h.TransTypeID AND i.VoucherNo=h.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY t.TransTypeName, t.id_key
                ORDER BY total_amount DESC
            """),
            ("J — MS top 20 debit-side parties FY25-26", """
                SELECT TOP 20 p.PartyName, p.PartyID,
                       COUNT(DISTINCT h.VoucherNo) AS invoices,
                       SUM(d.Amount)               AS total_amount
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND d.DrCrIndicator='D' AND d.PartyID IS NOT NULL
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY p.PartyName, p.PartyID
                ORDER BY total_amount DESC
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
            ("D — BR/CR voucher detail FY 2025-26", """
                SELECT t.ShortName,
                       COUNT(DISTINCT h.VoucherNo)                                   AS vouchers,
                       MIN(h.VoucherDate)                                            AS earliest,
                       MAX(h.VoucherDate)                                            AS latest,
                       SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END)  AS dr_total,
                       SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END)  AS cr_total,
                       COUNT(DISTINCT d.PartyID)                                     AS distinct_parties
                FROM TrVocDetail d
                JOIN TrVocHead h  ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName IN ('BR','CR')
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY t.ShortName
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
                  AND h.VoucherDate <  '2026-04-01'
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
            ("S — YR Wines (D06428) all-time ledger breakdown by voucher type", """
                SELECT t.ShortName, t.TransTypeName, d.DrCrIndicator,
                       COUNT(DISTINCT h.VoucherNo) AS vouchers,
                       SUM(d.Amount) AS amount
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                  AND d.PartyID = 'D06428'
                  AND h.VoucherDate < '2026-04-01'
                GROUP BY t.ShortName, t.TransTypeName, d.DrCrIndicator
                ORDER BY amount DESC
            """),
            ("T — ALL transaction types that create DR entries to D% customers (all-time to 31.03.2026)", """
                SELECT t.ShortName, t.TransTypeName,
                       COUNT(DISTINCT d.PartyID) AS customers_affected,
                       COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                       SUM(d.Amount) AS total_dr_amount
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                  AND d.DrCrIndicator='D'
                  AND d.PartyID LIKE 'D%'
                  AND h.VoucherDate < '2026-04-01'
                GROUP BY t.ShortName, t.TransTypeName
                ORDER BY total_dr_amount DESC
            """),
            ("U — MsPartyOpening columns and D% summary (opening balances)", """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='MsPartyOpening'
                ORDER BY ORDINAL_POSITION
            """),
            ("U2 — MsPartyOpening sample rows", """
                SELECT TOP 20 * FROM MsPartyOpening ORDER BY 1
            """),
            ("U3 — MsPartyOpening totals for D% customers", """
                SELECT
                    COUNT(*) AS rows,
                    COUNT(DISTINCT PartyID) AS distinct_parties,
                    SUM(CASE WHEN DrCrIndicator='D' THEN Amount ELSE 0 END) AS total_dr,
                    SUM(CASE WHEN DrCrIndicator='C' THEN Amount ELSE 0 END) AS total_cr,
                    SUM(CASE WHEN DrCrIndicator='D' THEN Amount ELSE -Amount END) AS net_balance
                FROM MsPartyOpening
                WHERE PartyID LIKE 'D%'
            """),
            ("U4 — Outstanding with opening balance: TrVocDetail net + MsPartyOpening net", """
                SELECT
                    COUNT(*) AS debtor_count,
                    SUM(net_balance) AS total_outstanding
                FROM (
                    SELECT PartyID,
                           SUM(CASE WHEN DrCrIndicator='D' THEN Amount ELSE -Amount END) AS net_balance
                    FROM (
                        SELECT d.PartyID, d.DrCrIndicator, d.Amount
                        FROM TrVocDetail d
                        JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                        WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                          AND d.PartyID LIKE 'D%'
                          AND h.VoucherDate < '2026-04-01'
                        UNION ALL
                        SELECT PartyID, DrCrIndicator, Amount
                        FROM MsPartyOpening
                        WHERE PartyID LIKE 'D%'
                    ) combined
                    GROUP BY PartyID
                ) sub
                WHERE net_balance > 0
            """),
            ("X — Sample CE vouchers that debit D% customers (what are they?)", """
                SELECT TOP 20
                    h.VoucherDate, h.VoucherNo, t.TransTypeName,
                    d.DrCrIndicator, d.Amount, d.PartyID,
                    p.PartyName
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                WHERE t.ShortName='CE'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND d.DrCrIndicator='D'
                  AND d.PartyID LIKE 'D%'
                ORDER BY d.Amount DESC
            """),
            ("X2 — All lines of a single CE voucher that debits a D% customer", """
                SELECT d.DrCrIndicator, d.Amount, d.PartyID, p.PartyName,
                       d.AccountID, a.AccountHeadName
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                LEFT JOIN MsPartyMaster p ON p.PartyID=d.PartyID
                LEFT JOIN MsAccountHead a ON a.AccountHeadID=d.AccountID
                WHERE h.VoucherNo = (
                    SELECT TOP 1 h2.VoucherNo
                    FROM TrVocDetail d2
                    JOIN TrVocHead h2 ON h2.TransTypeID=d2.TransTypeID AND h2.VoucherNo=d2.VoucherNo
                    JOIN MsTransType t2 ON t2.id_key=h2.TransTypeID
                    WHERE t2.ShortName='CE'
                      AND ISNULL(h2.Cancelled,'N') <> 'Y'
                      AND d2.DrCrIndicator='D'
                      AND d2.PartyID LIKE 'D%'
                    ORDER BY d2.Amount DESC
                )
                  AND t.ShortName='CE'
                ORDER BY d.Amount DESC
            """),
            ("V — Opening balance tables existence check", """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE='BASE TABLE'
                  AND (TABLE_NAME LIKE '%%Opening%%' OR TABLE_NAME LIKE '%%Balance%%')
                ORDER BY TABLE_NAME
            """),
            ("W — Net ledger D%% to 31.03.2026 via PartyID (old approach for reference)", """
                SELECT
                    COUNT(*) AS debtors,
                    SUM(net_balance) AS total_outstanding
                FROM (
                    SELECT d.PartyID,
                           SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance
                    FROM TrVocDetail d
                    JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                    WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                      AND d.PartyID LIKE 'D%%'
                      AND h.VoucherDate < '2026-04-01'
                    GROUP BY d.PartyID
                ) all_parties
                WHERE net_balance > 0
            """),
            ("Y — TrVocDetail columns", """
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='TrVocDetail'
                ORDER BY ORDINAL_POSITION
            """),
            ("Y2 — MsAccountHead columns", """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='MsAccountHead'
                ORDER BY ORDINAL_POSITION
            """),
            ("Y3 — Find YR Wines account in MsAccountHead (correct column names)", """
                SELECT AccHeadID, AccName, MainHeadID, SubHeadID
                FROM MsAccountHead
                WHERE AccName LIKE '%%YR%%' OR AccName LIKE '%%Y R%%'
                   OR AccName LIKE '%%VIRANSH%%'
            """),
            ("Y4 — TrVocDetail for YR Wines by AccHeadID", """
                SELECT t.ShortName, d.DrCrIndicator,
                       COUNT(DISTINCT h.VoucherNo) AS vouchers,
                       SUM(d.Amount) AS amount
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsAccountHead a ON a.AccHeadID=d.AccHeadID
                WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                  AND (a.AccName LIKE '%%YR%%' OR a.AccName LIKE '%%Y R%%'
                       OR a.AccName LIKE '%%VIRANSH%%')
                  AND h.VoucherDate < '2026-04-01'
                GROUP BY t.ShortName, d.DrCrIndicator
                ORDER BY amount DESC
            """),
            ("Y5 — XMainheadTypeMainhead all rows (find DEBTORS MainHeadID)", """
                SELECT * FROM XMainheadTypeMainhead ORDER BY MainheadID
            """),
            ("Y6 — MsAccountHead sample — first 10 rows (see MainHeadID values)", """
                SELECT TOP 10 AccHeadID, AccName, MainHeadID, SubHeadID
                FROM MsAccountHead
                ORDER BY AccHeadID
            """),
            ("Y7 — MsAccountHead: accounts where MainHeadID matches DEBTORS", """
                SELECT MainHeadID, COUNT(*) AS accounts
                FROM MsAccountHead
                GROUP BY MainHeadID
                ORDER BY accounts DESC
            """),
            ("Y8 — YR Wines balance via AccHeadID from TrVocDetail", """
                SELECT a.AccName,
                       SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE 0 END) AS total_dr,
                       SUM(CASE WHEN d.DrCrIndicator='C' THEN d.Amount ELSE 0 END) AS total_cr,
                       SUM(CASE WHEN d.DrCrIndicator='D' THEN d.Amount ELSE -d.Amount END) AS net_balance
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsAccountHead a ON a.AccHeadID=d.AccHeadID
                WHERE ISNULL(h.Cancelled,'N') <> 'Y'
                  AND (a.AccName LIKE '%%YR%%' OR a.AccName LIKE '%%Y R%%'
                       OR a.AccName LIKE '%%VIRANSH%%')
                  AND h.VoucherDate < '2026-04-01'
                GROUP BY a.AccName, d.AccHeadID
            """),
            ("Z — MsPartyOpening: D%% total CloseBal as on 31.03.2026 (ERP target = 58.41 Cr)", """
                SELECT COUNT(*) AS debtors,
                       SUM(CASE WHEN CloseBal > 0 THEN CloseBal ELSE 0 END) AS total_outstanding,
                       SUM(CloseBal) AS net_all_parties
                FROM MsPartyOpening
                WHERE PartyID LIKE 'D%%'
            """),
            ("Z2 — MsPartyOpening: YR Wines (D06428) closing balance (ERP target = 1.39 Cr)", """
                SELECT PartyID, AccHeadID, OpenBal, TotalDebit, TotalCredit,
                       CloseBal, CloseBalTmp
                FROM MsPartyOpening
                WHERE PartyID = 'D06428'
            """),
            ("Z3 — MsPartyOpening: top 30 D%% debtors by CloseBal", """
                SELECT TOP 30 p.AccName, op.PartyID, op.OpenBal,
                       op.TotalDebit, op.TotalCredit, op.CloseBal
                FROM MsPartyOpening op
                JOIN MsAccountHead p ON p.AccHeadID=op.AccHeadID
                WHERE op.PartyID LIKE 'D%%' AND op.CloseBal > 0
                ORDER BY op.CloseBal DESC
            """),
            ("AA — Sales total FY25-26 via TrVocDetail (CR to blank party): target 443.39 Cr", """
                SELECT
                    SUM(d.Amount) AS total_sales_detail,
                    COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND d.DrCrIndicator='C'
                  AND (d.PartyID IS NULL OR LTRIM(RTRIM(d.PartyID)) = '')
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
            """),
            ("AA2 — Sales by MS TransType FY25-26 via TrVocDetail CR to blank party", """
                SELECT t.TransTypeName, t.TransTypeID,
                    COUNT(DISTINCT CAST(h.TransTypeID AS VARCHAR)+'|'+h.VoucherNo) AS vouchers,
                    SUM(d.Amount) AS sales_amount
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='MS'
                  AND d.DrCrIndicator='C'
                  AND (d.PartyID IS NULL OR LTRIM(RTRIM(d.PartyID)) = '')
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY t.TransTypeName, t.TransTypeID
                ORDER BY sales_amount DESC
            """),
            ("AB — TrVocItem.BrandID vs MsItemMaster.BrandID: are they the same?", """
                SELECT TOP 20
                    i.ItemID,
                    i.BrandID AS item_BrandID,
                    m.BrandID AS master_BrandID,
                    CASE WHEN i.BrandID = m.BrandID THEN 'SAME' ELSE 'DIFFERENT' END AS match,
                    b.BrandName
                FROM TrVocItem i
                JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsItemMaster m ON m.ItemID = i.ItemID
                LEFT JOIN MsBrandMaster b ON b.BrandID = m.BrandID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
            """),
            ("AD — LOAD DEMO (LD) breakdown FY25-26: party types debited (are these customer sales?)", """
                SELECT d.DrCrIndicator,
                       CASE WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                            WHEN LEFT(d.PartyID,1)='C' THEN 'Supplier (C%)'
                            WHEN d.PartyID IS NULL OR LTRIM(RTRIM(d.PartyID))='' THEN 'GL/Blank'
                            ELSE 'Other: '+LEFT(d.PartyID,1) END AS party_type,
                       COUNT(*) AS rows,
                       SUM(d.Amount) AS total_amount
                FROM TrVocDetail d
                JOIN TrVocHead h ON h.TransTypeID=d.TransTypeID AND h.VoucherNo=d.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                WHERE t.ShortName='LD' AND t.TransTypeName LIKE '%%DEMO%%'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY d.DrCrIndicator,
                         CASE WHEN LEFT(d.PartyID,1)='D' THEN 'Customer (D%)'
                              WHEN LEFT(d.PartyID,1)='C' THEN 'Supplier (C%)'
                              WHEN d.PartyID IS NULL OR LTRIM(RTRIM(d.PartyID))='' THEN 'GL/Blank'
                              ELSE 'Other: '+LEFT(d.PartyID,1) END
                ORDER BY total_amount DESC
            """),
            ("AC — Top 15 brands by sales FY25-26 via MsItemMaster join (verify principal mapping)", """
                SELECT TOP 15
                    b.BrandName, b.BrandID,
                    SUM(i.TotalAmount) AS sales,
                    SUM(i.TotalBottleQty) AS bottles
                FROM TrVocItem i
                JOIN TrVocHead h ON h.TransTypeID=i.TransTypeID AND h.VoucherNo=i.VoucherNo
                JOIN MsTransType t ON t.id_key=h.TransTypeID
                JOIN MsItemMaster m ON m.ItemID = i.ItemID
                JOIN MsBrandMaster b ON b.BrandID = m.BrandID
                WHERE t.ShortName='MS'
                  AND ISNULL(h.Cancelled,'N') <> 'Y'
                  AND ISNULL(i.FreeItemYN,'N') <> 'Y'
                  AND h.VoucherDate >= '2025-04-01'
                  AND h.VoucherDate <  '2026-04-01'
                GROUP BY b.BrandName, b.BrandID
                ORDER BY sales DESC
            """),
            ]

            import io, zipfile

            col_run, col_dl = st.columns([1, 1])
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

            if run_clicked:
                with st.spinner("Running diagnostics…"):
                    results = {}
                    for title, sql in DIAG_SECTIONS:
                        try:
                            results[title] = query(sql)
                        except Exception as e:
                            results[title] = pd.DataFrame([{"ERROR": str(e)}])
                    st.session_state["diag_results"] = results
                    # Pre-build ZIP so download button is always ready
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for title, df in results.items():
                            safe = title.replace(" ", "_").replace("—", "-")[:50]
                            zf.writestr(f"{safe}.csv", df.to_csv(index=False))
                    st.session_state["diag_zip"] = buf.getvalue()

            if "diag_results" in st.session_state:
                st.divider()
                for title, df in st.session_state["diag_results"].items():
                    st.markdown(f"### {title}")
                    st.dataframe(df, use_container_width=True, hide_index=True)

        _diag_panel()
