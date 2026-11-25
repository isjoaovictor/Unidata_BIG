"""Tier 4 E2E Tests: Real-World Application & Release Journeys (12 cases: T4-01 .. T4-12)."""

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
    expand_methodology_section,
    launch_streamlit_app,
    normalize_brl_spaces,
    open_playwright_page,
    wait_for_streamlit_ready,
)
from tests.e2e.fixture_builders import (
    build_fix_multi_pay,
    build_fix_no_deliv,
    build_fix_no_trans,
    build_fix_repeat,
    build_fix_seasonal,
    build_fix_small_rfm,
    build_synthetic_readme,
    build_synthetic_showcase,
    build_synthetic_zip,
    copy_primary_fixture,
    validate_readme_content,
    validate_showcase_dir,
    validate_zip_deliverable,
    write_dataset,
)

pytestmark = pytest.mark.e2e


@pytest.mark.ui
def test_t4_01_analyst_desktop_journey_1440x900() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(1440, 900)) as (page, console_errs, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            text_lower = text.lower()
            assert "E-commerce Insights" in text
            assert "Análise histórica da base Olist" in text
            for section in ("visão geral", "sazonalidade", "clientes", "categorias", "recomendações"):
                assert section in text_lower
            assert "R$ 10.920,00" in text
            assert "R$ 260,00" in text
            assert "42" in text and "24" in text
            assert "Não informado" in text

            full_text = expand_methodology_section(page)
            assert "CC BY-NC-SA 4.0" in full_text
            assert "Traceback" not in full_text
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 1442
            assert not page_errs and not console_errs


@pytest.mark.ui
def test_t4_02_mobile_analyst_narrow_viewport_journey_390x844() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(390, 844)) as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "R$ 10.920,00" in text
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= 392, f"Mobile overflow: {scroll_w}"

            apply_temporal_filter(page, "2018")
            filtered_text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" not in filtered_text
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 392
            assert not page_errs


@pytest.mark.ui
def test_t4_03_tablet_responsive_and_keyboard_accessibility_journey_768x1024() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(768, 1024), reduced_motion="reduce") as (
            page,
            _,
            page_errs,
        ):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= 770
            tables = page.locator("table, [data-testid='stDataFrame'], [data-testid='stTable']")
            assert tables.count() >= 2
            page.keyboard.press("Tab")
            assert not page_errs


@pytest.mark.ui
def test_t4_04_seasonal_spike_and_yoy_exploration_journey(tmp_path: Path) -> None:
    d = build_fix_seasonal(tmp_path / "t4_04_seasonal")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "Nov/2017" in text or "nov/2017" in text.lower()
            assert "3.000,00" in text
            assert "padrão histórico observado" in text.lower()
            assert "Traceback" not in text
            assert not page_errs


