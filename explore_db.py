"""
explore_db.py  –  KW database schema explorer (pymssql version)
"""
import sys
import os
sys.path.insert(0, '/home/user/KWPL-dashboard')
os.chdir('/home/user/KWPL-dashboard')

from db import get_connection   # uses pymssql via .env credentials


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run_query(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, rows


def get_cols_from_top1(conn, table_name):
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT TOP 1 * FROM [{table_name}]")
        cur.fetchall()
        return [d[0] for d in cur.description] if cur.description else []
    except Exception as e:
        return [f"ERROR: {e}"]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

conn = get_connection()
print("=== Connected successfully ===\n")

# ── 1. All tables matching keywords ──────────────────────────────────────────
keywords = ['Head', 'Sub', 'Acc', 'Party', 'Salesman', 'Item', 'Ledger', 'Master']
where_parts = " OR ".join([f"TABLE_NAME LIKE '%{kw}%'" for kw in keywords])
sql_tables = f"""
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE'
  AND ({where_parts})
ORDER BY TABLE_NAME
"""
_, rows = run_query(conn, sql_tables)
all_tables = [r[0] for r in rows]

print(f"=== TABLES matching keywords ({len(all_tables)} found) ===")
for t in all_tables:
    print(f"  {t}")

# ── 2. Column exploration for specific tables ─────────────────────────────────
mainhead_tables = [t for t in all_tables if 'MainHead' in t]
subhead_tables  = [t for t in all_tables if 'SubHead'  in t]
acchead_tables  = [t for t in all_tables if 'AccHead'  in t]

explore = ['MsPartyMaster', 'MsTransType'] + mainhead_tables + subhead_tables + acchead_tables
seen = set(); explore_dedup = []
for t in explore:
    if t not in seen:
        seen.add(t); explore_dedup.append(t)

print("\n=== COLUMN DETAILS FOR SPECIFIC TABLES ===")
for tbl in explore_dedup:
    cols = get_cols_from_top1(conn, tbl)
    print(f"\nTable: {tbl}")
    print(f"  Columns ({len(cols)}): {', '.join(cols)}")

# ── 3. MsTransType full data ──────────────────────────────────────────────────
print("\n=== MsTransType — ShortName, id_key, TransTypeName ===")
try:
    _, rows2 = run_query(conn, "SELECT DISTINCT ShortName, id_key, TransTypeName FROM MsTransType ORDER BY ShortName")
    print(f"{'ShortName':<15} {'id_key':<10} TransTypeName")
    print("-" * 65)
    for r in rows2:
        print(f"{str(r[0]):<15} {str(r[1]):<10} {r[2]}")
except Exception as e:
    print(f"ERROR: {e}")

# ── 4. Full column dump for every matched table ───────────────────────────────
print("\n=== FULL COLUMN DUMP — ALL MATCHED TABLES ===")
for tbl in all_tables:
    cols = get_cols_from_top1(conn, tbl)
    print(f"\n[{tbl}]")
    for i, c in enumerate(cols, 1):
        print(f"  {i:3}. {c}")

conn.close()
print("\n=== Done ===")

