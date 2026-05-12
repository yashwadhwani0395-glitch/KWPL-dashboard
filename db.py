import os
import pyodbc
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

CONN_STR = (
    f"DRIVER={{{os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')}}};"
    f"SERVER={os.getenv('DB_SERVER')};"
    f"DATABASE={os.getenv('DB_NAME')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
    f"TrustServerCertificate=yes;"
)

SALES_TYPES = (9,13,18,19,23,27,34,35,38,39,40,41,44,47,49,50,51,52,53)
PURCHASE_TYPES = (11,20,22,30,32,33,36,42,45,46,48,54)


def get_connection():
    return pyodbc.connect(CONN_STR)


def query(sql: str, params=None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(sql, conn, params=params)
