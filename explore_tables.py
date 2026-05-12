import pyodbc

conn = pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server};SERVER=182.156.137.121,5235;DATABASE=KW2526;UID=KWPL;PWD=KWPL@123;TrustServerCertificate=yes;')
cursor = conn.cursor()

tables = ['TrVocHead', 'TrVocDetail', 'TrVocItem', 'MsPartyMaster', 'MsItemMaster', 'MsSalesmanMaster']

for table in tables:
    print(f"\n{'='*50}")
    print(f"TABLE: {table}")
    print('='*50)
    cursor.execute(f"SELECT TOP 1 * FROM {table}")
    cols = [desc[0] for desc in cursor.description]
    for col in cols:
        print(f"  {col}")

conn.close()
