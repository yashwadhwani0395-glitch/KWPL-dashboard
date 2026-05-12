import streamlit as st
from utils import fmt_inr, fmt_qty


def kpi_row(metrics: list[dict]):
    """
    Render a row of KPI metric cards.

    Each dict in metrics:
      { "label": str, "value": any, "fmt": "inr"|"qty"|"raw", "delta": optional str }
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        fmt = m.get("fmt", "raw")
        val = m["value"]
        if fmt == "inr":
            display = fmt_inr(val)
        elif fmt == "qty":
            display = fmt_qty(val)
        else:
            display = str(val)
        col.metric(label=m["label"], value=display, delta=m.get("delta"))
