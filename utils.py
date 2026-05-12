def fmt_inr(val) -> str:
    """Format a number as Indian currency string (Cr / L / raw)."""
    val = float(val or 0)
    if val >= 1_00_00_000:
        return f"₹{val / 1_00_00_000:.2f} Cr"
    elif val >= 1_00_000:
        return f"₹{val / 1_00_000:.2f} L"
    return f"₹{val:,.0f}"


def fmt_qty(val) -> str:
    return f"{int(val or 0):,}"


def fmt_date(series):
    import pandas as pd
    return pd.to_datetime(series).dt.strftime("%d-%b-%Y")


def month_col(df):
    """Convert yr + mo columns into a datetime month column."""
    import pandas as pd
    df["month"] = pd.to_datetime(
        df["yr"].astype(str) + "-" + df["mo"].astype(str) + "-01"
    )
    return df
