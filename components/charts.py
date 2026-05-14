import plotly.express as px
import plotly.graph_objects as go
from config import COLORS


def bar_chart(df, x, y, title="", color=None, orientation="v", color_scale=None, yaxis_title=""):
    if orientation == "h":
        fig = px.bar(df, x=y, y=x, orientation="h",
                     labels={y: "", x: ""},
                     color=y if color_scale else None,
                     color_continuous_scale=color_scale)
        fig.update_layout(yaxis={"categoryorder": "total ascending"},
                          coloraxis_showscale=False)
    else:
        fig = px.bar(df, x=x, y=y,
                     labels={x: "", y: ""},
                     color=y if color_scale else None,
                     color_continuous_scale=color_scale,
                     color_discrete_sequence=[color or COLORS["primary"]])
        fig.update_layout(xaxis_tickangle=-45, coloraxis_showscale=False)
    fig.update_layout(title=title, margin=dict(t=40 if title else 10, b=10))
    if yaxis_title:
        fig.update_layout(yaxis_title=yaxis_title)
    return fig


def line_chart(df, x, y_cols: list[dict], title="", yaxis_title=""):
    """y_cols: [{"col": "sales", "name": "Sales", "color": "#hex"}]"""
    fig = go.Figure()
    for y in y_cols:
        fig.add_trace(go.Scatter(
            name=y["name"], x=df[x], y=df[y["col"]],
            mode="lines+markers",
            line=dict(color=y.get("color", COLORS["primary"]))
        ))
    fig.update_layout(title=title, margin=dict(t=40 if title else 10, b=10),
                      legend=dict(orientation="h", y=1.1))
    if yaxis_title:
        fig.update_layout(yaxis_title=yaxis_title)
    return fig


def grouped_bar(df, x, series: list[dict], title="", yaxis_title=""):
    """series: [{"col": "sales", "name": "Sales", "color": "#hex"}]"""
    fig = go.Figure()
    for s in series:
        fig.add_trace(go.Bar(
            name=s["name"], x=df[x], y=df[s["col"]],
            marker_color=s.get("color", COLORS["primary"])
        ))
    fig.update_layout(barmode="group", title=title,
                      margin=dict(t=40 if title else 10, b=10),
                      legend=dict(orientation="h", y=1.1),
                      yaxis_title="₹")
    if yaxis_title:
        fig.update_layout(yaxis_title=yaxis_title)
    return fig


def pie_chart(df, names, values, title="", colors=None):
    fig = px.pie(df, names=names, values=values,
                 color_discrete_sequence=colors or px.colors.qualitative.Set2)
    fig.update_layout(title=title, margin=dict(t=40 if title else 10, b=10))
    return fig


def area_chart(df, x, y_cols: list[dict], title="", yaxis_title=""):
    fig = go.Figure()
    for y in y_cols:
        fig.add_trace(go.Scatter(
            name=y["name"], x=df[x], y=df[y["col"]],
            fill="tozeroy",
            line=dict(color=y.get("color", COLORS["primary"]))
        ))
    fig.update_layout(title=title, margin=dict(t=40 if title else 10, b=10),
                      legend=dict(orientation="h", y=1.1), yaxis_title="₹")
    if yaxis_title:
        fig.update_layout(yaxis_title=yaxis_title)
    return fig
