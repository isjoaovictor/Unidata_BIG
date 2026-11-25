"""Tier 1 E2E Tests: Happy-Path Feature Coverage (100 cases: T1-F01-01 .. T1-F20-05)."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
import warnings
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
    wait_for_streamlit_ready,
)
from tests.e2e.fixture_builders import (
    build_fix_bom_long,
    build_fix_multi_pay,
    build_fix_no_trans,
    build_fix_repeat,
    build_fix_seasonal,
    copy_primary_fixture,
    validate_readme_content,
    validate_showcase_dir,
    validate_zip_deliverable,
)

pytestmark = pytest.mark.e2e


def _load_and_prepare(data_dir: Path):
    from unidata.loader import load_olist_dataset
    from unidata.pipeline import prepare_data

    res = load_olist_dataset(data_dir)
    assert res.ok, f"Load failed for {data_dir}: {res.missing_files} {res.errors}"
    return res, prepare_data(res.tables)


def _capture_unfocused_styles(page) -> None:
    """Snapshot unfocused border/outline/shadow styles of interactive elements before Tab navigation."""
    page.evaluate(
        """() => {
            if (document.activeElement && document.activeElement !== document.body) {
                document.activeElement.blur();
            }
            const map = new WeakMap();
            const selector = 'button, a, input, select, textarea, summary, [tabindex], [role="button"], [role="combobox"], [role="slider"], [role="tab"]';
            for (const el of document.querySelectorAll(selector)) {
                const st = window.getComputedStyle(el);
                map.set(el, {
                    outlineStyle: st.outlineStyle,
                    outlineWidth: st.outlineWidth,
                    outlineColor: st.outlineColor,
                    boxShadow: st.boxShadow,
                    borderColor: st.borderColor,
                });
            }
            window.__unidataUnfocusedStyles = map;
        }"""
    )


def _find_visible_focus_indicator(page) -> bool:
    """Return True ONLY if focus actually produced a visible outline, boxShadow, or borderColor change."""
    return bool(
        page.evaluate(
            """() => {
                const el = document.activeElement;
                if (!el || el === document.body) return false;

                const readStyle = (target) => {
                    const st = window.getComputedStyle(target);
                    return {
                        outlineStyle: st.outlineStyle,
                        outlineWidth: st.outlineWidth,
                        outlineColor: st.outlineColor,
                        boxShadow: st.boxShadow,
                        borderColor: st.borderColor,
                    };
                };

                const focused = readStyle(el);
                let unfocused = window.__unidataUnfocusedStyles && window.__unidataUnfocusedStyles.get(el);
                if (!unfocused) {
                    el.blur();
                    unfocused = readStyle(el);
                    el.focus({ preventScroll: true });
                }

                const outlineWidthPx = parseFloat(focused.outlineWidth || '0');
                const outlineVisible = (
                    focused.outlineStyle !== 'none'
                    && outlineWidthPx > 0
                    && (
                        focused.outlineStyle !== unfocused.outlineStyle
                        || focused.outlineWidth !== unfocused.outlineWidth
                        || focused.outlineColor !== unfocused.outlineColor
                    )
                );
                const shadowChanged = (
                    Boolean(focused.boxShadow && focused.boxShadow !== 'none')
                    && focused.boxShadow !== unfocused.boxShadow
                );
                const borderChanged = (
                    Boolean(focused.borderColor && focused.borderColor !== 'rgba(0, 0, 0, 0)')
                    && focused.borderColor !== unfocused.borderColor
                );
                return outlineVisible || shadowChanged || borderChanged;
            }"""
        )
    )


# ===========================================================================
# F1 — GitHub-Ready Project Structure & .gitignore (5 cases)
# ===========================================================================


def test_t1_f01_01_required_repository_layout_exists(repo_root: Path) -> None:
    expected = [
        repo_root / "app.py",
        repo_root / "requirements.txt",
        repo_root / ".gitignore",
        repo_root / "data" / ".gitkeep",
        repo_root / "src" / "unidata" / "__init__.py",
        repo_root / "src" / "unidata" / "ui" / "__init__.py",
        repo_root / "tests",
    ]
    missing = [str(p.relative_to(repo_root)) for p in expected if not p.exists()]
    assert not missing, f"Missing required repository entries: {missing}"

    agents_dir = repo_root / ".agents"
    if agents_dir.exists():
        bad = [
            str(p)
            for p in agents_dir.rglob("*")
            if p.name in {"AGENTS.md", "GEMINI.md"} or p.suffix in {".py", ".csv"}
        ]
        assert not bad, f"Disallowed files inside .agents/: {bad}"


def test_t1_f01_02_gitignore_excludes_olist_csvs_and_local_artifacts(repo_root: Path) -> None:
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "data/*" in gitignore or "data/*.csv" in gitignore
    assert "!data/.gitkeep" in gitignore
    assert ".venv/" in gitignore or ".venv" in gitignore
    assert "__pycache__/" in gitignore
    assert ".pytest_cache/" in gitignore
    assert "*.zip" in gitignore


def test_t1_f01_03_requirements_pins_core_runtime_and_test_stack(repo_root: Path) -> None:
    req_text = (repo_root / "requirements.txt").read_text(encoding="utf-8")
    lines = [
        ln.strip().lower()
        for ln in req_text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    joined = "\n".join(lines)
    for pkg in ("pandas", "numpy", "scikit-learn", "streamlit", "pytest"):
        assert pkg in joined, f"Missing required package '{pkg}' in requirements.txt"
    assert "plotly" in joined or "altair" in joined
    for ln in lines:
        assert any(op in ln for op in ("==", ">=", "~=")), f"Unpinned requirement: {ln}"


def test_t1_f01_04_core_unidata_modules_are_streamlit_free(repo_root: Path) -> None:
    core_modules = [
        "config.py",
        "formatting.py",
        "loader.py",
        "pipeline.py",
        "analytics.py",
        "segmentation.py",
        "recommendations.py",
    ]
    core_dir = repo_root / "src" / "unidata"
    for mod in core_modules:
        mod_path = core_dir / mod
        assert mod_path.is_file(), f"Core module missing: {mod_path}"
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("streamlit"), f"{mod} imports streamlit"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("streamlit"), f"{mod} imports from streamlit"


def test_t1_f01_05_no_real_olist_csvs_stored_in_repo_data(repo_root: Path) -> None:
    data_dir = repo_root / "data"
    assert data_dir.is_dir()
    csvs = list(data_dir.rglob("*.csv"))
    assert csvs == [], f"Licensed Olist CSVs must not be present in repo data/: {csvs}"
    assert (data_dir / ".gitkeep").is_file()


# ===========================================================================
# F2 — Central Configuration (5 cases)
# ===========================================================================


def test_t1_f02_01_default_data_dir_and_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from unidata import config

    assert config.DEFAULT_DATA_DIR.name == "data"
    assert config.DEFAULT_DATA_DIR.parent == REPO_ROOT

    monkeypatch.delenv("UNIDATA_DATA_DIR", raising=False)
    assert config.get_data_dir() == config.DEFAULT_DATA_DIR

    monkeypatch.setenv("UNIDATA_DATA_DIR", str(tmp_path))
    assert config.get_data_dir() == tmp_path


def test_t1_f02_02_required_and_optional_file_schemas_match_olist_spec() -> None:
    from unidata import config

    req_files = config.REQUIRED_FILES
    assert set(req_files.keys()) == {"orders", "order_items", "customers", "products"}
    expected_names = {
        "orders": "olist_orders_dataset.csv",
        "order_items": "olist_order_items_dataset.csv",
        "customers": "olist_customers_dataset.csv",
        "products": "olist_products_dataset.csv",
    }
    for k, expected_fn in expected_names.items():
        val = req_files[k]
        actual_fn = val[0] if isinstance(val, tuple) else val
        assert actual_fn == expected_fn

    assert "category_translation" in config.OPTIONAL_FILES
    opt_val = config.OPTIONAL_FILES["category_translation"]
    assert (opt_val[0] if isinstance(opt_val, tuple) else opt_val) == "product_category_name_translation.csv"

    req_cols = getattr(config, "REQUIRED_COLUMNS", {})
    assert set(("order_id", "customer_id", "order_status", "order_purchase_timestamp")).issubset(req_cols["orders"])
    assert set(("order_id", "order_item_id", "product_id", "price")).issubset(req_cols["order_items"])
    assert set(("customer_id", "customer_unique_id")).issubset(req_cols["customers"])
    assert set(("product_id", "product_category_name")).issubset(req_cols["products"])


def test_t1_f02_03_id_columns_tuple_includes_all_key_identifiers() -> None:
    from unidata import config

    for col in ("order_id", "customer_id", "customer_unique_id", "product_id", "order_item_id"):
        assert col in config.ID_COLUMNS


def test_t1_f02_04_rfm_config_defaults_enforce_reproducible_kmeans() -> None:
    from unidata.config import RFMConfig

    cfg = RFMConfig()
    assert cfg.n_clusters == 4
    assert cfg.random_state == 42
    assert cfg.n_init == 10
    assert cfg.log_transform_frequency is True
    assert cfg.log_transform_monetary is True
    assert cfg.min_customers >= 4


def test_t1_f02_05_domain_string_constants_match_pt_br_spec() -> None:
    from unidata import config

    assert config.DELIVERED_STATUS == "delivered"
    assert config.UNKNOWN_CATEGORY_LABEL == "Não informado"


# ===========================================================================
# F3 — Fixed Olist CSV Loader & Missing-File Onboarding (5 cases)
# ===========================================================================


def test_t1_f03_01_loads_all_5_csvs_from_valid_local_directory() -> None:
    from unidata.loader import load_olist_dataset

    res = load_olist_dataset(PRIMARY_FIXTURE_DIR)
    assert res.ok is True
    assert res.has_translation is True
    assert res.missing_files == []
    assert res.errors == []
    for key in ("orders", "order_items", "customers", "products", "category_translation"):
        assert key in res.tables
        assert not res.tables[key].empty


def test_t1_f03_02_loads_successfully_when_optional_translation_csv_absent(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    data_dir = build_fix_no_trans(tmp_path / "no_trans")
    res = load_olist_dataset(data_dir)
    assert res.ok is True
    assert res.has_translation is False
    assert res.missing_files == []
    assert res.errors == []


def test_t1_f03_03_missing_directory_returns_structured_pt_br_onboarding(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    missing_dir = tmp_path / "does_not_exist"
    res = load_olist_dataset(missing_dir)
    assert res.ok is False
    assert len(res.missing_files) == 4
    for fn in (
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_customers_dataset.csv",
        "olist_products_dataset.csv",
    ):
        assert fn in res.missing_files
        assert fn in res.onboarding_message_pt
    assert str(missing_dir) in res.onboarding_message_pt
    assert "kaggle" in res.onboarding_message_pt.lower()


def test_t1_f03_04_partial_missing_files_lists_only_missing_required_files(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    partial_dir = copy_primary_fixture(
        tmp_path / "partial",
        exclude_files={"olist_order_items_dataset.csv", "olist_products_dataset.csv"},
    )
    res = load_olist_dataset(partial_dir)
    assert res.ok is False
    assert set(res.missing_files) == {
        "olist_order_items_dataset.csv",
        "olist_products_dataset.csv",
    }
    assert "olist_orders_dataset.csv" not in res.missing_files
    assert "olist_customers_dataset.csv" not in res.missing_files


def test_t1_f03_05_strict_local_only_reading_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import socket
    from unidata.loader import load_olist_dataset

    copy_dir = copy_primary_fixture(tmp_path / "offline")

    def _forbid_network(*args, **kwargs):
        raise RuntimeError("Network access is forbidden during local CSV loading")

    monkeypatch.setattr(socket, "create_connection", _forbid_network)
    res = load_olist_dataset(copy_dir)
    assert res.ok is True
    assert res.data_dir == copy_dir


# ===========================================================================
# F4 — Schema, Encoding, Type & Key Validation (5 cases)
# ===========================================================================


def test_t1_f04_01_preserves_all_id_columns_as_stripped_str(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.loader import load_olist_dataset

    data_dir = build_fix_multi_pay(tmp_path / "ids")
    res = load_olist_dataset(data_dir)
    assert res.ok is True
    orders = res.tables["orders"]
    items = res.tables["order_items"]
    customers = res.tables["customers"]
    assert pd.api.types.is_string_dtype(orders["order_id"]) or orders["order_id"].dtype == object
    assert pd.api.types.is_string_dtype(items["order_item_id"]) or items["order_item_id"].dtype == object
    assert "000123" in set(orders["order_id"])
    assert "000001" in set(customers["customer_id"])
    assert "000901" in set(customers["customer_unique_id"])
    assert all(not str(v).endswith(".0") for v in orders["order_id"])


def test_t1_f04_02_parses_order_purchase_timestamp_as_datetime64() -> None:
    import pandas as pd
    from unidata.loader import load_olist_dataset

    res = load_olist_dataset(PRIMARY_FIXTURE_DIR)
    assert res.ok is True
    assert pd.api.types.is_datetime64_any_dtype(res.tables["orders"]["order_purchase_timestamp"])


def test_t1_f04_03_parses_price_as_numeric_float() -> None:
    import pandas as pd
    from unidata.loader import load_olist_dataset

    res = load_olist_dataset(PRIMARY_FIXTURE_DIR)
    assert res.ok is True
    prices = res.tables["order_items"]["price"]
    assert pd.api.types.is_numeric_dtype(prices)
    assert (prices >= 0).all()


def test_t1_f04_04_handles_utf8_bom_csvs_cleanly(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    bom_dir = build_fix_bom_long(tmp_path / "bom")
    res = load_olist_dataset(bom_dir)
    assert res.ok is True
    for df in res.tables.values():
        for col in df.columns:
            assert not str(col).startswith("\ufeff"), f"BOM artifact in column {col!r}"


def test_t1_f04_05_missing_required_column_returns_structured_schema_error(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.loader import load_olist_dataset

    bad_dir = copy_primary_fixture(tmp_path / "missing_col")
    orders_path = bad_dir / "olist_orders_dataset.csv"
    df = pd.read_csv(orders_path).drop(columns=["order_purchase_timestamp"])
    df.to_csv(orders_path, index=False)

    res = load_olist_dataset(bad_dir)
    assert res.ok is False
    assert len(res.errors) == 1
    err = res.errors[0]
    assert err.filename == "olist_orders_dataset.csv"
    assert "order_purchase_timestamp" in err.missing_columns
    assert "order_purchase_timestamp" in err.message_pt


# ===========================================================================
# F5 — Delivered Order Filtering & Non-Duplicating Relational Joins (5 cases)
# ===========================================================================


def test_t1_f05_01_keeps_only_delivered_orders() -> None:
    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    assert prepared.diagnostics.orders_total_read == 46
    assert prepared.diagnostics.orders_delivered == 42
    assert prepared.diagnostics.orders_excluded_status == 4
    assert prepared.orders_df["order_id"].nunique() == 42
    assert len(prepared.orders_df) == 42


def test_t1_f05_02_multi_item_order_preserves_all_items_without_order_duplication(tmp_path: Path) -> None:
    _, prepared = _load_and_prepare(build_fix_multi_pay(tmp_path / "multi"))
    ord1_items = prepared.items_df[prepared.items_df["order_id"] == "000123"]
    ord1_rows = prepared.orders_df[prepared.orders_df["order_id"] == "000123"]
    assert len(ord1_items) == 2
    assert ord1_items["price"].sum() == pytest.approx(150.00)
    assert len(ord1_rows) == 1
    assert ord1_rows.iloc[0]["order_product_revenue"] == pytest.approx(150.00)
    assert int(ord1_rows.iloc[0]["items_count"]) == 2


def test_t1_f05_03_extra_order_payments_csv_never_inflates_joins(tmp_path: Path) -> None:
    data_dir = build_fix_multi_pay(tmp_path / "pay")
    assert (data_dir / "olist_order_payments_dataset.csv").is_file()
    _, prepared = _load_and_prepare(data_dir)
    assert prepared.items_df["price"].sum() == pytest.approx(350.00)
    assert prepared.orders_df["order_product_revenue"].sum() == pytest.approx(350.00)


def test_t1_f05_04_joins_customers_resolving_customer_unique_id(tmp_path: Path) -> None:
    _, prepared = _load_and_prepare(build_fix_repeat(tmp_path / "rep"))
    assert prepared.diagnostics.customers_total_read == 12
    assert prepared.diagnostics.unique_customers_delivered == 6
    assert prepared.orders_df["customer_id"].nunique() == 12
    assert prepared.orders_df["customer_unique_id"].nunique() == 6
    assert prepared.items_df["customer_unique_id"].isna().sum() == 0


def test_t1_f05_05_emits_complete_data_diagnostics_metadata() -> None:
    import pandas as pd

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    diag = prepared.diagnostics
    assert diag.orders_total_read == 46
    assert diag.orders_delivered == 42
    assert diag.orders_excluded_status == 4
    assert diag.items_total_read == 52
    assert diag.items_in_delivered_orders == 48
    assert diag.customers_total_read == 46
    assert diag.products_total_read == 6
    assert diag.translation_loaded is True
    assert diag.unique_customers_delivered == 24
    assert diag.min_purchase_date == pd.Timestamp("2017-05-10 12:00:00")
    assert diag.max_purchase_date == pd.Timestamp("2018-08-20 12:00:00")


# ===========================================================================
# F6 — Safe Caching (5 cases)
# ===========================================================================


@pytest.mark.ui
def test_t1_f06_01_streamlit_reruns_reuse_cached_dataset_on_filter_change(repo_root: Path) -> None:
    app_src = (repo_root / "app.py").read_text(encoding="utf-8")
    assert "cache_data" in app_src, "app.py must use @st.cache_data"
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, console_errs, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            initial = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in initial

            t0 = time.monotonic()
            mode = apply_temporal_filter(page, "2018")
            elapsed = time.monotonic() - t0
            filtered_text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            if mode in ("selectbox", "radio"):
                assert "5.640,00" in filtered_text or "188,00" in filtered_text
            else:
                assert "10.920,00" not in filtered_text
            assert elapsed < 10.0, f"Cached filter rerun took too long: {elapsed:.2f}s"
            assert "Traceback" not in filtered_text
            assert not page_errs, f"Page errors: {page_errs}"


@pytest.mark.ui
def test_t1_f06_02_cache_invalidates_when_csv_mtime_and_content_change(tmp_path: Path) -> None:
    import pandas as pd

    mut_dir = copy_primary_fixture(tmp_path / "cache_mut")
    with launch_streamlit_app(mut_dir) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text1 = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in text1

            items_csv = mut_dir / "olist_order_items_dataset.csv"
            df = pd.read_csv(items_csv, dtype={"order_id": str, "order_item_id": str, "product_id": str})
            df.loc[df["order_id"] == "ORD_G4_19", "price"] = df.loc[df["order_id"] == "ORD_G4_19", "price"] + 100.0
            df.to_csv(items_csv, index=False)
            now = time.time() + 5.0
            os.utime(items_csv, (now, now))

            page.reload(wait_until="domcontentloaded")
            text2 = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "11.020,00" in text2


def test_t1_f06_03_core_pipeline_callable_without_streamlit_runtime() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
        kpis = compute_kpis(prepared)
        monthly = compute_monthly_series(prepared)
        cats = compute_category_ranking(prepared)
        seg = compute_rfm_and_clusters(prepared.items_df)
        recs = generate_recommendations(kpis, monthly, cats, seg, "Mai/2017–Ago/2018", "Base completa")

    st_warnings = [w for w in caught if "ScriptRunContext" in str(w.message)]
    assert not st_warnings, f"Unexpected Streamlit warnings in headless mode: {st_warnings}"
    assert kpis.delivered_orders == 42
    assert seg.ok is True
    assert len(recs) >= 1


def test_t1_f06_04_cache_key_isolates_distinct_data_directories(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    dir_a = copy_primary_fixture(tmp_path / "dir_a")
    dir_b = build_fix_multi_pay(tmp_path / "dir_b")
    _, prep_a = _load_and_prepare(dir_a)
    _, prep_b = _load_and_prepare(dir_b)
    assert compute_kpis(prep_a).product_revenue == pytest.approx(10920.00)
    assert compute_kpis(prep_b).product_revenue == pytest.approx(350.00)


def test_t1_f06_05_filter_slicing_does_not_mutate_prepared_dataset() -> None:
    from unidata.analytics import compute_kpis, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    orig_orders = len(prepared.orders_df)
    orig_items = len(prepared.items_df)

    filtered = filter_prepared_data(prepared, start_ym="2018-05", end_ym="2018-08")
    assert compute_kpis(filtered).product_revenue == pytest.approx(5640.00)
    assert len(prepared.orders_df) == orig_orders
    assert len(prepared.items_df) == orig_items
    assert compute_kpis(prepared).product_revenue == pytest.approx(10920.00)


# ===========================================================================
# F7 — Overview KPIs (5 cases)
# ===========================================================================


def test_t1_f07_01_product_revenue_sums_price_excluding_freight(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(build_fix_multi_pay(tmp_path / "kpi_rev"))
    kpis = compute_kpis(prepared)
    assert kpis.product_revenue == pytest.approx(350.00)


def test_t1_f07_02_delivered_orders_counts_distinct_order_id(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(build_fix_multi_pay(tmp_path / "kpi_ord"))
    kpis = compute_kpis(prepared)
    assert kpis.delivered_orders == 2


def test_t1_f07_03_unique_customers_counts_distinct_customer_unique_id(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(build_fix_repeat(tmp_path / "kpi_cust"))
    kpis = compute_kpis(prepared)
    assert kpis.delivered_orders == 12
    assert kpis.unique_customers == 6


def test_t1_f07_04_average_ticket_equals_revenue_divided_by_orders(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(build_fix_multi_pay(tmp_path / "kpi_tkt"))
    kpis = compute_kpis(prepared)
    assert kpis.avg_ticket == pytest.approx(175.00)

    _, prep_primary = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    kpis_p = compute_kpis(prep_primary)
    assert kpis_p.product_revenue == pytest.approx(10920.00)
    assert kpis_p.delivered_orders == 42
    assert kpis_p.unique_customers == 24
    assert kpis_p.avg_ticket == pytest.approx(260.00)


def test_t1_f07_05_kpi_period_bounds_reflect_delivered_span() -> None:
    import pandas as pd
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    kpis = compute_kpis(prepared)
    assert kpis.is_empty is False
    assert kpis.period_start == pd.Timestamp("2017-05-10 12:00:00")
    assert kpis.period_end == pd.Timestamp("2018-08-20 12:00:00")


# ===========================================================================
# F8 — Monthly Calendar Time Series (5 cases)
# ===========================================================================


def test_t1_f08_01_aggregates_year_month_chronologically() -> None:
    from unidata.analytics import compute_monthly_series

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    monthly = compute_monthly_series(prepared)
    yms = monthly["year_month"].tolist()
    assert yms == ["2017-05", "2017-11", "2018-05", "2018-08"]
    assert yms == sorted(yms)


def test_t1_f08_02_monthly_revenue_orders_and_avg_ticket_match_formulas() -> None:
    from unidata.analytics import compute_kpis, compute_monthly_series

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    kpis = compute_kpis(prepared)
    monthly = compute_monthly_series(prepared).set_index("year_month")

    assert monthly["product_revenue"].sum() == pytest.approx(kpis.product_revenue)
    assert int(monthly["delivered_orders"].sum()) == kpis.delivered_orders
    expected = {
        "2017-05": (600.00, 4, 150.00),
        "2017-11": (4680.00, 8, 585.00),
        "2018-05": (2400.00, 12, 200.00),
        "2018-08": (3240.00, 18, 180.00),
    }
    for ym, (rev, ords, tkt) in expected.items():
        row = monthly.loc[ym]
        assert row["product_revenue"] == pytest.approx(rev)
        assert int(row["delivered_orders"]) == ords
        assert row["avg_ticket"] == pytest.approx(tkt)


def test_t1_f08_03_missing_calendar_months_not_silently_backfilled_as_zero() -> None:
    import pandas as pd
    from unidata.analytics import compute_monthly_series

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    monthly = compute_monthly_series(prepared)
    if "2017-06" in set(monthly["year_month"]):
        row = monthly[monthly["year_month"] == "2017-06"].iloc[0]
        assert pd.isna(row["product_revenue"]), "Gap month must not fabricate 0.00 revenue"
    else:
        assert len(monthly) == 4


def test_t1_f08_04_yoy_same_month_percentage_computed_when_prior_year_exists(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.analytics import compute_monthly_series

    _, prep_p = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    m_p = compute_monthly_series(prep_p).set_index("year_month")
    assert pd.isna(m_p.loc["2017-05", "yoy_revenue_pct"])
    assert float(m_p.loc["2018-05", "yoy_revenue_pct"]) == pytest.approx(300.0, abs=0.1)

    _, prep_s = _load_and_prepare(build_fix_seasonal(tmp_path / "seasonal_yoy"))
    m_s = compute_monthly_series(prep_s).set_index("year_month")
    assert pd.notna(m_s.loc["2018-11", "yoy_revenue_pct"])


def test_t1_f08_05_month_formatter_converts_yyyy_mm_to_pt_br() -> None:
    from unidata.formatting import format_month_pt

    cases = {
        "2017-11": "nov/2017",
        "2018-02": "fev/2018",
        "2018-05": "mai/2018",
        "2018-08": "ago/2018",
        "2018-09": "set/2018",
        "2018-10": "out/2018",
        "2017-12": "dez/2017",
    }
    for ym, expected_lower in cases.items():
        assert format_month_pt(ym).lower() == expected_lower


# ===========================================================================
# F9 — Product Category Aggregation & Translation Fallback (5 cases)
# ===========================================================================


def test_t1_f09_01_uses_english_translation_when_present() -> None:
    from unidata.analytics import compute_category_ranking

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    cats = compute_category_ranking(prepared)
    assert "bed_bath_table" in set(cats["category"])
    assert "health_beauty" in set(cats["category"])
    assert "livros_tecnicos" in set(cats["category"])


def test_t1_f09_02_falls_back_to_portuguese_slug_when_translation_missing(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking

    _, prepared = _load_and_prepare(build_fix_no_trans(tmp_path / "no_trans_cat"))
    cats = compute_category_ranking(prepared)
    names = set(cats["category"])
    assert "cama_mesa_banho" in names
    assert "beleza_saude" in names


def test_t1_f09_03_null_empty_category_maps_to_nao_informado(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking

    _, prep_p = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    cats_p = compute_category_ranking(prep_p).set_index("category")
    assert "Não informado" in cats_p.index
    assert cats_p.loc["Não informado", "product_revenue"] == pytest.approx(540.00)

    _, prep_nt = _load_and_prepare(build_fix_no_trans(tmp_path / "no_trans_null"))
    cats_nt = compute_category_ranking(prep_nt)
    assert "Não informado" in set(cats_nt["category"])


def test_t1_f09_04_sorts_categories_descending_with_exact_revenue_share() -> None:
    from unidata.analytics import compute_category_ranking

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    cats = compute_category_ranking(prepared)
    assert cats["product_revenue"].is_monotonic_decreasing
    assert (cats["revenue_share_pct"] >= 0.0).all()
    assert (cats["revenue_share_pct"] <= 100.0).all()
    assert cats["revenue_share_pct"].sum() == pytest.approx(100.0, abs=0.1)
    assert float(cats.iloc[0]["revenue_share_pct"]) == pytest.approx(45.24, abs=0.2)
    assert cats.iloc[0]["category"] == "bed_bath_table"
    assert cats.iloc[0]["product_revenue"] == pytest.approx(4940.00)


def test_t1_f09_05_computes_items_count_and_distinct_orders_and_top_n() -> None:
    from unidata.analytics import compute_category_ranking

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    cats_all = compute_category_ranking(prepared).set_index("category")
    assert int(cats_all.loc["bed_bath_table", "items_count"]) == 12
    assert int(cats_all.loc["bed_bath_table", "delivered_orders"]) == 12

    cats_top3 = compute_category_ranking(prepared, top_n=3)
    assert len(cats_top3) == 3
    assert cats_top3["category"].tolist() == [
        "bed_bath_table",
        "computers_accessories",
        "health_beauty",
    ]


# ===========================================================================
# F10 — RFM Feature Table (customer_unique_id) (5 cases)
# ===========================================================================


def test_t1_f10_01_produces_one_row_per_unique_customer(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(build_fix_repeat(tmp_path / "rfm_uniq"))
    rfm_df, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "recency", "frequency", "monetary"}.issubset(set(rfm_df.columns))
    assert len(rfm_df) == 6
    assert rfm_df["customer_unique_id"].is_unique


def test_t1_f10_02_reference_date_equals_dataset_max_delivered_date() -> None:
    import pandas as pd
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    _, ref_date = compute_rfm_table(prepared.items_df)
    assert ref_date == pd.Timestamp("2018-08-20 12:00:00")


def test_t1_f10_03_recency_equals_days_from_reference_date() -> None:
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    rfm_df, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "recency", "frequency", "monetary"}.issubset(set(rfm_df.columns))
    by_uid = rfm_df.set_index("customer_unique_id")

    assert int(by_uid.loc["CUST_U01", "recency"]) == 0
    assert int(by_uid.loc["CUST_U03", "recency"]) == 2
    assert int(by_uid.loc["CUST_U07", "recency"]) == 10
    assert int(by_uid.loc["CUST_U19", "recency"]) == 467
    assert (rfm_df["recency"] >= 0).all()


def test_t1_f10_04_frequency_equals_nunique_order_id_across_customer_ids(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(build_fix_repeat(tmp_path / "rfm_freq"))
    rfm_df, _ = compute_rfm_table(prepared.items_df)
    assert "frequency" in rfm_df.columns
    assert (rfm_df["frequency"] == 2).all()


def test_t1_f10_05_monetary_equals_sum_price_excluding_freight(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(build_fix_multi_pay(tmp_path / "rfm_mon"))
    rfm_df, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "monetary"}.issubset(set(rfm_df.columns))
    by_uid = rfm_df.set_index("customer_unique_id")
    assert by_uid.loc["000901", "monetary"] == pytest.approx(150.00)
    assert by_uid.loc["000902", "monetary"] == pytest.approx(200.00)


# ===========================================================================
# F11 — Reproducible K-means Clustering (k=4) & Semantic Labeling (5 cases)
# ===========================================================================


def test_t1_f11_01_produces_four_deterministic_clusters() -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is True
    assert seg.customer_count == 24
    assert seg.rfm_df is not None
    assert {
        "customer_unique_id",
        "recency",
        "frequency",
        "monetary",
        "cluster_id",
        "cluster_label",
    }.issubset(set(seg.rfm_df.columns))
    assert seg.cluster_summary is not None
    assert len(seg.cluster_summary) == 4
    assert int(seg.cluster_summary["customer_count"].sum()) == 24
    assert (seg.cluster_summary["customer_pct"] >= 0.0).all()
    assert (seg.cluster_summary["customer_pct"] <= 100.0).all()
    assert seg.cluster_summary["customer_pct"].sum() == pytest.approx(100.0, abs=0.1)
    assert all(float(v) == pytest.approx(25.0, abs=0.1) for v in seg.cluster_summary["customer_pct"])


def test_t1_f11_02_repeated_runs_yield_identical_cluster_assignments() -> None:
    import pandas as pd
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg1 = compute_rfm_and_clusters(prepared.items_df)
    seg2 = compute_rfm_and_clusters(prepared.items_df)
    assert seg1.ok and seg2.ok
    assert {"customer_unique_id", "cluster_id", "cluster_label"}.issubset(set(seg1.rfm_df.columns))
    m1 = seg1.rfm_df.set_index("customer_unique_id")["cluster_label"].sort_index()
    m2 = seg2.rfm_df.set_index("customer_unique_id")["cluster_label"].sort_index()
    pd.testing.assert_series_equal(m1, m2)
    pd.testing.assert_frame_equal(seg1.cluster_summary, seg2.cluster_summary)


def test_t1_f11_03_model_info_documents_transform_scaler_params_and_ref_date() -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is True
    info_str = str(seg.model_info).lower()
    assert seg.model_info.get("n_clusters") == 4 or "4" in info_str
    assert seg.model_info.get("random_state") == 42 or "42" in info_str
    assert seg.model_info.get("n_init") == 10 or "10" in info_str
    assert "log1p" in info_str
    assert "standardscaler" in info_str
    assert "2018-08-20" in info_str or seg.reference_date is not None


def test_t1_f11_04_semantic_labels_do_not_expose_raw_cluster_ids_as_hierarchy() -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is True
    summary = seg.cluster_summary
    required_cols = {
        "cluster_label",
        "profile_description",
        "customer_count",
        "customer_pct",
        "median_recency",
        "median_frequency",
        "median_monetary",
        "avg_ticket",
    }
    assert required_cols.issubset(set(summary.columns))
    for lbl in summary["cluster_label"]:
        assert not re.fullmatch(r"cluster\s*[0-3]", str(lbl).strip().lower())


def test_t1_f11_05_shuffled_input_rows_produce_identical_cluster_summary() -> None:
    import pandas as pd
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    seg_orig = compute_rfm_and_clusters(prepared.items_df)
    shuffled_items = prepared.items_df.sample(frac=1.0, random_state=99).reset_index(drop=True)
    seg_shuf = compute_rfm_and_clusters(shuffled_items)
    assert seg_orig.ok and seg_shuf.ok
    pd.testing.assert_frame_equal(seg_orig.cluster_summary, seg_shuf.cluster_summary)


# ===========================================================================
# F12 — Deterministic Explainable Recommendations (5 cases)
# ===========================================================================


def test_t1_f12_01_generates_recommendations_across_all_three_categories() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    kpis = compute_kpis(prepared)
    monthly = compute_monthly_series(prepared)
    cats = compute_category_ranking(prepared)
    seg = compute_rfm_and_clusters(prepared.items_df)
    recs = generate_recommendations(kpis, monthly, cats, seg, "Mai/2017–Ago/2018", "Base completa")

    rec_cats = {r.category for r in recs}
    assert rec_cats == {"Clientes", "Sazonalidade", "Produtos"}
    strengths = [r.strength for r in recs]
    assert strengths == sorted(strengths, reverse=True)


def test_t1_f12_02_each_recommendation_attaches_numeric_evidence_and_period() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        compute_rfm_and_clusters(prepared.items_df),
        "Mai/2017–Ago/2018",
        "Base completa",
    )
    for rec in recs:
        assert rec.evidence.strip()
        assert re.search(r"(R\$|\d+,\d+%|\d+)", rec.evidence)
        assert "Mai/2017–Ago/2018" in rec.period or "Base completa" in rec.period


def test_t1_f12_03_uses_cautious_non_causal_pt_br_action_verbs() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        compute_rfm_and_clusters(prepared.items_df),
        "Mai/2017–Ago/2018",
        "Base completa",
    )
    cautious_markers = ("avalie", "considere", "investigue", "indica", "priorize", "observe", "monitore")
    forbidden = ("vai aumentar", "aumentará vendas", "garante aumento", "comprovadamente aumenta")
    for rec in recs:
        text = f"{rec.title} {rec.observation}".lower()
        assert any(w in text for w in cautious_markers), f"Missing cautious verb in: {text}"
        for bad in forbidden:
            assert bad not in text, f"Forbidden causal phrase '{bad}' in: {text}"


def test_t1_f12_04_includes_historical_olist_non_causal_caveat() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        compute_rfm_and_clusters(prepared.items_df),
        "Mai/2017–Ago/2018",
        "Base completa",
    )
    for rec in recs:
        cav = rec.caveat.lower()
        assert "históric" in cav or "historic" in cav
        assert "olist" in cav
        assert "causal" in cav or "previs" in cav


def test_t1_f12_05_deterministic_output_across_repeated_executions() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    kpis = compute_kpis(prepared)
    monthly = compute_monthly_series(prepared)
    cats = compute_category_ranking(prepared)
    seg = compute_rfm_and_clusters(prepared.items_df)
    r1 = generate_recommendations(kpis, monthly, cats, seg, "Mai/2017–Ago/2018", "Base completa")
    r2 = generate_recommendations(kpis, monthly, cats, seg, "Mai/2017–Ago/2018", "Base completa")
    assert r1 == r2


# ===========================================================================
# F13 — Interactive Temporal Filtering (Year / Month Range) (5 cases)
# ===========================================================================


def test_t1_f13_01_filter_prepared_data_restricts_to_range() -> None:
    from unidata.analytics import filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    filtered = filter_prepared_data(prepared, start_ym="2018-01", end_ym="2018-08")
    assert set(filtered.orders_df["year_month"]).issubset({"2018-05", "2018-08"})
    assert set(filtered.items_df["year_month"]).issubset({"2018-05", "2018-08"})
    assert len(filtered.orders_df) == 30


@pytest.mark.ui
def test_t1_f13_02_filter_propagates_consistently_in_streamlit_ui() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            initial = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in initial

            mode = apply_temporal_filter(page, "2018")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            if mode in ("selectbox", "radio"):
                assert "5.640,00" in text and "188,00" in text
            else:
                assert "10.920,00" not in text


@pytest.mark.ui
def test_t1_f13_03_explicit_rfm_scope_declaration_visible_when_filtered() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            apply_temporal_filter(page, "2018")
            text = wait_for_streamlit_ready(page).lower()
            assert ("base completa" in text) or ("período filtrado" in text) or ("recorte" in text)


@pytest.mark.ui
def test_t1_f13_04_reset_filter_restores_full_historical_interval() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            apply_temporal_filter(page, "2018")
            filtered_text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" not in filtered_text

            restored_text = click_reset_filter(page)
            assert "10.920,00" in restored_text


def test_t1_f13_05_single_month_filter_works_cleanly() -> None:
    from unidata.analytics import compute_kpis, compute_monthly_series, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    sliced = filter_prepared_data(prepared, start_ym="2017-11", end_ym="2017-11")
    kpis = compute_kpis(sliced)
    monthly = compute_monthly_series(sliced)
    assert len(monthly) == 1
    assert monthly.iloc[0]["year_month"] == "2017-11"
    assert kpis.product_revenue == pytest.approx(4680.00)


# ===========================================================================
# F14 — Dark REKKI/Operate Streamlit Dashboard (pt-BR) (5 cases)
# ===========================================================================


@pytest.mark.ui
def test_t1_f14_01_dashboard_renders_http_200_with_header_and_brand() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with urllib.request.urlopen(url, timeout=10.0) as resp:
            assert resp.status == 200
        with open_playwright_page() as (page, console_errs, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "E-commerce Insights" in text
            assert "Análise histórica da base Olist" in text
            assert "Sobre os dados" in text or "Metodologia" in text
            assert "Traceback" not in text
            assert not page_errs, f"Page errors: {page_errs}"
            assert not console_errs, f"Console errors: {console_errs}"


@pytest.mark.ui
def test_t1_f14_02_enforces_design_md_rekki_dark_color_tokens() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            colors = page.evaluate(
                """() => {
                    const app = document.querySelector('.stApp') || document.body;
                    const bodyBg = window.getComputedStyle(document.body).backgroundColor;
                    const appBg = window.getComputedStyle(app).backgroundColor;
                    const appColor = window.getComputedStyle(app).color;
                    const html = document.documentElement.outerHTML.toLowerCase();
                    return { bodyBg, appBg, appColor, hasTokens: html.includes('#000000') && html.includes('#040910') && html.includes('#0d0d0d') && html.includes('#0063e1') };
                }"""
            )
            assert colors["appBg"] == "rgb(0, 0, 0)" or colors["bodyBg"] == "rgb(0, 0, 0)"
            assert colors["appColor"] == "rgb(255, 255, 255)"
            assert colors["hasTokens"] is True


@pytest.mark.ui
def test_t1_f14_03_formats_currency_in_brl_with_nominal_disclaimer() -> None:
    from unidata.formatting import format_brl

    assert normalize_brl_spaces(format_brl(1234.56)) == "R$ 1.234,56"
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "R$ 10.920,00" in text
            assert "R$ 260,00" in text
            assert "nominal" in text.lower() or "nominais" in text.lower()


@pytest.mark.ui
def test_t1_f14_04_renders_all_5_core_analytical_sections_in_pt_br() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text_lower = wait_for_streamlit_ready(page).lower()
            for section in ("visão geral", "sazonalidade", "clientes", "categorias", "recomendações"):
                assert section in text_lower, f"Missing UI section: {section}"


@pytest.mark.ui
def test_t1_f14_05_uses_mandatory_pt_br_domain_vocabulary() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page).lower()
            for term in (
                "receita de produtos",
                "ticket médio por pedido",
                "clientes únicos",
                "período analisado",
                "padrão histórico observado",
            ):
                assert term in text, f"Missing mandatory pt-BR term: '{term}'"


# ===========================================================================
# F15 — Accessible Charts, Alternative Tables & Responsiveness (5 cases)
# ===========================================================================


@pytest.mark.ui
def test_t1_f15_01_monthly_chart_is_2d_line_with_metric_selector_and_title() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            chart_info = page.evaluate(
                """() => {
                    const plots = Array.from(document.querySelectorAll('.js-plotly-plot'));
                    const has3d = plots.some(el => (el.data || []).some(tr => String(tr.type || '').includes('3d')))
                        || (document.querySelectorAll('.gl-container canvas').length > 0 && document.body.innerHTML.includes('scatter3d'));
                    const titles = plots.map(el => {
                        const layoutTitle = el.layout && el.layout.title && el.layout.title.text ? String(el.layout.title.text) : '';
                        const svgTitleEl = el.querySelector('.gtitle');
                        const svgTitle = svgTitleEl ? (svgTitleEl.textContent || '') : '';
                        return (layoutTitle || svgTitle).trim();
                    });
                    const hasLineOrScatter = plots.some(el => (el.data || []).some(tr => ['scatter', 'scattergl', 'line'].includes(String(tr.type || 'scatter'))));
                    return { plotCount: plots.length, has3d, titles, hasLineOrScatter };
                }"""
            )
            assert chart_info["plotCount"] >= 2
            assert chart_info["has3d"] is False
            assert chart_info["hasLineOrScatter"] is True

            # Verify descriptive metric+unit chart title (never generic "Performance" alone)
            non_empty_titles = [t.lower() for t in chart_info["titles"] if t]
            if not non_empty_titles:
                # Fallback: check heading elements directly above plots
                non_empty_titles = page.evaluate(
                    """() => Array.from(document.querySelectorAll('h1, h2, h3, h4, .gtitle'))
                        .map(el => (el.innerText || el.textContent || '').trim().toLowerCase())"""
                )
            assert any(
                any(k in t for k in ("receita", "pedidos", "ticket", "r$", "mensal", "categoria", "segment"))
                and t.strip() != "performance"
                for t in non_empty_titles
            ), f"Missing descriptive metric+unit chart title in: {non_empty_titles}"

            # Verify metric selector controls expose Receita, Pedidos, and Ticket
            controls_text = page.evaluate(
                """() => Array.from(document.querySelectorAll(
                    '[data-testid="stRadio"], [data-testid="stButtonGroup"], [role="radiogroup"], [role="tablist"], button'
                )).map(el => (el.innerText || el.textContent || '')).join(' | ').toLowerCase()"""
            )
            if not all(k in controls_text for k in ("receita", "pedidos", "ticket")):
                # Inspect selectbox dropdown options if selector is a stSelectbox
                selectboxes = page.locator('[data-testid="stSelectbox"]')
                collected_opts = [controls_text]
                for idx in range(selectboxes.count()):
                    selectboxes.nth(idx).click()
                    page.wait_for_timeout(150)
                    opts = page.locator('[role="option"]').all_inner_texts()
                    collected_opts.append(" | ".join(opts).lower())
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(100)
                controls_text = " | ".join(collected_opts)
            for metric_kw in ("receita", "pedidos", "ticket"):
                assert metric_kw in controls_text, (
                    f"Missing monthly metric selector option '{metric_kw}' in UI controls: {controls_text}"
                )


@pytest.mark.ui
def test_t1_f15_02_category_and_segment_charts_have_non_color_only_encoding() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "bed_bath_table" in text
            assert "4.940,00" in text
            assert "25,0%" in text or "25.0%" in text


@pytest.mark.ui
def test_t1_f15_03_tabular_and_textual_alternatives_accompany_charts() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            tables = page.locator("table, [data-testid='stDataFrame'], [data-testid='stTable']")
            assert tables.count() >= 2


@pytest.mark.ui
def test_t1_f15_04_desktop_1440_layout_without_horizontal_overflow() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(1440, 900)) as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= 1442, f"Desktop horizontal overflow: scrollWidth={scroll_w}"


@pytest.mark.ui
def test_t1_f15_05_visible_keyboard_focus_rings_and_labeled_controls() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            _capture_unfocused_styles(page)
            focused_any = False
            for _ in range(15):
                page.keyboard.press("Tab")
                if _find_visible_focus_indicator(page):
                    focused_any = True
                    break
            assert focused_any, "No visible keyboard focus indicator detected across Tab navigation"

            unlabeled = page.evaluate(
                """() => Array.from(document.querySelectorAll('button, [role="combobox"], [role="slider"]'))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return false;
                        const label = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                        return !label;
                    }).length"""
            )
            assert unlabeled == 0, f"Found {unlabeled} visible interactive control(s) without accessible label"


# ===========================================================================
# F16 — Methodology, Provenance & CC BY-NC-SA 4.0 Disclosure (5 cases)
# ===========================================================================


@pytest.mark.ui
def test_t1_f16_01_methodology_section_accessible_directly_in_ui() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "Olist" in text and "CC BY-NC-SA 4.0" in text


@pytest.mark.ui
def test_t1_f16_02_displays_olist_kaggle_attribution_and_cc_license() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "Olist" in text
            assert "Kaggle" in text
            assert "CC BY-NC-SA 4.0" in text
            assert "não comercial" in text.lower()


@pytest.mark.ui
def test_t1_f16_03_documents_exact_analytical_rules_and_kmeans_params() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "delivered" in text.lower()
            assert "customer_unique_id" in text
            assert re.search(r"(?<![\d.,])\b42\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b10\b(?![\d.,])", text)
            assert "StandardScaler" in text or "padroniz" in text.lower()


@pytest.mark.ui
def test_t1_f16_04_displays_data_quality_diagnostics_counts() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = normalize_brl_spaces(expand_methodology_section(page))
            lower = text.lower()
            assert any(k in lower for k in ("lido", "entreg", "exclu", "diagnóstic", "qualidade")), (
                "Missing diagnostics context labels in expanded methodology section"
            )
            assert re.search(r"(?<![\d.,])\b46\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b42\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b24\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b4\b(?![\d.,%])", text)


@pytest.mark.ui
def test_t1_f16_05_states_explicit_limitations_no_national_claim_no_forecast() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page).lower()
            assert "causal" in text or "previs" in text or "prevê" in text
            assert "olist" in text


# ===========================================================================
# F17 — Automated Test Suite on Synthetic Fixtures (5 cases)
# ===========================================================================


def test_t1_f17_01_core_unit_integration_suite_runs_offline_via_pytest(repo_root: Path) -> None:
    unit_files = sorted(p for p in (repo_root / "tests").glob("test_*.py"))
    assert len(unit_files) >= 2, f"Expected unit/integration test files in tests/: {unit_files}"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *[str(p) for p in unit_files], "-q"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"Core tests failed:\n{proc.stdout}\n{proc.stderr}"


def test_t1_f17_02_multi_item_multi_payment_fixture_oracle_passes(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(build_fix_multi_pay(tmp_path / "f17_mp"))
    kpis = compute_kpis(prepared)
    assert kpis.product_revenue == pytest.approx(350.00)
    assert kpis.delivered_orders == 2


def test_t1_f17_03_repeat_customer_unique_id_deduplication_oracle_passes(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(build_fix_repeat(tmp_path / "f17_rep"))
    kpis = compute_kpis(prepared)
    rfm, _ = compute_rfm_table(prepared.items_df)
    assert "frequency" in rfm.columns
    assert kpis.unique_customers == 6
    assert (rfm["frequency"] == 2).all()


def test_t1_f17_04_reproducible_kmeans_and_recommendation_caveat_oracle_passes() -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
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
    assert seg.ok is True
    assert all("olist" in r.caveat.lower() for r in recs)


def test_t1_f17_05_e2e_suite_uses_isolated_fixtures_separate_from_data(repo_root: Path) -> None:
    assert (PRIMARY_FIXTURE_DIR / "olist_orders_dataset.csv").is_file()
    data_dir = repo_root / "data"
    assert list(data_dir.glob("*.csv")) == []


# ===========================================================================
# F18 — Detailed "Unidata" README.md (5 live m4_deliverable cases)
# ===========================================================================


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f18_01_readme_exists_and_starts_with_unidata_title(repo_root: Path) -> None:
    readme = repo_root / "README.md"
    assert readme.is_file(), "Live README.md missing in workspace"
    lines = [ln.strip() for ln in readme.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines and lines[0] == "# Unidata"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f18_02_readme_documents_summary_problem_and_architecture(repo_root: Path) -> None:
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=False)
    arch_errs = [e for e in errs if "summary" in e or "architecture" in e or "not found" in e]
    assert not arch_errs, f"README architecture/summary issues: {arch_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f18_03_readme_documents_install_kaggle_placement_run_and_test(repo_root: Path) -> None:
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=False)
    setup_errs = [
        e
        for e in errs
        if any(k in e for k in ("pip install", "Kaggle", "5 Olist", "data/", "streamlit", "pytest", "not found"))
    ]
    assert not setup_errs, f"README setup/command issues: {setup_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f18_04_readme_documents_methodology_limitations_and_impeccable(repo_root: Path) -> None:
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=False)
    meth_errs = [e for e in errs if any(k in e for k in ("K-means", "causal", "Impeccable", "not found"))]
    assert not meth_errs, f"README methodology/Impeccable issues: {meth_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f18_05_readme_includes_olist_attribution_and_cc_license(repo_root: Path) -> None:
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=False)
    lic_errs = [e for e in errs if any(k in e for k in ("CC BY-NC-SA", "non-commercial", "not found"))]
    assert not lic_errs, f"README license issues: {lic_errs}"


# ===========================================================================
# F19 — Project Showcase Presentation (8 Sections) (5 live m4_deliverable cases)
# ===========================================================================


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f19_01_all_4_project_showcase_deliverables_exist(repo_root: Path) -> None:
    pres = repo_root / "presentation"
    for fn in ("showcase.html", "showcase.config.json", "SOURCES.md", "README.md"):
        fpath = pres / fn
        assert fpath.is_file() and fpath.stat().st_size > 0, f"Missing or empty: {fpath}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f19_02_showcase_html_contains_all_8_required_pt_br_sections(repo_root: Path) -> None:
    errs = validate_showcase_dir(repo_root / "presentation")
    sec_errs = [e for e in errs if "section" in e or "Missing" in e]
    assert not sec_errs, f"Showcase section issues: {sec_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f19_03_showcase_config_preserves_unidata_identity_and_tokens(repo_root: Path) -> None:
    errs = validate_showcase_dir(repo_root / "presentation")
    cfg_errs = [e for e in errs if "showcase.config.json" in e or "Missing" in e]
    assert not cfg_errs, f"Showcase config issues: {cfg_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t1_f19_04_showcase_honest_provenance_no_fabricated_metrics(repo_root: Path) -> None:
    errs = validate_showcase_dir(repo_root / "presentation")
    prov_errs = [e for e in errs if "attribution" in e or "provenance" in e or "SOURCES.md" in e or "Missing" in e]
    assert not prov_errs, f"Showcase provenance issues: {prov_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
@pytest.mark.ui
def test_t1_f19_05_showcase_html_renders_cleanly_in_playwright(repo_root: Path) -> None:
    html_file = repo_root / "presentation" / "showcase.html"
    assert html_file.is_file(), f"Missing {html_file}"
    url = html_file.resolve().as_uri()
    for vp in ((1440, 900), (390, 844)):
        with open_playwright_page(viewport=vp) as (page, console_errs, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= vp[0] + 2, f"Showcase overflow at {vp}: {scroll_w}"
            assert not page_errs, f"Showcase page errors: {page_errs}"
            assert not console_errs, f"Showcase console errors: {console_errs}"


# ===========================================================================
# F20 — Final .zip Deliverable (5 live m6_release_gate cases)
# ===========================================================================


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t1_f20_01_deliverable_zip_exists_and_is_valid_non_corrupt(repo_root: Path) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    assert zip_path.is_file(), f"Missing deliverable {zip_path}"
    assert zipfile.is_zipfile(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert zf.testzip() is None


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t1_f20_02_archive_contains_complete_codebase_tests_readme_presentation(repo_root: Path) -> None:
    errs = validate_zip_deliverable(repo_root / "unidata-ecommerce-insights.zip")
    req_errs = [e for e in errs if "Missing" in e or "empty" in e]
    assert not req_errs, f"Zip inclusion errors: {req_errs}"


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t1_f20_03_archive_strictly_excludes_olist_csvs_venv_git_caches_agents(repo_root: Path) -> None:
    errs = validate_zip_deliverable(repo_root / "unidata-ecommerce-insights.zip")
    excl_errs = [e for e in errs if "Forbidden" in e or "Nested" in e or "Missing deliverable" in e]
    assert not excl_errs, f"Zip exclusion errors: {excl_errs}"


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t1_f20_04_extracted_zip_passes_core_pytest_suite(repo_root: Path, tmp_path: Path) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    assert zip_path.is_file(), f"Missing deliverable {zip_path}"
    extract_dir = tmp_path / "extracted_repo"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    candidates = [extract_dir, *[p for p in extract_dir.iterdir() if p.is_dir()]]
    root_in_zip = next((c for c in candidates if (c / "app.py").is_file()), None)
    assert root_in_zip is not None, "Could not locate app.py inside extracted zip"

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-m", "not m6_release_gate and not ui", "-q"],
        cwd=str(root_in_zip),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"Extracted zip pytest failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
@pytest.mark.ui
def test_t1_f20_05_extracted_zip_app_starts_cleanly_with_onboarding(repo_root: Path, tmp_path: Path) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    assert zip_path.is_file(), f"Missing deliverable {zip_path}"
    extract_dir = tmp_path / "extracted_app"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    candidates = [extract_dir, *[p for p in extract_dir.iterdir() if p.is_dir()]]
    root_in_zip = next((c for c in candidates if (c / "app.py").is_file()), None)
    assert root_in_zip is not None

    with launch_streamlit_app(root_in_zip / "data", app_root=root_in_zip) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in text
            assert "Traceback" not in text
            assert not page_errs