@pytest.mark.ui
def test_t4_05_repeat_buyer_retention_and_multi_payment_integrity_journey(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis
    from unidata.loader import load_olist_dataset
    from unidata.pipeline import prepare_data
    from unidata.segmentation import compute_rfm_table

    # Combined 4 customers (2 repeat with 2 customer_ids, 2 single) + multi-row payments + freight
    d = write_dataset(
        tmp_path / "t4_05_combo",
        orders=[
            ["O1", "C1A", "delivered", "2018-05-01 12:00:00"],
            ["O2", "C1B", "delivered", "2018-06-01 12:00:00"],
            ["O3", "C2A", "delivered", "2018-05-05 12:00:00"],
            ["O4", "C2B", "delivered", "2018-06-10 12:00:00"],
            ["O5", "C3", "delivered", "2018-07-01 12:00:00"],
            ["O6", "C4", "delivered", "2018-08-01 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "20.00"],
            ["O1", "2", "P2", "50.00", "20.00"],
            ["O2", "1", "P1", "150.00", "20.00"],
            ["O3", "1", "P2", "200.00", "20.00"],
            ["O4", "1", "P1", "100.00", "20.00"],
            ["O5", "1", "P1", "80.00", "20.00"],
            ["O6", "1", "P2", "120.00", "20.00"],
        ],
        customers=[
            ["C1A", "U_R1"],
            ["C1B", "U_R1"],
            ["C2A", "U_R2"],
            ["C2B", "U_R2"],
            ["C3", "U_S3"],
            ["C4", "U_S4"],
        ],
        products=[["P1", "cama_mesa_banho"], ["P2", "beleza_saude"]],
        payments=[
            ["O1", "1", "voucher", "1", "90.00"],
            ["O1", "2", "credit_card", "2", "190.00"],
            ["O2", "1", "credit_card", "1", "250.00"],
        ],
    )
    prepared = prepare_data(load_olist_dataset(d).tables)
    kpis = compute_kpis(prepared)
    assert kpis.product_revenue == pytest.approx(800.00)
    assert kpis.unique_customers == 4
    rfm, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "frequency"}.issubset(set(rfm.columns))
    assert int(rfm.set_index("customer_unique_id").loc["U_R1", "frequency"]) == 2

    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "R$ 800,00" in text
            assert not page_errs


@pytest.mark.ui
def test_t4_06_missing_data_onboarding_to_recovery_journey(tmp_path: Path) -> None:
    hot = tmp_path / "t4_06_recovery"
    hot.mkdir()
    with launch_streamlit_app(hot) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            txt1 = wait_for_streamlit_ready(page)
            for fn in (
                "olist_orders_dataset.csv",
                "olist_order_items_dataset.csv",
                "olist_customers_dataset.csv",
                "olist_products_dataset.csv",
            ):
                assert fn in txt1
            assert "Traceback" not in txt1

            copy_primary_fixture(hot)
            page.reload(wait_until="domcontentloaded")
            txt2 = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "R$ 10.920,00" in txt2
            assert not page_errs


@pytest.mark.ui
def test_t4_07_degraded_resilience_partial_kmeans_failure_journey(tmp_path: Path) -> None:
    d = build_fix_small_rfm(tmp_path / "t4_07_degraded", variant="A")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "R$ 600,00" in text
            assert "Clientes" in text
            assert "Sazonalidade" in text
            assert "Categorias" in text
            assert "Traceback" not in text
            assert not page_errs


@pytest.mark.ui
def test_t4_08_zero_delivered_and_translation_absent_boundary_journeys(tmp_path: Path) -> None:
    nd_dir = build_fix_no_deliv(tmp_path / "t4_08_nd")
    with launch_streamlit_app(nd_dir) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            txt = wait_for_streamlit_ready(page)
            assert "Traceback" not in txt
            assert not page_errs

    nt_dir = build_fix_no_trans(tmp_path / "t4_08_nt")
    with launch_streamlit_app(nt_dir) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            txt = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "cama_mesa_banho" in txt
            assert "Não informado" in txt
            assert "R$ 10.920,00" in txt
            assert not page_errs


def test_t4_09_synthetic_deliverable_validators_always_on_gate(tmp_path: Path) -> None:
    # README synthetic pass + fail
    good_readme = build_synthetic_readme(tmp_path / "README_ok.md")
    assert validate_readme_content(good_readme, check_links=False) == []
    bad_readme = build_synthetic_readme(tmp_path / "README_bad.md", include_title=False)
    assert validate_readme_content(bad_readme, check_links=False)

    # Showcase synthetic pass + fail
    good_pres = build_synthetic_showcase(tmp_path / "pres_ok")
    assert validate_showcase_dir(good_pres) == []
    bad_pres = build_synthetic_showcase(tmp_path / "pres_bad", include_section_8=False, leak_coxinha=True)
    pres_errs = validate_showcase_dir(bad_pres)
    assert len(pres_errs) >= 2

    # Zip synthetic pass + fail + full-tree parity check
    good_zip = build_synthetic_zip(tmp_path / "ok.zip")
    assert validate_zip_deliverable(good_zip) == []
    bad_zip = build_synthetic_zip(tmp_path / "bad.zip", include_olist_csv=True, include_venv=True)
    zip_errs = validate_zip_deliverable(bad_zip)
    assert len(zip_errs) >= 2

    # Stale src/ and requirements.txt vs expected_repo_root must be flagged
    fake_repo = tmp_path / "fake_repo"
    with zipfile.ZipFile(good_zip, "r") as zf:
        zf.extractall(fake_repo)
    assert validate_zip_deliverable(good_zip, expected_repo_root=fake_repo) == []
    (fake_repo / "src" / "unidata" / "pipeline.py").write_text("# modified in workspace\n", encoding="utf-8")
    (fake_repo / "requirements.txt").write_text("pandas==9.9.9\n", encoding="utf-8")
    parity_errs = validate_zip_deliverable(good_zip, expected_repo_root=fake_repo)
    assert any("src/unidata/pipeline.py" in e for e in parity_errs)
    assert any("requirements.txt" in e for e in parity_errs)


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t4_10_github_readiness_and_live_readme_acceptance(repo_root: Path) -> None:
    assert (repo_root / ".gitignore").is_file()
    assert (repo_root / "requirements.txt").is_file()
    assert list((repo_root / "data").glob("*.csv")) == []
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=True)
    assert not errs, f"Live README validation failed: {errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
@pytest.mark.ui
def test_t4_11_project_showcase_8_section_interactive_and_viewport_acceptance(
    repo_root: Path,
) -> None:
    pres_dir = repo_root / "presentation"
    errs = validate_showcase_dir(pres_dir)
    assert not errs, f"Live presentation validation failed: {errs}"

    url = (pres_dir / "showcase.html").resolve().as_uri()
    for vp in ((1440, 900), (768, 1024), (390, 844)):
        with open_playwright_page(viewport=vp, offline=True) as (page, console_errs, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= vp[0] + 2, f"Showcase overflow at {vp}: {scroll_w}"
            assert not page_errs and not console_errs


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
@pytest.mark.ui
def test_t4_12_final_zip_clean_room_extraction_and_full_verification(
    repo_root: Path, tmp_path: Path
) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    errs = validate_zip_deliverable(zip_path, expected_repo_root=repo_root)
    assert not errs, f"Live zip audit failed: {errs}"

    ext = tmp_path / "release_clean_room"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(ext)
    candidates = [ext, *[p for p in ext.iterdir() if p.is_dir()]]
    root_in_zip = next((c for c in candidates if (c / "app.py").is_file()), None)
    assert root_in_zip is not None

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-m", "not m6_release_gate and not ui", "-q"],
        cwd=str(root_in_zip),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"Extracted suite failed:\n{proc.stdout}\n{proc.stderr}"

    with launch_streamlit_app(root_in_zip / "data", app_root=root_in_zip) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            txt = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in txt
            assert "Traceback" not in txt
            assert not page_errs
