"""Unit and integration tests for unidata.recommendations."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from unidata.analytics import (
    KPISummary,
    compute_category_ranking,
    compute_kpis,
    compute_monthly_series,
    filter_prepared_data,
)
from unidata.config import UNKNOWN_CATEGORY_LABEL
from unidata.formatting import format_brl, format_month_pt, format_pct_pt
from unidata.loader import load_olist_dataset
from unidata.pipeline import prepare_data
from unidata.recommendations import Recommendation, generate_recommendations
from unidata.segmentation import SegmentationResult, compute_rfm_and_clusters

_CAUTIOUS_MARKERS = (
    "avalie",
    "considere",
    "investigue",
    "indica",
    "priorize",
    "observe",
    "monitore",
)

_FORBIDDEN_PATTERNS = (
    re.compile(r"\bprevis[ãa]o\b"),
    re.compile(r"\baumentar[áa]\b"),
    re.compile(r"\bvai aumentar\b"),
    re.compile(r"\bgarantido\b"),
    re.compile(r"\bclientes fi[ée]is\b"),
    re.compile(r"\bmelhor segmento\b"),
)


def test_generate_recommendations_standard_olist_happy_path_and_determinism(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    kpis = compute_kpis(prepared)
    monthly_df = compute_monthly_series(prepared)
    categories_df = compute_category_ranking(prepared)
    seg_result = compute_rfm_and_clusters(prepared.items_df)

    period_label = "Out/2017 a Jan/2018"
    rfm_scope_label = "Base completa (Out/2017–Jan/2018)"

    recs1 = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=categories_df,
        seg_result=seg_result,
        period_label=period_label,
        rfm_scope_label=rfm_scope_label,
    )
    recs2 = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=categories_df,
        seg_result=seg_result,
        period_label=period_label,
        rfm_scope_label=rfm_scope_label,
    )

    assert recs1 == recs2
    assert all(isinstance(r, Recommendation) for r in recs1)
    assert {r.category for r in recs1} == {"Clientes", "Sazonalidade", "Produtos"}

    strengths = [r.strength for r in recs1]
    assert strengths == sorted(strengths, reverse=True)

    for rec in recs1:
        assert rec.title.strip()
        assert rec.observation.strip()
        assert rec.evidence.strip()
        assert rec.period.strip()
        assert rec.caveat.strip()

        # Cautious verbs present and forbidden terms absent
        body = f"{rec.title} {rec.observation} {rec.evidence}".lower()
        assert any(marker in body for marker in _CAUTIOUS_MARKERS)
        for pattern in _FORBIDDEN_PATTERNS:
            assert pattern.search(body) is None

        # Historical Olist non-causal caveat
        caveat_lower = rec.caveat.lower()
        assert "históric" in caveat_lower or "historic" in caveat_lower
        assert "olist" in caveat_lower
        assert "causal" in caveat_lower

        # Percentage points never 100x inflated (e.g. "2500,0%")
        assert not re.search(r"\d{4,},\d%", rec.evidence)

        if rec.category == "Clientes":
            assert rfm_scope_label in rec.period
        else:
            assert period_label in rec.period


def test_recommendations_evidence_traceability_exact_formatted_values(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    kpis = compute_kpis(prepared)
    monthly_df = compute_monthly_series(prepared)
    categories_df = compute_category_ranking(prepared)
    seg_result = compute_rfm_and_clusters(prepared.items_df)

    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=categories_df,
        seg_result=seg_result,
        period_label="Out/2017–Jan/2018",
        rfm_scope_label="Escopo completo",
    )

    by_cat: dict[str, list[Recommendation]] = {}
    for r in recs:
        by_cat.setdefault(r.category, []).append(r)

    # Seasonality cites peak month Jan/2018 and R$ 469,50
    season_rec = by_cat["Sazonalidade"][0]
    assert format_month_pt("2018-01") in f"{season_rec.title} {season_rec.observation}"
    assert format_brl(469.50) in season_rec.evidence

    # Products cites sports_leisure, R$ 420,00, and 46,7%
    prod_rec = by_cat["Produtos"][0]
    assert "sports_leisure" in prod_rec.title
    assert format_brl(420.00) in prod_rec.evidence
    assert format_pct_pt((420.0 / 900.0) * 100.0) in prod_rec.evidence

    # Customer recommendation matches cluster_summary values
    cust_rec = by_cat["Clientes"][0]
    assert seg_result.cluster_summary is not None
    expected_brl_values = {
        format_brl(v) for v in seg_result.cluster_summary["median_monetary"]
    }
    assert any(val in cust_rec.evidence for val in expected_brl_values)
    assert format_pct_pt(25.0) in cust_rec.evidence


def test_recommendations_empty_kpis_and_sliced_empty_dataframes_return_empty(
    empty_delivered_dir: Path,
) -> None:
    empty_prepared = prepare_data(load_olist_dataset(empty_delivered_dir).tables)
    empty_kpis = compute_kpis(empty_prepared)
    failed_seg = compute_rfm_and_clusters(empty_prepared.items_df)

    # Normal empty tables
    assert (
        generate_recommendations(
            kpis=empty_kpis,
            monthly_df=compute_monthly_series(empty_prepared),
            categories_df=compute_category_ranking(empty_prepared),
            seg_result=failed_seg,
            period_label="Sem período",
            rfm_scope_label="Sem dados",
        )
        == []
    )

    # Schema-defensive: sliced raw empty DataFrames with mismatched columns
    assert (
        generate_recommendations(
            kpis=empty_kpis,
            monthly_df=empty_prepared.orders_df.iloc[0:0],
            categories_df=empty_prepared.items_df.iloc[0:0],
            seg_result=failed_seg,
            period_label="Sem período",
            rfm_scope_label="Sem dados",
        )
        == []
    )


def test_recommendations_omits_clientes_when_segmentation_fails(
    edge_cases_olist_dir: Path,
) -> None:
    prepared = prepare_data(load_olist_dataset(edge_cases_olist_dir).tables)
    kpis = compute_kpis(prepared)
    monthly_df = compute_monthly_series(prepared)
    categories_df = compute_category_ranking(prepared)
    seg_result = compute_rfm_and_clusters(prepared.items_df)

    assert seg_result.ok is False
    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=categories_df,
        seg_result=seg_result,
        period_label="Dez/2017",
        rfm_scope_label="Dez/2017",
    )

    cats = {r.category for r in recs}
    assert "Clientes" not in cats
    assert "Sazonalidade" not in cats  # only 1 month in edge_cases_olist
    assert "Produtos" in cats


def test_recommendations_single_active_month_omits_seasonality(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    nov = filter_prepared_data(prepared, start_ym="2017-11", end_ym="2017-11")
    kpis = compute_kpis(nov)
    monthly_df = compute_monthly_series(nov)
    categories_df = compute_category_ranking(nov)
    seg_full = compute_rfm_and_clusters(prepared.items_df)

    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=categories_df,
        seg_result=seg_full,
        period_label="Nov/2017",
        rfm_scope_label="Base completa (Out/2017–Jan/2018)",
    )

    cats = {r.category for r in recs}
    assert "Sazonalidade" not in cats
    assert "Produtos" in cats
    assert "Clientes" in cats

    # Verify Clientes preserves rfm_scope_label while Produtos preserves period_label
    for rec in recs:
        if rec.category == "Clientes":
            assert "Base completa (Out/2017–Jan/2018)" in rec.period
        else:
            assert "Nov/2017" in rec.period


def test_recommendations_equal_revenue_months_and_nan_gaps_handled_honestly() -> None:
    kpis = KPISummary(
        product_revenue=200.0,
        delivered_orders=2,
        unique_customers=2,
        avg_ticket=100.0,
        is_empty=False,
        period_start=pd.Timestamp("2018-01-01"),
        period_end=pd.Timestamp("2018-03-01"),
    )
    equal_monthly = pd.DataFrame(
        {
            "year_month": ["2018-01", "2018-02", "2018-03"],
            "product_revenue": [100.0, float("nan"), 100.0],
            "delivered_orders": [1, 0, 1],
            "avg_ticket": [100.0, 0.0, 100.0],
            "yoy_revenue_pct": [float("nan"), float("nan"), float("nan")],
        }
    )
    cats_df = pd.DataFrame(
        {
            "category": ["beleza_saude"],
            "product_revenue": [200.0],
            "revenue_share_pct": [100.0],
            "items_count": [2],
            "delivered_orders": [2],
        }
    )
    failed_seg = SegmentationResult(
        ok=False,
        error_message="Insuficiente",
        rfm_df=None,
        cluster_summary=None,
        reference_date=None,
        customer_count=2,
        model_info={},
    )

    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=equal_monthly,
        categories_df=cats_df,
        seg_result=failed_seg,
        period_label="Jan/2018–Mar/2018",
        rfm_scope_label="Jan/2018–Mar/2018",
    )
    # Zero spread across valid months -> Sazonalidade omitted cleanly
    assert [r.category for r in recs] == ["Produtos"]


def test_recommendations_leading_unknown_category_handled_honestly() -> None:
    kpis = KPISummary(
        product_revenue=500.0,
        delivered_orders=4,
        unique_customers=4,
        avg_ticket=125.0,
        is_empty=False,
        period_start=pd.Timestamp("2018-01-01"),
        period_end=pd.Timestamp("2018-02-01"),
    )
    monthly_df = pd.DataFrame(
        {
            "year_month": ["2018-01", "2018-02"],
            "product_revenue": [350.0, 150.0],
            "delivered_orders": [3, 1],
            "avg_ticket": [116.67, 150.0],
            "yoy_revenue_pct": [float("nan"), float("nan")],
        }
    )
    cats_df = pd.DataFrame(
        {
            "category": [UNKNOWN_CATEGORY_LABEL, "informatica_acessorios"],
            "product_revenue": [350.0, 150.0],
            "revenue_share_pct": [70.0, 30.0],
            "items_count": [3, 1],
            "delivered_orders": [3, 1],
        }
    )
    failed_seg = SegmentationResult(
        ok=False,
        error_message="Insuficiente",
        rfm_df=None,
        cluster_summary=None,
        reference_date=None,
        customer_count=4,
        model_info={},
    )

    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=cats_df,
        seg_result=failed_seg,
        period_label="Jan/2018–Fev/2018",
        rfm_scope_label="Jan/2018–Fev/2018",
    )

    prod_recs = [r for r in recs if r.category == "Produtos"]
    assert len(prod_recs) == 2
    assert "catálogo" in prod_recs[0].title.lower()
    assert UNKNOWN_CATEGORY_LABEL in prod_recs[0].title
    assert "destacar" not in prod_recs[0].title.lower()
    assert "informatica_acessorios" in prod_recs[1].title
    assert format_brl(150.0) in prod_recs[1].evidence


def test_recommendations_zero_revenue_kpis_returns_empty() -> None:
    zero_kpis = KPISummary(
        product_revenue=0.0,
        delivered_orders=1,
        unique_customers=1,
        avg_ticket=0.0,
        is_empty=False,
        period_start=pd.Timestamp("2018-01-01"),
        period_end=pd.Timestamp("2018-01-01"),
    )
    failed_seg = SegmentationResult(
        ok=False,
        error_message="Insuficiente",
        rfm_df=None,
        cluster_summary=None,
        reference_date=None,
        customer_count=1,
        model_info={},
    )

    assert (
        generate_recommendations(
            kpis=zero_kpis,
            monthly_df=pd.DataFrame(),
            categories_df=pd.DataFrame(),
            seg_result=failed_seg,
            period_label="Jan/2018",
            rfm_scope_label="Jan/2018",
        )
        == []
    )


def test_recommendations_seasonality_filters_invalid_year_month_no_em_dash() -> None:
    kpis = KPISummary(
        product_revenue=600.0,
        delivered_orders=6,
        unique_customers=6,
        avg_ticket=100.0,
        is_empty=False,
        period_start=pd.Timestamp("2018-01-01"),
        period_end=pd.Timestamp("2018-02-28"),
    )
    failed_seg = SegmentationResult(
        ok=False,
        error_message="err",
        rfm_df=None,
        cluster_summary=None,
        reference_date=None,
        customer_count=0,
        model_info={},
    )

    # 1 valid month + 1 invalid year_month -> Sazonalidade omitted cleanly (never emits '—')
    invalid_trough_monthly = pd.DataFrame(
        {
            "year_month": ["2018-01", "INVALID_YM"],
            "product_revenue": [500.0, 100.0],
            "delivered_orders": [5, 1],
        }
    )
    recs_one_valid = generate_recommendations(
        kpis=kpis,
        monthly_df=invalid_trough_monthly,
        categories_df=pd.DataFrame(),
        seg_result=failed_seg,
        period_label="Jan/2018",
        rfm_scope_label="Base",
    )
    assert recs_one_valid == []

    # 2 valid months + 2 invalid year_months -> invalid rows excluded before peak/trough
    mixed_monthly = pd.DataFrame(
        {
            "year_month": ["2018-01", "2018-02", "INVALID_YM", "2018-13"],
            "product_revenue": [400.0, 200.0, 50.0, 999.0],
            "delivered_orders": [4, 2, 1, 9],
        }
    )
    recs_mixed = generate_recommendations(
        kpis=kpis,
        monthly_df=mixed_monthly,
        categories_df=pd.DataFrame(),
        seg_result=failed_seg,
        period_label="Jan/2018–Fev/2018",
        rfm_scope_label="Base",
    )
    assert [r.category for r in recs_mixed] == ["Sazonalidade"]
    rec = recs_mixed[0]
    assert "—" not in rec.title
    assert "—" not in rec.observation
    assert "—" not in rec.evidence
    assert "Jan/2018" in rec.observation
    assert "Fev/2018" in rec.observation


def test_recommendations_customer_rules_nat_reference_date_and_non_finite_summary() -> None:
    kpis = KPISummary(
        product_revenue=600.0,
        delivered_orders=6,
        unique_customers=6,
        avg_ticket=100.0,
        is_empty=False,
        period_start=pd.Timestamp("2018-01-01"),
        period_end=pd.Timestamp("2018-01-31"),
    )
    summary_with_inf = pd.DataFrame(
        {
            "cluster_label": ["Segmento A — Maior gasto", "Segmento B — Inválido"],
            "customer_count": [10, 5],
            "customer_pct": [66.7, np.inf],
            "median_recency": [12.0, 30.0],
            "median_frequency": [2.0, 1.0],
            "median_monetary": [300.0, 500.0],
        }
    )
    seg_nat = SegmentationResult(
        ok=True,
        error_message=None,
        rfm_df=pd.DataFrame(),
        cluster_summary=summary_with_inf,
        reference_date=pd.NaT,  # type: ignore[arg-type]
        customer_count=15,
        model_info={},
    )
    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=pd.DataFrame(),
        categories_df=pd.DataFrame(),
        seg_result=seg_nat,
        period_label="Jan/2018",
        rfm_scope_label="Base completa",
    )
    assert len(recs) == 1
    assert recs[0].category == "Clientes"
    assert "Segmento A" in recs[0].title
    assert "Segmento B" not in recs[0].title
    assert "ref.:" not in recs[0].period
    assert "—" not in recs[0].period
    assert recs[0].period == "Base completa (recorte exibido: Jan/2018)"

    # All non-finite rows -> Clientes omitted cleanly
    all_inf_seg = SegmentationResult(
        ok=True,
        error_message=None,
        rfm_df=pd.DataFrame(),
        cluster_summary=pd.DataFrame(
            {
                "cluster_label": ["Segmento X"],
                "customer_count": [5],
                "customer_pct": [100.0],
                "median_recency": [np.inf],
                "median_frequency": [1.0],
                "median_monetary": [100.0],
            }
        ),
        reference_date=pd.NaT,  # type: ignore[arg-type]
        customer_count=5,
        model_info={},
    )
    assert (
        generate_recommendations(
            kpis=kpis,
            monthly_df=pd.DataFrame(),
            categories_df=pd.DataFrame(),
            seg_result=all_inf_seg,
            period_label="Jan/2018",
            rfm_scope_label="Base completa",
        )
        == []
    )


def test_recommendations_has_zero_streamlit_imports() -> None:
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {src_dir!r}); "
                "import unidata.recommendations; "
                "assert 'streamlit' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
