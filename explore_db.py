"""
explore_db.py
Connects to MS SQL Server and prints a full schema report:
  - All tables (with row counts and column schemas)
  - All views (with column schemas)
  - All stored procedures
  - Foreign key relationships
"""

import os
import sys
import pyodbc
from dotenv import load_dotenv

load_dotenv()

SERVER   = os.getenv("DB_SERVER", "192.168.1.50")
PORT     = os.getenv("DB_PORT", "1433")
DATABASE = os.getenv("DB_NAME")
USERNAME = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER   = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

if not all([DATABASE, USERNAME, PASSWORD]):
    sys.exit("ERROR: DB_NAME, DB_USER, and DB_PASSWORD must be set in .env")

CONN_STR = (
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER},{PORT};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
)

DIVIDER      = "=" * 80
THIN_DIVIDER = "-" * 60


def connect():
    try:
        conn = pyodbc.connect(CONN_STR, timeout=10)
        return conn
    except pyodbc.Error as e:
        sys.exit(f"Connection failed:\n{e}")


# ── Tables ────────────────────────────────────────────────────────────────────

TABLES_SQL = """
SELECT
    t.TABLE_SCHEMA,
    t.TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES t
WHERE t.TABLE_TYPE = 'BASE TABLE'
ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
"""

COLUMNS_SQL = """
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.CHARACTER_MAXIMUM_LENGTH,
    c.NUMERIC_PRECISION,
    c.NUMERIC_SCALE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    CASE WHEN kcu.COLUMN_NAME IS NOT NULL THEN 'PK' ELSE '' END AS PK_FLAG
FROM INFORMATION_SCHEMA.COLUMNS c
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON kcu.TABLE_SCHEMA = c.TABLE_SCHEMA
   AND kcu.TABLE_NAME  = c.TABLE_NAME
   AND kcu.COLUMN_NAME = c.COLUMN_NAME
   AND kcu.CONSTRAINT_NAME LIKE 'PK%'
WHERE c.TABLE_SCHEMA = ?
  AND c.TABLE_NAME   = ?
ORDER BY c.ORDINAL_POSITION
"""

ROW_COUNT_SQL = "SELECT COUNT(*) FROM [{schema}].[{table}]"


def print_tables(cursor):
    print(f"\n{DIVIDER}")
    print("TABLES")
    print(DIVIDER)

    cursor.execute(TABLES_SQL)
    tables = cursor.fetchall()

    if not tables:
        print("  (no user tables found)")
        return

    for schema, table in tables:
        # Row count
        try:
            cursor.execute(ROW_COUNT_SQL.format(schema=schema, table=table))
            row_count = cursor.fetchone()[0]
        except Exception:
            row_count = "N/A"

        print(f"\n  [{schema}].[{table}]  —  {row_count:,} rows" if isinstance(row_count, int)
              else f"\n  [{schema}].[{table}]  —  rows: {row_count}")
        print(f"  {THIN_DIVIDER}")

        cursor.execute(COLUMNS_SQL, schema, table)
        cols = cursor.fetchall()
        header = f"  {'#':<4} {'Column':<35} {'Type':<20} {'Nullable':<10} {'Default':<20} {'PK'}"
        print(header)
        print(f"  {'-'*4} {'-'*35} {'-'*20} {'-'*10} {'-'*20} {'--'}")

        for i, (col_name, dtype, char_len, num_prec, num_scale,
                nullable, default, pk) in enumerate(cols, 1):
            # Build a readable type string
            if char_len:
                type_str = f"{dtype}({char_len})"
            elif num_prec and dtype in ("decimal", "numeric"):
                type_str = f"{dtype}({num_prec},{num_scale or 0})"
            else:
                type_str = dtype

            default_str = (str(default)[:18] if default else "")
            print(f"  {i:<4} {col_name:<35} {type_str:<20} {nullable:<10} {default_str:<20} {pk}")


# ── Views ─────────────────────────────────────────────────────────────────────

VIEWS_SQL = """
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.VIEWS
ORDER BY TABLE_SCHEMA, TABLE_NAME
"""

VIEW_COLUMNS_SQL = """
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.CHARACTER_MAXIMUM_LENGTH,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_SCHEMA = ?
  AND c.TABLE_NAME   = ?
ORDER BY c.ORDINAL_POSITION
"""


def print_views(cursor):
    print(f"\n{DIVIDER}")
    print("VIEWS")
    print(DIVIDER)

    cursor.execute(VIEWS_SQL)
    views = cursor.fetchall()

    if not views:
        print("  (no views found)")
        return

    for schema, view in views:
        print(f"\n  [{schema}].[{view}]")
        cursor.execute(VIEW_COLUMNS_SQL, schema, view)
        cols = cursor.fetchall()
        for col_name, dtype, char_len, nullable in cols:
            type_str = f"{dtype}({char_len})" if char_len else dtype
            print(f"    {col_name:<35} {type_str:<20} nullable={nullable}")


# ── Stored Procedures ─────────────────────────────────────────────────────────

PROCS_SQL = """
SELECT
    r.ROUTINE_SCHEMA,
    r.ROUTINE_NAME,
    r.ROUTINE_TYPE
FROM INFORMATION_SCHEMA.ROUTINES r
WHERE r.ROUTINE_TYPE IN ('PROCEDURE', 'FUNCTION')
ORDER BY r.ROUTINE_TYPE, r.ROUTINE_SCHEMA, r.ROUTINE_NAME
"""

