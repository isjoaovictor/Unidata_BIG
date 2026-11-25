"""Pure 2D Plotly chart builders styled with REKKI Operate dark tokens."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from unidata.config import UNKNOWN_CATEGORY_LABEL
from unidata.formatting import format_brl, format_int_pt, format_month_pt, format_pct_pt
from unidata.ui.theme import PALETTE

PLOTLY_CONFIG: dict[str, object] = {
    "displayModeBar": False,
    "responsive": True,
}

MONTHLY_METRIC_OPTIONS: dict[str, tuple[str, str, str, str]] = {
    "Receita de produtos (R$)": (
        "product_revenue",
        "Receita de produtos (R$)",
        "R$",
        "brl",
    ),
    "Pedidos entregues (un.)": (
        "delivered_orders",
        "Pedidos entregues (un.)",
        "Pedidos",
        "int",
    ),
    "Ticket médio por pedido (R$)": (
        "avg_ticket",
        "Ticket médio por pedido (R$)",
        "R$",
        "brl",
    ),
}

_SEGMENT_COLORS: tuple[str, ...] = (
    PALETTE["series_primary"],
    PALETTE["series_secondary"],
    PALETTE["series_teal"],
    PALETTE["series_amber"],
)


def _truncate_axis_label(label: str, max_len: int = 24) -> str:
    """Shorten long tick labels for chart legibility while keeping full names in hover/table."""
    clean = str(label).strip()
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 1].rstrip()}…"


def _format_metric_value(value: float, kind: str) -> str:
    """Format a metric scalar according to its display kind."""
    if kind == "brl":
        return format_brl(value)
    return format_int_pt(value)


def _base_dark_layout(title_text: str, height: int = 350) -> dict[str, object]:
    """Return consistent REKKI dark Plotly layout configuration."""
    return {
        "title": {
            "text": title_text,
            "font": {"color": PALETTE["text"], "size": 15},
            "x": 0.0,
            "xanchor": "left",
        },
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": PALETTE["card"],
        "font": {
            "family": "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            "color": PALETTE["text"],
            "size": 12,
        },
        "hoverlabel": {
            "bgcolor": PALETTE["control"],
            "bordercolor": PALETTE["accent"],
            "font": {"color": PALETTE["text"], "size": 12},
        },
        "margin": {"l": 16, "r": 20, "t": 54, "b": 40},
        "height": height,
        "autosize": True,
        "showlegend": False,
    }


def build_monthly_trend_chart(
    monthly_df: pd.DataFrame,
    metric_label: str = "Receita de produtos (R$)",
) -> go.Figure:
    """Build a 2D line+marker Plotly figure for monthly seasonality."""
    col_name, title_suffix, unit_label, kind = MONTHLY_METRIC_OPTIONS.get(
        metric_label,
        MONTHLY_METRIC_OPTIONS["Receita de produtos (R$)"],
    )

    if monthly_df.empty:
        fig = go.Figure()
        fig.update_layout(**_base_dark_layout(f"Padrão histórico observado — {title_suffix}"))
        return fig

    work = monthly_df.sort_values("year_month", ascending=True, kind="mergesort").reset_index(drop=True)
    x_labels = [format_month_pt(str(ym)) for ym in work["year_month"]]
    y_vals = [float(v) for v in work[col_name]]

    hover_texts: list[str] = []
    for _, row in work.iterrows():
        ym_pt = format_month_pt(str(row["year_month"]))
        val_fmt = _format_metric_value(float(row[col_name]), kind)
        orders_fmt = format_int_pt(int(row["delivered_orders"]))
        yoy_raw = row.get("yoy_revenue_pct")
        if yoy_raw is not None and pd.notna(yoy_raw) and math.isfinite(float(yoy_raw)):
            yoy_txt = format_pct_pt(float(yoy_raw))
        else:
            yoy_txt = "Sem base do ano anterior"
        hover_texts.append(
            f"<b>{ym_pt}</b> ({row['year_month']})<br>"
            f"{title_suffix}: {val_fmt}<br>"
            f"Pedidos entregues: {orders_fmt}<br>"
            f"Variação YoY (receita): {yoy_txt}"
        )

    fig = go.Figure(
        data=[
            go.Scatter(
                x=x_labels,
                y=y_vals,
                mode="lines+markers",
                name=title_suffix,
                line={"color": PALETTE["series_primary"], "width": 2.5},
                marker={
                    "color": PALETTE["series_secondary"],
                    "size": 7,
                    "line": {"color": PALETTE["text"], "width": 1},
                },
                customdata=hover_texts,
                hovertemplate="%{customdata}<extra></extra>",
            )
        ]
    )

    layout = _base_dark_layout(f"Padrão histórico observado — {title_suffix}", height=350)
    layout["xaxis"] = {
        "title": {"text": "Mês calendário", "font": {"color": PALETTE["subtle"], "size": 12}},
        "showgrid": False,
        "zeroline": False,
        "tickfont": {"color": PALETTE["subtle"], "size": 11},
        "automargin": True,
        "type": "category",
    }
    yaxis_cfg: dict[str, object] = {
        "title": {"text": unit_label, "font": {"color": PALETTE["subtle"], "size": 12}},
        "showgrid": True,
        "gridcolor": "rgba(255,255,255,0.08)",
        "zeroline": False,
        "tickfont": {"color": PALETTE["subtle"], "size": 11},
        "automargin": True,
        "rangemode": "tozero",
    }
    if kind == "brl":
        yaxis_cfg["tickprefix"] = "R$ "
    layout["yaxis"] = yaxis_cfg

    fig.update_layout(**layout)
    return fig


def build_segment_distribution_chart(cluster_summary: pd.DataFrame) -> go.Figure:
    """Build a 2D horizontal bar chart comparing unique customer share across RFM clusters."""
    title = "Distribuição de clientes únicos por segmento RFM (%)"
    if cluster_summary is None or cluster_summary.empty:
        fig = go.Figure()
        fig.update_layout(**_base_dark_layout(title, height=300))
        return fig

    work = cluster_summary.reset_index(drop=True)
    y_ticks: list[str] = []
    x_pcts: list[float] = []
    bar_texts: list[str] = []
    hover_texts: list[str] = []
    colors: list[str] = []

    for idx, row in work.iterrows():
        full_label = str(row["cluster_label"])
        short_label = full_label.split(" — ", 1)[0].strip() or full_label
        pct = float(row["customer_pct"])
        count = int(row["customer_count"])
        med_r = float(row["median_recency"])
        med_f = float(row["median_frequency"])
        med_m = float(row["median_monetary"])
        avg_t = float(row["avg_ticket"])

        y_ticks.append(short_label)
        x_pcts.append(pct)
        bar_texts.append(f"{format_int_pt(count)} clientes ({format_pct_pt(pct)})")
        colors.append(_SEGMENT_COLORS[idx % len(_SEGMENT_COLORS)])
        hover_texts.append(
            f"<b>{full_label}</b><br>"
            f"Clientes únicos: {format_int_pt(count)} ({format_pct_pt(pct)})<br>"
            f"Recência mediana: {format_int_pt(med_r)} dia(s)<br>"
            f"Frequência mediana: {med_f:.1f} pedido(s)<br>"
            f"Gasto mediano: {format_brl(med_m)}<br>"
            f"Ticket médio: {format_brl(avg_t)}"
        )

    fig = go.Figure(
        data=[
            go.Bar(
                x=x_pcts,
                y=y_ticks,
                orientation="h",
                text=bar_texts,
                textposition="auto",
                insidetextfont={"color": PALETTE["text"], "size": 11},
                outsidetextfont={"color": PALETTE["text"], "size": 11},
                marker={"color": colors, "line": {"color": "rgba(255,255,255,0.2)", "width": 1}},
                customdata=hover_texts,
                hovertemplate="%{customdata}<extra></extra>",
            )
        ]
    )

    layout = _base_dark_layout(title, height=max(260, 56 * len(work) + 100))
    layout["xaxis"] = {
        "title": {"text": "Participação de clientes únicos (%)", "font": {"color": PALETTE["subtle"], "size": 12}},
        "showgrid": True,
        "gridcolor": "rgba(255,255,255,0.08)",
        "zeroline": False,
        "tickfont": {"color": PALETTE["subtle"], "size": 11},
        "ticksuffix": "%",
        "range": [0, max(100.0, max(x_pcts, default=0.0) * 1.15)],
        "automargin": True,
    }
    layout["yaxis"] = {
        "autorange": "reversed",
        "showgrid": False,
        "tickfont": {"color": PALETTE["text"], "size": 12},
        "automargin": True,
        "type": "category",
    }

    fig.update_layout(**layout)
    return fig


def build_category_ranking_chart(
    categories_df: pd.DataFrame,
    top_n: int = 10,
) -> go.Figure:
    """Build a 2D horizontal bar chart ranking top categories by product revenue (R$)."""
    title = "Categorias por receita de produtos (R$)"
    if categories_df is None or categories_df.empty:
        fig = go.Figure()
        fig.update_layout(**_base_dark_layout(title, height=320))
        return fig

    work = categories_df.head(max(1, int(top_n))).reset_index(drop=True)
    y_ticks: list[str] = []
    x_revs: list[float] = []
    bar_texts: list[str] = []
    hover_texts: list[str] = []
    colors: list[str] = []

    seen_ticks: dict[str, int] = {}
    for _, row in work.iterrows():
        full_cat = str(row["category"])
        rev = float(row["product_revenue"])
        share = float(row["revenue_share_pct"])
        items = int(row["items_count"])
        orders = int(row["delivered_orders"])

        tick = _truncate_axis_label(full_cat, max_len=24)
        count_seen = seen_ticks.get(tick, 0)
        seen_ticks[tick] = count_seen + 1
        if count_seen > 0:
            tick = f"{tick} ({count_seen + 1})"

        y_ticks.append(tick)
        x_revs.append(rev)
        bar_texts.append(f"{format_brl(rev)} ({format_pct_pt(share)})")
        colors.append(
            PALETTE["muted"] if full_cat == UNKNOWN_CATEGORY_LABEL else PALETTE["series_primary"]
        )
        hover_texts.append(
            f"<b>{full_cat}</b><br>"
            f"Receita de produtos: {format_brl(rev)}<br>"
            f"Participação: {format_pct_pt(share)}<br>"
            f"Itens vendidos: {format_int_pt(items)}<br>"
            f"Pedidos entregues: {format_int_pt(orders)}"
        )

    fig = go.Figure(
        data=[
            go.Bar(
                x=x_revs,
                y=y_ticks,
                orientation="h",
                text=bar_texts,
                textposition="auto",
                insidetextfont={"color": PALETTE["text"], "size": 11},
                outsidetextfont={"color": PALETTE["text"], "size": 11},
                marker={"color": colors, "line": {"color": "rgba(255,255,255,0.16)", "width": 1}},
                customdata=hover_texts,
                hovertemplate="%{customdata}<extra></extra>",
            )
        ]
    )

    max_rev = max(x_revs, default=0.0)
    layout = _base_dark_layout(title, height=max(280, 40 * len(work) + 110))
    layout["xaxis"] = {
        "title": {"text": "Receita de produtos (R$)", "font": {"color": PALETTE["subtle"], "size": 12}},
        "showgrid": True,
        "gridcolor": "rgba(255,255,255,0.08)",
        "zeroline": False,
        "tickprefix": "R$ ",
        "tickfont": {"color": PALETTE["subtle"], "size": 11},
        "range": [0, max_rev * 1.28 if max_rev > 0 else 1.0],
        "automargin": True,
    }
    layout["yaxis"] = {
        "autorange": "reversed",
        "showgrid": False,
        "tickfont": {"color": PALETTE["text"], "size": 12},
        "automargin": True,
        "type": "category",
    }

    fig.update_layout(**layout)
    return fig
