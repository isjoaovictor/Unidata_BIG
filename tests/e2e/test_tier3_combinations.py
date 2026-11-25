"""Tier 3 E2E Tests: Pairwise & Multi-Feature Combinations (24 cases: T3-01 .. T3-24)."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import zipfile

import pytest

from tests.e2e.conftest import (
    PRIMARY_FIXTURE_DIR,
    REPO_ROOT,
    apply_temporal_filter,
    click_reset_filter,
    expand_methodology_section,
    launch_streamlit_app,
    normalize_brl_spaces,
    open_playwright_page,
    try_select_empty_filter_in_ui,
    wait_for_streamlit_ready,
)
from tests.e2e.fixture_builders import (
    build_fix_bom_long,
    build_fix_multi_pay,
    build_fix_no_deliv,
    build_fix_no_trans,
    build_fix_repeat,
    build_fix_small_rfm,
    copy_primary_fixture,
    validate_readme_content,
    validate_showcase_dir,
    validate_zip_deliverable,
    write_dataset,
)

pytestmark = pytest.mark.e2e


def _load_and_prepare(data_dir: Path):
    from unidata.loader import load_olist_dataset
    from unidata.pipeline import prepare_data

    res = load_olist_dataset(data_dir)
    assert res.ok, f"Load failed for {data_dir}: {res.missing_files} {res.errors}"
    return res, prepare_data(res.tables)


def test_t3_01_f3_f4_f5_bom_leading_zero_ids_through_loader_to_pipeline(tmp_path: Path) -> None:
    d = build_fix_bom_long(tmp_path / "t3_01")
    res, prepared = _load_and_prepare(d)
    assert res.ok is True
    assert "00001" in set(prepared.orders_df["order_id"])
    assert "00091" in set(prepared.orders_df["customer_unique_id"])
    assert prepared.diagnostics.orders_delivered == 5


def test_t3_02_f5_f7_multi_item_multi_payment_canceled_to_kpis(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    d = write_dataset(
        tmp_path / "t3_02",
        orders=[
            ["O1", "C1", "delivered", "2018-05-01 12:00:00"],
            ["O2", "C2", "canceled", "2018-05-02 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "25.00"],
            ["O1", "2", "P2", "50.00", "25.00"],
            ["O2", "1", "P1", "999.00", "25.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"]],
        products=[["P1", "cama_mesa_banho"], ["P2", "beleza_saude"]],
        payments=[
            ["O1", "1", "voucher", "1", "50.00"],
            ["O1", "2", "credit_card", "2", "150.00"],
        ],
    )
    _, prepared = _load_and_prepare(d)
    kpis = compute_kpis(prepared)
    assert kpis.product_revenue == pytest.approx(150.00)
    assert kpis.delivered_orders == 1
    assert kpis.avg_ticket == pytest.approx(150.00)


def test_t3_03_f5_f7_f10_repeat_customers_reconcile_kpis_and_rfm(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(build_fix_repeat(tmp_path / "t3_03"))
    kpis = compute_kpis(prepared)
    rfm, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "frequency", "monetary"}.issubset(set(rfm.columns))
    assert kpis.unique_customers == len(rfm)
    assert int(rfm["frequency"].sum()) == kpis.delivered_orders
    assert float(rfm["monetary"].sum()) == pytest.approx(kpis.product_revenue)


def test_t3_04_f7_f8_filtered_kpis_reconcile_with_monthly_series() -> None:
    from unidata.analytics import compute_kpis, compute_monthly_series, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    for start_ym, end_ym in [(None, None), ("2018-05", "2018-08"), ("2017-01", "2017-12")]:
        sl = filter_prepared_data(prepared, start_ym=start_ym, end_ym=end_ym)
        kpis = compute_kpis(sl)
        monthly = compute_monthly_series(sl)
        assert monthly["product_revenue"].sum() == pytest.approx(kpis.product_revenue)
        assert int(monthly["delivered_orders"].sum()) == kpis.delivered_orders


def test_t3_05_f7_f9_filtered_kpis_reconcile_with_category_ranking() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    for start_ym, end_ym in [(None, None), ("2018-05", "2018-08")]:
        sl = filter_prepared_data(prepared, start_ym=start_ym, end_ym=end_ym)
        kpis = compute_kpis(sl)
        cats = compute_category_ranking(sl)
        assert cats["product_revenue"].sum() == pytest.approx(kpis.product_revenue)
        assert int(cats["items_count"].sum()) == len(sl.items_df)


def test_t3_06_f8_f13_temporal_filter_and_monthly_yoy_handling() -> None:
    import pandas as pd
    from unidata.analytics import compute_monthly_series, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    # Filtered strictly to 2018 -> 2017-05 not in filtered slice, so 2018-05 YoY is NaN without crash
    sliced = filter_prepared_data(prepared, start_ym="2018-01", end_ym="2018-11")
    monthly = compute_monthly_series(sliced).set_index("year_month")
    assert list(monthly.index) == ["2018-05", "2018-08"]
    assert pd.isna(monthly.loc["2018-05", "yoy_revenue_pct"])


def test_t3_07_f9_f13_temporal_filter_switches_leading_category_and_recommendation() -> None:
    from unidata.analytics import (
        compute_category_ranking,
        compute_kpis,
        compute_monthly_series,
        filter_prepared_data,
    )
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    # 2017 leader: bed_bath_table (3740.00)
    s2017 = filter_prepared_data(prepared, start_ym="2017-01", end_ym="2017-12")
    c2017 = compute_category_ranking(s2017)
    assert c2017.iloc[0]["category"] == "bed_bath_table"

    # 2018 leader: computers_accessories (1800.00)
    s2018 = filter_prepared_data(prepared, start_ym="2018-01", end_ym="2018-12")
    c2018 = compute_category_ranking(s2018)
    assert c2018.iloc[0]["category"] == "computers_accessories"
    recs2018 = generate_recommendations(
        compute_kpis(s2018),
        compute_monthly_series(s2018),
        c2018,
        compute_rfm_and_clusters(s2018.items_df),
        "Mai/2018–Ago/2018",
        "Período filtrado",
    )
    prod_recs = [r for r in recs2018 if r.category == "Produtos"]
    assert prod_recs and "computers_accessories" in f"{prod_recs[0].title} {prod_recs[0].observation} {prod_recs[0].evidence}"


@pytest.mark.ui
def test_t3_08_f10_f11_f13_temporal_filter_and_rfm_scope_declaration() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            apply_temporal_filter(page, "2018")
            text = wait_for_streamlit_ready(page).lower()
            assert ("base completa" in text) or ("período filtrado" in text) or ("recorte" in text)


def test_t3_09_f11_f12_cluster_summary_matches_clientes_recommendation() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.formatting import format_brl
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg = compute_rfm_and_clusters(prepared.items_df)
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        seg,
        "Mai/2017–Ago/2018",
        "Base completa",
    )
    cli_recs = [r for r in recs if r.category == "Clientes"]
    assert cli_recs
    ev = normalize_brl_spaces(cli_recs[0].evidence)
    possible_medians = [
        normalize_brl_spaces(format_brl(float(v)))
        for v in seg.cluster_summary["median_monetary"].tolist()
    ]
    assert any(m in ev for m in possible_medians) or "25,0%" in ev


def test_t3_10_f8_f12_monthly_peak_matches_sazonalidade_recommendation() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    monthly = compute_monthly_series(prepared)
    recs = generate_recommendations(
        compute_kpis(prepared),
        monthly,
        compute_category_ranking(prepared),
        compute_rfm_and_clusters(prepared.items_df),
        "Mai/2017–Ago/2018",
        "Base completa",
    )
    saz = [r for r in recs if r.category == "Sazonalidade"]
    assert saz
    combined = normalize_brl_spaces(f"{saz[0].title} {saz[0].observation} {saz[0].evidence}")
    assert "Nov/2017" in combined or "2017-11" in combined
    assert "4.680,00" in combined


def test_t3_11_f9_f12_category_leader_matches_produtos_recommendation() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    cats = compute_category_ranking(prepared)
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        cats,
        compute_rfm_and_clusters(prepared.items_df),
        "Mai/2017–Ago/2018",
        "Base completa",
    )
    prod = [r for r in recs if r.category == "Produtos"]
    assert prod
    combined = normalize_brl_spaces(f"{prod[0].title} {prod[0].observation} {prod[0].evidence}")
    assert "bed_bath_table" in combined
    assert "4.940,00" in combined


@pytest.mark.ui
def test_t3_12_f11_f12_f14_degenerate_rfm_partial_failure_keeps_dashboard_alive(
    tmp_path: Path,
) -> None:
    d = build_fix_small_rfm(tmp_path / "t3_12", variant="A")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "600,00" in text
            assert "Clientes" in text
            assert "Recomendações" in text
            assert "Traceback" not in text
            assert not page_errs


@pytest.mark.ui
def test_t3_13_f4_f9_f16_missing_translation_reflects_in_categories_and_diagnostics(
    tmp_path: Path,
) -> None:
    d = build_fix_no_trans(tmp_path / "t3_13")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "cama_mesa_banho" in text
            assert "Não informado" in text


@pytest.mark.ui
def test_t3_14_f13_f14_f15_empty_filter_state_and_reset_in_ui(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis, filter_prepared_data
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    empty = filter_prepared_data(prepared, start_ym="2017-02", end_ym="2017-02")
    kpis = compute_kpis(empty)
    assert kpis.is_empty is True
    assert generate_recommendations(
        kpis,
        empty.orders_df.iloc[0:0],
        empty.items_df.iloc[0:0],
        compute_rfm_and_clusters(empty.items_df),
        "Fev/2017",
        "Vazio",
    ) == []

    triggered_empty_in_ui = False
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "E-commerce Insights" in text
            if try_select_empty_filter_in_ui(page):
                triggered_empty_in_ui = True
                empty_txt = wait_for_streamlit_ready(page).lower()
                assert any(
                    k in empty_txt for k in ("sem dados", "nenhum", "vazio", "sem cobertura", "0 pedido", "limpar", "voltar")
                )
                assert page.evaluate("() => document.querySelectorAll('.js-plotly-plot').length") == 0
                restored = click_reset_filter(page)
                assert "10.920,00" in restored
            assert not page_errs

    if not triggered_empty_in_ui:
        nd_dir = build_fix_no_deliv(tmp_path / "t3_14_empty_ui")
        with launch_streamlit_app(nd_dir) as (url, _):
            with open_playwright_page() as (page, _, page_errs):
                page.goto(url, wait_until="domcontentloaded")
                empty_txt = wait_for_streamlit_ready(page).lower()
                assert any(
                    k in empty_txt for k in ("sem dados", "nenhum", "vazio", "sem cobertura", "entreg", "0 pedido")
                )
                assert page.evaluate("() => document.querySelectorAll('.js-plotly-plot').length") == 0
                assert "traceback" not in empty_txt
                assert not page_errs


@pytest.mark.ui
def test_t3_15_f6_f13_f14_caching_filter_round_trip_equality() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            initial = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in initial

            apply_temporal_filter(page, "2017")
            filtered = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" not in filtered

            after_reset = click_reset_filter(page)
            assert "10.920,00" in after_reset


@pytest.mark.ui
def test_t3_16_f14_f15_f16_dark_theme_accessibility_and_methodology() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "CC BY-NC-SA 4.0" in text
            colors = page.evaluate(
                """() => {
                    const app = document.querySelector('.stApp') || document.body;
                    return {
                        bodyBg: window.getComputedStyle(document.body).backgroundColor,
                        appBg: window.getComputedStyle(app).backgroundColor,
                    };
                }"""
            )
            assert colors["appBg"] == "rgb(0, 0, 0)" or colors["bodyBg"] == "rgb(0, 0, 0)"


@pytest.mark.ui
def test_t3_17_f5_f16_diagnostics_counts_reconcile_with_kpis_in_ui() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = normalize_brl_spaces(expand_methodology_section(page))
            lower = text.lower()
            assert any(k in lower for k in ("lido", "entreg", "exclu", "diagnóstic", "qualidade"))
            assert re.search(r"(?<![\d.,])\b42\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b24\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b46\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b4\b(?![\d.,%])", text)


@pytest.mark.ui
def test_t3_18_f7_f14_nominal_brl_formatting_and_tabular_nums_across_ui() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert re.search(r"R\$\s\d{1,3}(\.\d{3})*,\d{2}", text)
            has_tabular = page.evaluate(
                "() => document.documentElement.outerHTML.toLowerCase().includes('tabular-nums')"
            )
            assert has_tabular is True


@pytest.mark.ui
def test_t3_19_f11_f15_kmeans_segment_distribution_matches_rfm_table() -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is True
    assert {"customer_unique_id", "recency", "frequency", "monetary", "cluster_id", "cluster_label"}.issubset(
        set(seg.rfm_df.columns)
    )
    assert int(seg.cluster_summary["customer_count"].sum()) == 24
    assert (seg.cluster_summary["customer_pct"] >= 0.0).all()
    assert (seg.cluster_summary["customer_pct"] <= 100.0).all()
    assert seg.cluster_summary["customer_pct"].sum() == pytest.approx(100.0, abs=0.1)

    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            for lbl in seg.cluster_summary["cluster_label"].tolist():
                assert str(lbl) in text


@pytest.mark.ui
def test_t3_20_f3_f6_f14_missing_onboarding_hot_drop_recovery_in_ui(tmp_path: Path) -> None:
    hot = tmp_path / "hot_t3_20"
    hot.mkdir()
    with launch_streamlit_app(hot) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            txt1 = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in txt1

            copy_primary_fixture(hot)
            page.reload(wait_until="domcontentloaded")
            txt2 = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in txt2


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t3_21_f1_f18_gitignore_and_readme_olist_instructions_parity(repo_root: Path) -> None:
    from unidata import config

    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "data/*" in gitignore
    for val in list(config.REQUIRED_FILES.values()) + list(config.OPTIONAL_FILES.values()):
        fn = val[0] if isinstance(val, tuple) else val
        assert fn in readme


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
@pytest.mark.ui
def test_t3_22_f14_f16_f19_dashboard_and_showcase_provenance_consistency(repo_root: Path) -> None:
    errs = validate_showcase_dir(repo_root / "presentation")
    assert not errs, f"Showcase validation failed: {errs}"
    html = (repo_root / "presentation" / "showcase.html").read_text(encoding="utf-8").lower()
    assert "cc by-nc-sa 4.0" in html and "olist" in html


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t3_23_f1_f17_f20_clean_room_zip_extraction_passes_tests(
    repo_root: Path, tmp_path: Path
) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    errs = validate_zip_deliverable(zip_path)
    assert not errs, f"Zip validation errors: {errs}"

    ext = tmp_path / "clean_room"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(ext)
    candidates = [ext, *[p for p in ext.iterdir() if p.is_dir()]]
    root_in_zip = next((c for c in candidates if (c / "app.py").is_file()), None)
    assert root_in_zip is not None
    unit_files = sorted(p for p in (root_in_zip / "tests").glob("test_*.py"))
    assert unit_files
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *[str(p) for p in unit_files], "-q"],
        cwd=str(root_in_zip),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t3_24_f18_f19_f20_zip_matches_workspace_readme_and_presentation_byte_for_byte(
    repo_root: Path,
) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    errs = validate_zip_deliverable(zip_path, expected_repo_root=repo_root)
    assert not errs, f"Release parity errors: {errs}"
