"""Deterministic explainable recommendations engine with numeric evidence and caveats."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

import numpy as np
import pandas as pd

from unidata.analytics import KPISummary
from unidata.config import UNKNOWN_CATEGORY_LABEL
from unidata.formatting import (
    format_brl,
    format_date_pt,
    format_int_pt,
    format_month_pt,
    format_pct_pt,
)
from unidata.segmentation import SegmentationResult

_YM_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

_CATEGORY_PRIORITY: dict[str, int] = {
    "Clientes": 0,
    "Sazonalidade": 1,
    "Produtos": 2,
}

_HISTORICAL_CAVEAT_PT: str = (
    "Padrão histórico observado na base Olist (recorte analisado); "
    "não estabelece relação causal nem projeção de vendas futuras."
)


@dataclass(frozen=True)
class Recommendation:
    """Explainable recommendation card backed by observed metrics and non-causal caveat."""

    category: str
    title: str
    observation: str
    evidence: str
    period: str
    caveat: str
    strength: float


def _format_scalar_pt(value: float) -> str:
    """Format a scalar count/days metric neatly in pt-BR."""
    if float(value).is_integer():
        return format_int_pt(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def _evaluate_customer_rules(
    seg_result: SegmentationResult | None,
    period_label: str,
    rfm_scope_label: str,
) -> list[Recommendation]:
    """Generate cautious customer-segment recommendations when segmentation succeeded."""
    if (
        seg_result is None
        or not seg_result.ok
        or seg_result.cluster_summary is None
        or seg_result.cluster_summary.empty
        or seg_result.customer_count <= 0
    ):
        return []

    required_cols = {
        "cluster_label",
        "customer_count",
        "customer_pct",
        "median_recency",
        "median_frequency",
        "median_monetary",
    }
    summary = seg_result.cluster_summary
    if not required_cols.issubset(set(summary.columns)):
        return []

    work = summary.copy()
    numeric_cols = (
        "customer_count",
        "customer_pct",
        "median_recency",
        "median_frequency",
        "median_monetary",
    )
    for col in numeric_cols:
        work[col] = pd.to_numeric(work[col], errors="coerce").astype("float64")

    valid_mask = work["cluster_label"].notna() & (work["customer_count"] > 0)
    for col in numeric_cols:
        valid_mask &= work[col].notna() & np.isfinite(work[col])

    work = work.loc[valid_mask].copy()
    if work.empty:
        return []

    work["cluster_label"] = work["cluster_label"].astype(str).str.strip()
    work = work.loc[work["cluster_label"] != ""].copy()
    if work.empty:
        return []

    ref_str = (
        format_date_pt(seg_result.reference_date)
        if pd.notna(seg_result.reference_date)
        else "—"
    )
    if ref_str != "—":
        scope_text = f"{rfm_scope_label} (recorte exibido: {period_label}; ref.: {ref_str})"
    else:
        scope_text = f"{rfm_scope_label} (recorte exibido: {period_label})"

    by_monetary = work.sort_values(
        by=["median_monetary", "customer_count", "median_recency", "cluster_label"],
        ascending=[False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)

    top_seg = by_monetary.iloc[0]
    top_label = str(top_seg["cluster_label"])
    top_count = int(round(float(top_seg["customer_count"])))
    top_pct = float(top_seg["customer_pct"])
    top_recency = float(top_seg["median_recency"])
    top_freq = float(top_seg["median_frequency"])
    top_monetary = float(top_seg["median_monetary"])

    recs: list[Recommendation] = []
    if top_monetary > 0.0:
        max_med_m = float(work["median_monetary"].max())
        min_med_m = float(work["median_monetary"].min())
        spread_ratio = (
            (max_med_m - min_med_m) / max_med_m if max_med_m > 0.0 else 0.0
        )
        strength = min(0.95, 0.72 + 0.18 * spread_ratio + 0.05 * min(1.0, top_pct / 50.0))

        recs.append(
            Recommendation(
                category="Clientes",
                title=f"Avalie campanhas direcionadas ao {top_label}",
                observation=(
                    f"Avalie priorizar comunicações segmentadas para '{top_label}': "
                    f"o grupo concentra {format_pct_pt(top_pct)} dos clientes segmentados "
                    f"e apresenta o maior gasto mediano observado ({format_brl(top_monetary)})."
                ),
                evidence=(
                    f"Clientes: {format_int_pt(top_count)} ({format_pct_pt(top_pct)}); "
                    f"gasto mediano {format_brl(top_monetary)}; "
                    f"frequência mediana {_format_scalar_pt(top_freq)} pedido(s); "
                    f"recência mediana {_format_scalar_pt(top_recency)} dia(s)."
                ),
                period=scope_text,
                caveat=_HISTORICAL_CAVEAT_PT,
                strength=round(strength, 4),
            )
        )

    remaining = work.loc[work["cluster_label"] != top_label].copy()
    if not remaining.empty:
        by_reactivation = remaining.sort_values(
            by=["customer_pct", "median_recency", "customer_count", "cluster_label"],
            ascending=[False, False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)
        alt_seg = by_reactivation.iloc[0]
        alt_pct = float(alt_seg["customer_pct"])
        alt_recency = float(alt_seg["median_recency"])
        global_med_r = float(work["median_recency"].median())

        if alt_pct >= 20.0 or alt_recency > global_med_r:
            alt_label = str(alt_seg["cluster_label"])
            alt_count = int(round(float(alt_seg["customer_count"])))
            alt_freq = float(alt_seg["median_frequency"])
            alt_monetary = float(alt_seg["median_monetary"])
            alt_strength = min(0.75, 0.45 + 0.25 * min(1.0, alt_pct / 50.0))

            recs.append(
                Recommendation(
                    category="Clientes",
                    title=f"Investigue ações de reativação para o {alt_label}",
                    observation=(
                        f"Investigue iniciativas de reativação para '{alt_label}': "
                        f"reúne {format_pct_pt(alt_pct)} da base analisada com recência mediana "
                        f"de {_format_scalar_pt(alt_recency)} dia(s)."
                    ),
                    evidence=(
                        f"Clientes: {format_int_pt(alt_count)} ({format_pct_pt(alt_pct)}); "
                        f"recência mediana {_format_scalar_pt(alt_recency)} dia(s); "
                        f"frequência mediana {_format_scalar_pt(alt_freq)} pedido(s); "
                        f"gasto mediano {format_brl(alt_monetary)}."
                    ),
                    period=scope_text,
                    caveat=_HISTORICAL_CAVEAT_PT,
                    strength=round(alt_strength, 4),
                )
            )

    return recs


def _evaluate_seasonality_rules(
    monthly_df: pd.DataFrame | None,
    period_label: str,
) -> list[Recommendation]:
    """Generate seasonality recommendations when >= 2 active months show distinct revenue."""
    if monthly_df is None or monthly_df.empty:
        return []

    required_cols = {"year_month", "product_revenue", "delivered_orders"}
    if not required_cols.issubset(set(monthly_df.columns)):
        return []

    work = monthly_df.copy()
    work["year_month"] = work["year_month"].astype("string").str.strip()
    work["product_revenue"] = pd.to_numeric(
        work["product_revenue"], errors="coerce"
    ).astype("float64")
    work["delivered_orders"] = pd.to_numeric(
        work["delivered_orders"], errors="coerce"
    ).astype("float64")

    valid = work.loc[
        work["year_month"].notna()
        & (work["year_month"] != "")
        & work["product_revenue"].notna()
        & np.isfinite(work["product_revenue"])
        & work["delivered_orders"].notna()
        & np.isfinite(work["delivered_orders"])
        & (work["delivered_orders"] > 0)
        & (work["product_revenue"] >= 0.0)
    ].copy()

    if len(valid) < 2:
        return []

    valid = valid.loc[
        valid["year_month"].map(
            lambda ym: _YM_REGEX.fullmatch(str(ym)) is not None
            and format_month_pt(str(ym)) != "—"
        )
    ].copy()
    if len(valid) < 2:
        return []

    max_rev = float(valid["product_revenue"].max())
    min_rev = float(valid["product_revenue"].min())
    if max_rev <= 0.0 or math.isclose(max_rev, min_rev, rel_tol=1e-9, abs_tol=1e-9):
        return []

    total_rev = float(valid["product_revenue"].sum())
    by_rev_desc = valid.sort_values(
        by=["product_revenue", "delivered_orders", "year_month"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    by_rev_asc = valid.sort_values(
        by=["product_revenue", "delivered_orders", "year_month"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)

    peak = by_rev_desc.iloc[0]
    trough = by_rev_asc.iloc[0]

    peak_ym = str(peak["year_month"])
    peak_label = format_month_pt(peak_ym)
    trough_ym = str(trough["year_month"])
    trough_label = format_month_pt(trough_ym)
    if peak_label == "—" or trough_label == "—":
        return []
    peak_rev = float(peak["product_revenue"])
    peak_orders = int(round(float(peak["delivered_orders"])))
    peak_share_pct = (peak_rev / total_rev * 100.0) if total_rev > 0.0 else 0.0

    trough_rev = float(trough["product_revenue"])
    trough_orders = int(round(float(trough["delivered_orders"])))

    yoy_note = ""
    if "yoy_revenue_pct" in valid.columns and pd.notna(peak.get("yoy_revenue_pct")):
        yoy_val = float(peak["yoy_revenue_pct"])
        if math.isfinite(yoy_val):
            yoy_note = f"; variação interanual (YoY): {format_pct_pt(yoy_val)}"

    if len(by_rev_desc) >= 3:
        second = by_rev_desc.iloc[1]
        second_ym = str(second["year_month"])
        second_label = format_month_pt(second_ym)
        second_rev = float(second["product_revenue"])
        obs_extra = (
            f" seguido por {second_label} ({format_brl(second_rev)})"
            if second_label != "—"
            else ""
        )
    else:
        obs_extra = ""

    amplitude_ratio = (max_rev - min_rev) / max_rev if max_rev > 0.0 else 0.0
    strength = min(0.92, 0.58 + 0.34 * amplitude_ratio)

    return [
        Recommendation(
            category="Sazonalidade",
            title=f"Investigue o pico sazonal observado em {peak_label}",
            observation=(
                f"Investigue o calendário de campanhas em torno de {peak_label}, "
                f"mês com maior receita de produtos observada no período ({format_brl(peak_rev)})"
                f"{obs_extra}; em contraste, {trough_label} registrou o menor volume ({format_brl(trough_rev)})."
            ),
            evidence=(
                f"Pico em {peak_label}: {format_brl(peak_rev)} ({format_pct_pt(peak_share_pct)} "
                f"da receita do período, {format_int_pt(peak_orders)} pedido(s){yoy_note}). "
                f"Menor mês: {trough_label} com {format_brl(trough_rev)} "
                f"({format_int_pt(trough_orders)} pedido(s))."
            ),
            period=period_label,
            caveat=_HISTORICAL_CAVEAT_PT,
            strength=round(strength, 4),
        )
    ]


def _evaluate_product_rules(
    categories_df: pd.DataFrame | None,
    period_label: str,
) -> list[Recommendation]:
    """Generate product category recommendations while handling 'Não informado' honestly."""
    if categories_df is None or categories_df.empty:
        return []

    required_cols = {
        "category",
        "product_revenue",
        "revenue_share_pct",
        "items_count",
        "delivered_orders",
    }
    if not required_cols.issubset(set(categories_df.columns)):
        return []

    work = categories_df.copy()
    work["category"] = work["category"].astype("string").str.strip()
    for col in ("product_revenue", "revenue_share_pct", "items_count", "delivered_orders"):
        work[col] = pd.to_numeric(work[col], errors="coerce")

    valid = work.loc[
        work["category"].notna()
        & (work["category"] != "")
        & work["product_revenue"].notna()
        & (work["product_revenue"] > 0.0)
        & work["revenue_share_pct"].notna()
        & work["items_count"].notna()
        & work["delivered_orders"].notna()
    ].copy()

    if valid.empty:
        return []

    valid = valid.loc[
        valid["product_revenue"].map(math.isfinite)
        & valid["revenue_share_pct"].map(math.isfinite)
        & valid["items_count"].map(math.isfinite)
        & valid["delivered_orders"].map(math.isfinite)
    ].copy()
    if valid.empty:
        return []

    valid = valid.sort_values(
        by=["product_revenue", "delivered_orders", "items_count", "category"],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)

    top_row = valid.iloc[0]
    top_cat = str(top_row["category"])
    top_rev = float(top_row["product_revenue"])
    top_share = float(top_row["revenue_share_pct"])
    top_items = int(round(float(top_row["items_count"])))
    top_orders = int(round(float(top_row["delivered_orders"])))

    recs: list[Recommendation] = []

    if top_cat == UNKNOWN_CATEGORY_LABEL:
        recs.append(
            Recommendation(
                category="Produtos",
                title=f"Investigue a classificação de catálogo em '{UNKNOWN_CATEGORY_LABEL}'",
                observation=(
                    f"Investigue o preenchimento de categorias no catálogo: itens sem categoria "
                    f"informada ('{UNKNOWN_CATEGORY_LABEL}') lideraram o recorte com "
                    f"{format_pct_pt(top_share)} da receita observada, o que indica lacuna de cadastro."
                ),
                evidence=(
                    f"Categoria '{UNKNOWN_CATEGORY_LABEL}': {format_brl(top_rev)} "
                    f"({format_pct_pt(top_share)} da receita), {format_int_pt(top_items)} item(ns) "
                    f"em {format_int_pt(top_orders)} pedido(s)."
                ),
                period=period_label,
                caveat=_HISTORICAL_CAVEAT_PT,
                strength=round(min(0.88, 0.55 + 0.30 * min(1.0, top_share / 100.0)), 4),
            )
        )

        named = valid.loc[valid["category"] != UNKNOWN_CATEGORY_LABEL].reset_index(drop=True)
        if not named.empty:
            lead_named = named.iloc[0]
            named_cat = str(lead_named["category"])
            named_rev = float(lead_named["product_revenue"])
            named_share = float(lead_named["revenue_share_pct"])
            named_items = int(round(float(lead_named["items_count"])))
            named_orders = int(round(float(lead_named["delivered_orders"])))

            recs.append(
                Recommendation(
                    category="Produtos",
                    title=f"Considere destacar a categoria identificada '{named_cat}'",
                    observation=(
                        f"Considere avaliar campanhas para '{named_cat}', principal categoria "
                        f"identificada no recorte com {format_brl(named_rev)} em receita de produtos."
                    ),
                    evidence=(
                        f"Categoria '{named_cat}': {format_brl(named_rev)} "
                        f"({format_pct_pt(named_share)} da receita), {format_int_pt(named_items)} item(ns) "
                        f"em {format_int_pt(named_orders)} pedido(s)."
                    ),
                    period=period_label,
                    caveat=_HISTORICAL_CAVEAT_PT,
                    strength=round(min(0.80, 0.45 + 0.30 * min(1.0, named_share / 100.0)), 4),
                )
            )
    else:
        strength = min(0.90, 0.56 + 0.34 * min(1.0, top_share / 100.0))
        recs.append(
            Recommendation(
                category="Produtos",
                title=f"Considere destacar a categoria '{top_cat}'",
                observation=(
                    f"Considere priorizar a exposição da categoria '{top_cat}': "
                    f"lidera em receita observada no recorte com {format_pct_pt(top_share)} "
                    f"do total de produtos entregues."
                ),
                evidence=(
                    f"Categoria '{top_cat}': {format_brl(top_rev)} "
                    f"({format_pct_pt(top_share)} da receita), {format_int_pt(top_items)} item(ns) "
                    f"em {format_int_pt(top_orders)} pedido(s)."
                ),
                period=period_label,
                caveat=_HISTORICAL_CAVEAT_PT,
                strength=round(strength, 4),
            )
        )

    return recs


def generate_recommendations(
    kpis: KPISummary,
    monthly_df: pd.DataFrame,
    categories_df: pd.DataFrame,
    seg_result: SegmentationResult,
    period_label: str,
    rfm_scope_label: str,
) -> list[Recommendation]:
    """Generate deterministic, cautious, evidence-backed recommendations across M2 outputs."""
    if (
        kpis is None
        or kpis.is_empty
        or kpis.delivered_orders <= 0
        or not math.isfinite(float(kpis.product_revenue))
        or kpis.product_revenue <= 0.0
    ):
        return []

    norm_period = (period_label or "").strip() or "Período não especificado"
    norm_rfm_scope = (rfm_scope_label or "").strip() or "Escopo RFM não especificado"

    recs: list[Recommendation] = []
    recs.extend(_evaluate_customer_rules(seg_result, norm_period, norm_rfm_scope))
    recs.extend(_evaluate_seasonality_rules(monthly_df, norm_period))
    recs.extend(_evaluate_product_rules(categories_df, norm_period))

    recs.sort(
        key=lambda rec: (
            -round(float(rec.strength), 6),
            _CATEGORY_PRIORITY.get(rec.category, 99),
            rec.title,
        )
    )
    return recs