PROC_PARAMS_SQL = """
SELECT
    p.PARAMETER_NAME,
    p.DATA_TYPE,
    p.PARAMETER_MODE,
    p.CHARACTER_MAXIMUM_LENGTH,
    p.NUMERIC_PRECISION,
    p.NUMERIC_SCALE
FROM INFORMATION_SCHEMA.PARAMETERS p
WHERE p.SPECIFIC_SCHEMA = ?
  AND p.SPECIFIC_NAME   = ?
ORDER BY p.ORDINAL_POSITION
"""


def print_procedures(cursor):
    print(f"\n{DIVIDER}")
    print("STORED PROCEDURES & FUNCTIONS")
    print(DIVIDER)

    cursor.execute(PROCS_SQL)
    procs = cursor.fetchall()

    if not procs:
        print("  (none found)")
        return

    for schema, name, rtype in procs:
        print(f"\n  [{rtype}]  [{schema}].[{name}]")
        cursor.execute(PROC_PARAMS_SQL, schema, name)
        params = cursor.fetchall()
        if params:
            for pname, dtype, mode, char_len, num_prec, num_scale in params:
                if char_len:
                    type_str = f"{dtype}({char_len})"
                elif num_prec and dtype in ("decimal", "numeric"):
                    type_str = f"{dtype}({num_prec},{num_scale or 0})"
                else:
                    type_str = dtype
                print(f"    {mode:<5} {pname or '(return)':<35} {type_str}")
        else:
            print("    (no parameters)")


# ── Foreign Keys ──────────────────────────────────────────────────────────────

FK_SQL = """
SELECT
    fk.name                        AS fk_name,
    OBJECT_SCHEMA_NAME(fk.parent_object_id)         AS from_schema,
    OBJECT_NAME(fk.parent_object_id)                AS from_table,
    COL_NAME(fkc.parent_object_id,  fkc.parent_column_id)   AS from_column,
    OBJECT_SCHEMA_NAME(fk.referenced_object_id)     AS to_schema,
    OBJECT_NAME(fk.referenced_object_id)            AS to_table,
    COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS to_column,
    fk.delete_referential_action_desc,
    fk.update_referential_action_desc
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc
    ON fk.object_id = fkc.constraint_object_id
ORDER BY from_schema, from_table, fk_name
"""


def print_foreign_keys(cursor):
    print(f"\n{DIVIDER}")
    print("FOREIGN KEY RELATIONSHIPS")
    print(DIVIDER)

    cursor.execute(FK_SQL)
    fks = cursor.fetchall()

    if not fks:
        print("  (no foreign keys found)")
        return

    current_fk = None
    for (fk_name, from_schema, from_table, from_col,
         to_schema, to_table, to_col,
         del_action, upd_action) in fks:
        if fk_name != current_fk:
            current_fk = fk_name
            print(f"\n  {fk_name}")
            print(f"    [{from_schema}].[{from_table}].{from_col}")
            print(f"    --> [{to_schema}].[{to_table}].{to_col}")
            print(f"    ON DELETE {del_action}  |  ON UPDATE {upd_action}")


# ── Indexes ───────────────────────────────────────────────────────────────────

INDEX_SQL = """
SELECT
    OBJECT_SCHEMA_NAME(i.object_id)  AS schema_name,
    OBJECT_NAME(i.object_id)         AS table_name,
    i.name                           AS index_name,
    i.type_desc,
    i.is_unique,
    i.is_primary_key,
    STRING_AGG(c.name, ', ')
        WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns
FROM sys.indexes i
JOIN sys.index_columns ic ON ic.object_id = i.object_id
                          AND ic.index_id  = i.index_id
JOIN sys.columns c        ON c.object_id  = i.object_id
                          AND c.column_id  = ic.column_id
WHERE OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1
  AND i.name IS NOT NULL
GROUP BY i.object_id, i.name, i.type_desc, i.is_unique, i.is_primary_key
ORDER BY schema_name, table_name, i.is_primary_key DESC, index_name
"""


def print_indexes(cursor):
    print(f"\n{DIVIDER}")
    print("INDEXES")
    print(DIVIDER)

    try:
        cursor.execute(INDEX_SQL)
        indexes = cursor.fetchall()
    except Exception:
        # STRING_AGG requires SQL Server 2017+; fall back gracefully
        print("  (index listing skipped — requires SQL Server 2017+)")
        return

    if not indexes:
        print("  (no indexes found)")
        return

    current_table = None
    for schema, table, idx_name, idx_type, is_unique, is_pk, columns in indexes:
        key = f"[{schema}].[{table}]"
        if key != current_table:
            current_table = key
            print(f"\n  {key}")
        flags = []
        if is_pk:
            flags.append("PRIMARY KEY")
        if is_unique:
            flags.append("UNIQUE")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"    {idx_name:<50} {idx_type:<15}{flag_str}")
        print(f"      columns: {columns}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nConnecting to {SERVER},{PORT} / {DATABASE} ...")
    conn = connect()
    cursor = conn.cursor()
    print("Connected.\n")

    print_tables(cursor)
    print_views(cursor)
    print_procedures(cursor)
    print_foreign_keys(cursor)
    print_indexes(cursor)

    cursor.close()
    conn.close()

    print(f"\n{DIVIDER}")
    print("Exploration complete.")
    print(DIVIDER)


if __name__ == "__main__":
    main()
