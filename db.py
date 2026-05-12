import os
import pymssql
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def _cfg(key: str, default: str = "") -> str:
    """Read config from st.secrets (Streamlit Cloud) or .env (local)."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def get_connection():
    server_raw = _cfg("DB_SERVER", "localhost")
    # Support "host,port" format used in pyodbc connection strings
    if "," in server_raw:
        host, port = server_raw.split(",", 1)
    else:
        host, port = server_raw, "1433"

    return pymssql.connect(
        server=host.strip(),
        port=port.strip(),
        user=_cfg("DB_USER"),
        password=_cfg("DB_PASSWORD"),
        database=_cfg("DB_NAME"),
        tds_version="7.4",
        login_timeout=15,
    )


def query(sql: str, params=None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql(sql, conn, params=params)
