import os
import threading
import pymssql
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_lock = threading.Lock()
_pool: list = []
_MAX_POOL = 8


def _cfg(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _new_conn():
    server_raw = _cfg("DB_SERVER", "localhost")
    host, port = server_raw.split(",", 1) if "," in server_raw else (server_raw, "1433")
    return pymssql.connect(
        server=host.strip(), port=port.strip(),
        user=_cfg("DB_USER"), password=_cfg("DB_PASSWORD"),
        database=_cfg("DB_NAME"), tds_version="7.4", login_timeout=15,
    )


def get_connection():
    with _lock:
        while _pool:
            conn = _pool.pop()
            try:
                conn.cursor().execute("SELECT 1")
                return conn
            except Exception:
                pass
    return _new_conn()


def _release(conn):
    with _lock:
        if len(_pool) < _MAX_POOL:
            _pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


@st.cache_data(ttl=1800, show_spinner=False)
def query(sql: str, params=None) -> pd.DataFrame:
    conn = get_connection()
    ok = False
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        if not rows:
            cols = [d[0] for d in cursor.description] if cursor.description else []
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(rows)
        ok = True
        return df
    finally:
        if ok:
            _release(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass
