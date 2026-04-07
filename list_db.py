import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

SERVER   = os.getenv("DB_SERVER", "192.168.1.50")
PORT     = os.getenv("DB_PORT", "1433")
USERNAME = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
DRIVER   = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

conn = pyodbc.connect(
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER},{PORT};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    "TrustServerCertificate=yes;"
)
cur = conn.cursor()
cur.execute("SELECT name FROM sys.databases WHERE name NOT IN ('master','tempdb','model','msdb')")
dbs = [r[0] for r in cur.fetchall()]
print("Databases found:")
for db in dbs:
    print(" -", db)
conn.close()
