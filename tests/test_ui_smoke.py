"""Headless UI smoke tests for Unidata theme, charts, and Streamlit operational states."""

from __future__ import annotations

from pathlib import Path
import re

from streamlit.testing.v1 import AppTest

from unidata.analytics import compute_category_ranking, compute_monthly_series
from unidata.config import KAGGLE_DATASET_URL, REQUIRED_FILES
from unidata.pipeline import prepare_data
from unidata.segmentation import compute_rfm_and_clusters
from unidata.ui.charts import (
    build_category_ranking_chart,
    build_monthly_trend_chart,
    build_segment_distribution_chart,
)
from unidata.ui.theme import PALETTE, THEME_CSS

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "app.py"


def _all_rendered_text(at: AppTest) -> str:
    """Collect visible text from AppTest markdown, tables, captions, and buttons."""
    parts: list[str] = []
    for block in at.markdown:
        parts.append(str(block.value))
    for tbl in at.table:
        parts.append(tbl.value.to_string())
    for btn in at.button:
        parts.append(str(btn.label))
    for sel in at.selectbox:
        parts.append(str(sel.label))
        parts.append(str(sel.value))
    for rad in at.radio:
        parts.append(str(rad.label))
        parts.append(str(rad.value))
    return "\n".join(parts)


def test_theme_contains_all_design_tokens_and_accessibility_rules() -> None:
    """Ensure REKKI Operate CSS tokens, tabular-nums, focus rings, and offline safety exist."""
    css_lower = THEME_CSS.lower()
    expected_tokens = (
        "#000000",
        "#040910",
        "#0d0d0d",
        "#1f1f1f",
        "#2b2c2e",
        "#0063e1",
        "#ffffff",
        "#858585",
        "#979797",
        "rgba(255,255,255,0.12)",
        "#69a7ff",
    )
    for token in expected_tokens:
        assert token in css_lower, f"Missing CSS token: {token}"
    assert PALETTE["canvas"] == "#000000"
    assert "tabular-nums" in css_lower
    assert ":focus-visible" in css_lower
    assert "prefers-reduced-motion" in css_lower
    assert "@import" not in css_lower
    assert "http://" not in css_lower
    assert "https://" not in css_lower


def test_charts_are_2d_with_metric_unit_titles_and_pt_br_tooltips(standard_tables) -> None:
    """Verify Plotly charts are strictly 2D with descriptive titles and untruncated tooltips."""
    prepared = prepare_data(standard_tables)
    monthly_df = compute_monthly_series(prepared)
    categories_df = compute_category_ranking(prepared)
    seg_result = compute_rfm_and_clusters(prepared.items_df)
    assert seg_result.ok and seg_result.cluster_summary is not None

    monthly_fig = build_monthly_trend_chart(monthly_df, "Receita de produtos (R$)")
    seg_fig = build_segment_distribution_chart(seg_result.cluster_summary)
    cat_fig = build_category_ranking_chart(categories_df, top_n=10)

    for fig in (monthly_fig, seg_fig, cat_fig):
        assert len(fig.data) >= 1
        title_text = str(fig.layout.title.text or "")
        assert title_text.strip() != ""
        assert title_text.strip().lower() != "performance"
        for trace in fig.data:
            assert "3d" not in str(trace.type).lower()

    assert monthly_fig.data[0].type == "scatter"
    assert seg_fig.data[0].type == "bar"
    assert cat_fig.data[0].type == "bar"
    assert any("R$" in str(item) for item in cat_fig.data[0].customdata)


