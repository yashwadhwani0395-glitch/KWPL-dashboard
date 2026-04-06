import pyodbc
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=YOUR_SERVER;"
    "UID=YOUR_USER;"
    "PWD=YOUR_PASSWORD;"
    "TrustServerCertificate=yes;"
)
cur = conn.cursor()
cur.execute("SELECT name FROM sys.databases WHERE name NOT IN ('master','tempdb','model','msdb')")
dbs = [r[0] for r in cur.fetchall()]
print("Databases found:")
for db in dbs:
    print(" -", db)
conn.close()