def test_app_ready_state_and_filter_reset_roundtrip(
    monkeypatch,
    standard_olist_dir: Path,
) -> None:
    """Verify Pronto state, year filtering, and one-click Limpar filtro reset."""
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(standard_olist_dir))
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.run()

    assert len(at.exception) == 0
    full_text = _all_rendered_text(at)
    assert "R$ 900,00" in full_text
    for term in (
        "Visão geral",
        "Sazonalidade mensal",
        "Clientes e segmentação RFM",
        "Categorias de produtos",
        "Recomendações explicáveis",
        "Receita de produtos",
        "Ticket médio por pedido",
        "Clientes únicos",
        "Período analisado",
        "Padrão histórico observado",
    ):
        assert term.lower() in full_text.lower()
    assert "100.000 pedidos" not in full_text

    # First selectbox is Ano analisado; selecting 2018 must update KPIs
    assert at.selectbox[0].label == "Ano analisado"
    at.selectbox[0].select("2018").run()
    assert len(at.exception) == 0
    filtered_text = _all_rendered_text(at)
    assert "R$ 469,50" in filtered_text
    assert "R$ 900,00" not in filtered_text
    assert "Período filtrado" in filtered_text

    # Reset button restores R$ 900,00
    reset_btn = next(b for b in at.button if "Limpar filtro" in b.label)
    reset_btn.click().run()
    assert len(at.exception) == 0
    restored_text = _all_rendered_text(at)
    assert "R$ 900,00" in restored_text


def test_app_inverted_filter_triggers_empty_filter_state_and_recovers(
    monkeypatch,
    standard_olist_dir: Path,
) -> None:
    """Verify inverted month range renders Filtro sem dados and reset button recovers."""
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(standard_olist_dir))
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.run()
    assert len(at.exception) == 0

    at.selectbox[1].select("2018-01").run()
    at.selectbox[2].select("2017-10").run()
    assert len(at.exception) == 0
    empty_text = _all_rendered_text(at)
    assert "Filtro sem dados" in empty_text
    assert "Limpar filtro" in empty_text

    reset_btn = next(b for b in at.button if "Limpar filtro" in b.label)
    reset_btn.click().run()
    assert len(at.exception) == 0
    assert "R$ 900,00" in _all_rendered_text(at)


def test_app_missing_files_onboarding_state(
    monkeypatch,
    missing_all_files_dir: Path,
) -> None:
    """Verify missing CSVs render actionable onboarding without tracebacks."""
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(missing_all_files_dir))
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.run()

    assert len(at.exception) == 0
    text = _all_rendered_text(at)
    for filename in REQUIRED_FILES.values():
        assert filename in text
    assert KAGGLE_DATASET_URL in text
    assert "CC BY-NC-SA 4.0" in text
    assert "Traceback" not in text


def test_app_schema_error_state(
    monkeypatch,
    make_missing_column_dir,
) -> None:
    """Verify missing required column renders structured SchemaError without tracebacks."""
    bad_dir = make_missing_column_dir("orders", "order_status")
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(bad_dir))
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.run()

    assert len(at.exception) == 0
    text = _all_rendered_text(at)
    assert "olist_orders_dataset.csv" in text
    assert "order_status" in text
    assert "Traceback" not in text


def test_app_empty_delivered_coverage_state(
    monkeypatch,
    empty_delivered_dir: Path,
) -> None:
    """Verify 0 delivered orders renders Dados sem cobertura cleanly."""
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(empty_delivered_dir))
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.run()

    assert len(at.exception) == 0
    text = _all_rendered_text(at)
    assert "Dados sem cobertura" in text
    assert "Traceback" not in text


def test_app_no_translation_and_partial_kmeans_states(
    monkeypatch,
    no_translation_dir: Path,
    edge_cases_olist_dir: Path,
) -> None:
    """Verify missing translation fallback and partial K-means isolation."""
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(no_translation_dir))
    at_no_trans = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at_no_trans.run()
    assert len(at_no_trans.exception) == 0
    no_trans_text = _all_rendered_text(at_no_trans)
    assert "ausente" in no_trans_text.lower()
    assert "CC BY-NC-SA 4.0" in no_trans_text

    # edge_cases_olist_dir has < 4 distinct RFM customer profiles -> K-means partial failure
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(edge_cases_olist_dir))
    at_edge = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at_edge.run()
    assert len(at_edge.exception) == 0
    edge_text = _all_rendered_text(at_edge)
    assert "Segmentação RFM indisponível" in edge_text
    assert "Visão geral" in edge_text
    assert "Categorias de produtos" in edge_text
    assert not re.search(r"100\.000 pedidos", edge_text)
