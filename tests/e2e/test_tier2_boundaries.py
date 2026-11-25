"""Tier 2 E2E Tests: Boundary, Adversarial & Corner Cases (100 cases: T2-F01-01 .. T2-F20-05)."""

from __future__ import annotations

import ast
import fnmatch
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
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
    build_fix_large_batch,
    build_fix_no_deliv,
    build_fix_no_trans,
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


def _load_and_prepare(data_dir: Path):
    from unidata.loader import load_olist_dataset
    from unidata.pipeline import prepare_data

    res = load_olist_dataset(data_dir)
    assert res.ok, f"Load failed for {data_dir}: {res.missing_files} {res.errors}"
    return res, prepare_data(res.tables)


# ===========================================================================
# F1 — GitHub-Ready Project Structure & .gitignore (5 edge cases)
# ===========================================================================


def test_t2_f01_01_gitignore_blocks_nested_and_uppercase_olist_csvs(repo_root: Path) -> None:
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    patterns = [ln.strip() for ln in gitignore.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert "data/*" in patterns
    assert "!data/.gitkeep" in patterns
    assert any(fnmatch.fnmatch("olist_orders_dataset.csv", p) for p in patterns)
    assert any(p in ("data/*", "data/*.csv") for p in patterns)


def test_t2_f01_02_gitignore_does_not_ignore_e2e_synthetic_fixtures(repo_root: Path) -> None:
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in gitignore.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert "*.csv" not in lines, "Global *.csv would accidentally ignore tests/e2e/fixtures/primary/*.csv"


def test_t2_f01_03_no_forbidden_agents_or_gemini_md_anywhere(repo_root: Path) -> None:
    forbidden = []
    for p in repo_root.rglob("*"):
        if ".venv" in p.parts or ".git" in p.parts:
            continue
        if p.name in {"AGENTS.md", "GEMINI.md"}:
            forbidden.append(str(p))
    assert forbidden == [], f"Forbidden instruction files found: {forbidden}"


def test_t2_f01_04_no_hardcoded_absolute_user_paths_in_source(repo_root: Path) -> None:
    src_files = list((repo_root / "src").rglob("*.py")) + [repo_root / "app.py"]
    for sf in src_files:
        if not sf.is_file():
            continue
        txt = sf.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in txt and "C:/Users/" not in txt, f"Hardcoded Windows user path in {sf}"


def test_t2_f01_05_requirements_has_no_vcs_or_local_file_urls(repo_root: Path) -> None:
    req = (repo_root / "requirements.txt").read_text(encoding="utf-8")
    for ln in req.splitlines():
        s = ln.strip().lower()
        if not s or s.startswith("#"):
            continue
        assert "git+" not in s and not s.startswith("-e ") and "file://" not in s


# ===========================================================================
# F2 — Central Configuration (5 edge cases)
# ===========================================================================


def test_t2_f02_01_config_constants_remain_immutable_across_pipeline() -> None:
    from unidata import config

    req_before = dict(config.REQUIRED_FILES)
    id_before = tuple(config.ID_COLUMNS)
    cfg = config.RFMConfig()
    _load_and_prepare(PRIMARY_FIXTURE_DIR)
    assert config.REQUIRED_FILES == req_before
    assert config.ID_COLUMNS == id_before
    assert cfg.n_clusters == 4 and cfg.random_state == 42 and cfg.n_init == 10


def test_t2_f02_02_rfm_config_small_min_customers_guards_degenerate_clusters(tmp_path: Path) -> None:
    from unidata.config import RFMConfig
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(build_fix_small_rfm(tmp_path / "sr_cfg", variant="A"))
    seg = compute_rfm_and_clusters(prepared.items_df, config=RFMConfig(min_customers=2))
    assert seg.ok is False
    assert seg.error_message


def test_t2_f02_03_optional_translation_never_promoted_to_required() -> None:
    from unidata import config

    req_vals = {v[0] if isinstance(v, tuple) else v for v in config.REQUIRED_FILES.values()}
    assert "product_category_name_translation.csv" not in req_vals
    opt_vals = {v[0] if isinstance(v, tuple) else v for v in config.OPTIONAL_FILES.values()}
    assert "product_category_name_translation.csv" in opt_vals


def test_t2_f02_04_loader_reads_strictly_inside_configured_data_dir(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    # Put valid CSVs in parent, leave child empty -> must NOT traverse to parent
    copy_primary_fixture(tmp_path)
    empty_child = tmp_path / "nested_empty"
    empty_child.mkdir()
    res = load_olist_dataset(empty_child)
    assert res.ok is False
    assert len(res.missing_files) == 4


def test_t2_f02_05_formatting_edge_inputs_none_nan_zero_large_and_invalid() -> None:
    from unidata.formatting import format_brl, format_date_pt, format_int_pt, format_month_pt

    assert format_brl(None) == "—"
    assert format_brl(float("nan")) == "—"
    assert format_brl(float("inf")) == "—"
    assert normalize_brl_spaces(format_brl(0)) == "R$ 0,00"
    assert normalize_brl_spaces(format_brl(1000000.5)) == "R$ 1.000.000,50"
    assert format_int_pt(12345) == "12.345"
    assert format_date_pt(None) == "—"
    assert format_month_pt("not-a-month") == "—"


# ===========================================================================
# F3 — Fixed Olist CSV Loader & Missing-File Onboarding (5 edge cases)
# ===========================================================================


def test_t2_f03_01_empty_data_dir_with_only_gitkeep_lists_all_4_missing(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()
    (empty_dir / ".gitkeep").write_text("", encoding="utf-8")

    res = load_olist_dataset(empty_dir)
    assert res.ok is False
    assert len(res.missing_files) == 4
    assert "product_category_name_translation.csv" in res.onboarding_message_pt


def test_t2_f03_02_single_missing_required_csv_named_explicitly(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = copy_primary_fixture(tmp_path / "one_missing", exclude_files={"olist_products_dataset.csv"})
    res = load_olist_dataset(d)
    assert res.ok is False
    assert res.missing_files == ["olist_products_dataset.csv"]
    assert "olist_products_dataset.csv" in res.onboarding_message_pt


def test_t2_f03_03_zero_byte_csv_file_handled_without_traceback(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = copy_primary_fixture(tmp_path / "zero_byte")
    (d / "olist_orders_dataset.csv").write_bytes(b"")
    res = load_olist_dataset(d)
    assert res.ok is False
    assert any(e.filename == "olist_orders_dataset.csv" for e in res.errors)


def test_t2_f03_04_header_only_csv_handled_gracefully(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset
    from unidata.pipeline import prepare_data

    d = copy_primary_fixture(tmp_path / "header_only")
    (d / "olist_orders_dataset.csv").write_text(
        "order_id,customer_id,order_status,order_purchase_timestamp\n",
        encoding="utf-8",
    )
    res = load_olist_dataset(d)
    if res.ok:
        prep = prepare_data(res.tables)
        assert prep.diagnostics.orders_delivered == 0
    else:
        assert res.errors or res.missing_files


def test_t2_f03_05_corrupted_optional_translation_csv_does_not_crash(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = copy_primary_fixture(tmp_path / "bad_trans")
    (d / "product_category_name_translation.csv").write_bytes(b"\xff\xfe\x80\x81")
    res = load_olist_dataset(d)
    # Either reports explicit SchemaError for translation file or skips cleanly
    if res.ok:
        assert res.has_translation is False
    else:
        assert any("product_category_name_translation.csv" in e.filename for e in res.errors)


# ===========================================================================
# F4 — Schema, Encoding, Type & Key Validation (5 edge cases)
# ===========================================================================


def test_t2_f04_01_utf8_bom_crlf_and_quoted_commas(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = build_fix_bom_long(tmp_path / "bom_crlf")
    res = load_olist_dataset(d)
    assert res.ok is True
    cats = set(res.tables["products"]["product_category_name"].dropna())
    assert "Categoria, Especial" in cats


def test_t2_f04_02_non_utf8_binary_garbage_returns_encoding_error(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = copy_primary_fixture(tmp_path / "bad_utf8")
    (d / "olist_products_dataset.csv").write_bytes(b"\xff\xfe\x00\x80\x81invalid")
    res = load_olist_dataset(d)
    assert res.ok is False
    assert any(e.filename == "olist_products_dataset.csv" for e in res.errors)


def test_t2_f04_03_malformed_csv_unclosed_quote_returns_parse_error(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = copy_primary_fixture(tmp_path / "malformed")
    (d / "olist_order_items_dataset.csv").write_text(
        'order_id,order_item_id,product_id,price\n"unclosed,1,P1,10.0\n',
        encoding="utf-8",
    )
    res = load_olist_dataset(d)
    assert res.ok is False
    assert any(e.filename == "olist_order_items_dataset.csv" for e in res.errors)


def test_t2_f04_04_leading_zero_numeric_ids_preserved_exact_length(tmp_path: Path) -> None:
    from unidata.loader import load_olist_dataset

    d = write_dataset(
        tmp_path / "lead_zeros",
        orders=[["000123", "000001", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["000123", "01", "000009", "45.00", "5.00"]],
        customers=[["000001", "00000077"]],
        products=[["000009", "cama_mesa_banho"]],
    )
    res = load_olist_dataset(d)
    assert res.ok is True
    assert res.tables["orders"].iloc[0]["order_id"] == "000123"
    assert res.tables["customers"].iloc[0]["customer_unique_id"] == "00000077"
    assert len(res.tables["customers"].iloc[0]["customer_unique_id"]) == 8


def test_t2_f04_05_invalid_timestamps_and_negative_nonnumeric_prices_filtered_in_diagnostics(
    tmp_path: Path,
) -> None:
    from unidata.analytics import compute_kpis

    d = write_dataset(
        tmp_path / "bad_vals",
        orders=[
            ["O1", "C1", "delivered", "2018-05-01 12:00:00"],
            ["O2", "C2", "delivered", "not-a-date"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "10.00"],
            ["O1", "2", "P1", "-10.00", "10.00"],
            ["O1", "3", "P1", "abc", "10.00"],
            ["O2", "1", "P1", "50.00", "10.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    assert prepared.diagnostics.orders_invalid_timestamp == 1
    assert prepared.diagnostics.items_dropped_invalid_price_or_key == 2
    assert compute_kpis(prepared).product_revenue == pytest.approx(100.00)


# ===========================================================================
# F5 — Delivered Order Filtering & Non-Duplicating Relational Joins (5 edge cases)
# ===========================================================================


def test_t2_f05_01_multi_item_multi_payment_stress(tmp_path: Path) -> None:
    d = write_dataset(
        tmp_path / "stress_mp",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[
            ["O1", "1", "P1", "10.00", "5.00"],
            ["O1", "2", "P1", "20.00", "5.00"],
            ["O1", "3", "P1", "30.00", "5.00"],
            ["O1", "4", "P1", "40.00", "5.00"],
        ],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
        payments=[["O1", str(i), "credit_card", "1", "20.00"] for i in range(1, 6)],
    )
    _, prepared = _load_and_prepare(d)
    assert len(prepared.orders_df) == 1
    assert int(prepared.orders_df.iloc[0]["items_count"]) == 4
    assert prepared.orders_df.iloc[0]["order_product_revenue"] == pytest.approx(100.00)
    assert prepared.items_df["price"].sum() == pytest.approx(100.00)


def test_t2_f05_02_duplicate_customer_and_product_lookup_keys_deduplicated(tmp_path: Path) -> None:
    d = write_dataset(
        tmp_path / "dup_lookups",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["O1", "1", "P1", "125.00", "10.00"]],
        customers=[["C1", "U1"], ["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"], ["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    assert prepared.diagnostics.customers_duplicate_keys_dropped == 1
    assert prepared.diagnostics.products_duplicate_keys_dropped == 1
    assert len(prepared.items_df) == 1
    assert prepared.items_df["price"].sum() == pytest.approx(125.00)


def test_t2_f05_03_all_7_non_delivered_olist_statuses_excluded(tmp_path: Path) -> None:
    non_deliv = ["canceled", "unavailable", "invoiced", "processing", "shipped", "created", "approved"]
    orders = [["O_DEL", "C_DEL", "delivered", "2018-05-01 12:00:00"]]
    items = [["O_DEL", "1", "P1", "250.00", "10.00"]]
    custs = [["C_DEL", "U_DEL"]]
    for idx, st in enumerate(non_deliv, start=1):
        orders.append([f"O_{idx}", f"C_{idx}", st, "2018-05-02 12:00:00"])
        items.append([f"O_{idx}", "1", "P1", "999.00", "10.00"])
        custs.append([f"C_{idx}", f"U_{idx}"])
    d = write_dataset(
        tmp_path / "statuses",
        orders=orders,
        order_items=items,
        customers=custs,
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    assert prepared.diagnostics.orders_delivered == 1
    assert prepared.diagnostics.orders_excluded_status == 7
    assert prepared.items_df["price"].sum() == pytest.approx(250.00)


def test_t2_f05_04_orphan_items_and_missing_customer_or_product_handled(tmp_path: Path) -> None:
    d = write_dataset(
        tmp_path / "orphans",
        orders=[
            ["O1", "C1", "delivered", "2018-05-01 12:00:00"],
            ["O_NOCUST", "C_MISSING", "delivered", "2018-05-01 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P_MISSING", "120.00", "10.00"],
            ["O_ORPHAN", "1", "P1", "500.00", "10.00"],
        ],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    assert prepared.diagnostics.orders_missing_customer == 1
    assert prepared.diagnostics.items_missing_product == 1
    assert prepared.items_df["price"].sum() == pytest.approx(120.00)
    assert prepared.items_df.iloc[0]["product_category_name_display"] == "Não informado"


def test_t2_f05_05_leading_zero_ids_preserved_across_all_joins(tmp_path: Path) -> None:
    d = write_dataset(
        tmp_path / "join_zeros",
        orders=[["0009", "0008", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["0009", "0001", "0006", "80.00", "10.00"]],
        customers=[["0008", "0007"]],
        products=[["0006", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    row = prepared.items_df.iloc[0]
    assert row["order_id"] == "0009"
    assert row["customer_id"] == "0008"
    assert row["customer_unique_id"] == "0007"
    assert row["product_id"] == "0006"


# ===========================================================================
# F6 — Safe Caching (5 edge cases)
# ===========================================================================


@pytest.mark.ui
def test_t2_f06_01_cache_recovers_from_missing_files_when_csvs_added(tmp_path: Path) -> None:
    hot_dir = tmp_path / "hot_drop"
    hot_dir.mkdir()
    with launch_streamlit_app(hot_dir) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            txt1 = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in txt1

            copy_primary_fixture(hot_dir)
            page.reload(wait_until="domcontentloaded")
            txt2 = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in txt2


@pytest.mark.ui
def test_t2_f06_02_cache_invalidates_when_optional_translation_added_later(tmp_path: Path) -> None:
    d = build_fix_no_trans(tmp_path / "add_trans")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            txt1 = wait_for_streamlit_ready(page)
            assert "cama_mesa_banho" in txt1

            src_trans = PRIMARY_FIXTURE_DIR / "product_category_name_translation.csv"
            dst_trans = d / "product_category_name_translation.csv"
            dst_trans.write_bytes(src_trans.read_bytes())
            now = time.time() + 5.0
            os.utime(dst_trans, (now, now))

            page.reload(wait_until="domcontentloaded")
            txt2 = wait_for_streamlit_ready(page)
            assert "bed_bath_table" in txt2


@pytest.mark.ui
def test_t2_f06_03_repeated_filter_switches_preserve_deterministic_state() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            initial = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in initial

            apply_temporal_filter(page, "2017")
            apply_temporal_filter(page, "2018")
            txt = click_reset_filter(page)
            assert "10.920,00" in txt


def test_t2_f06_04_large_synthetic_batch_2000_orders_completes_fast(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.segmentation import compute_rfm_and_clusters

    d = build_fix_large_batch(tmp_path / "large_2k", n_orders=2000)
    t0 = time.monotonic()
    _, prepared = _load_and_prepare(d)
    kpis = compute_kpis(prepared)
    _ = compute_monthly_series(prepared)
    _ = compute_category_ranking(prepared)
    seg = compute_rfm_and_clusters(prepared.items_df)
    elapsed = time.monotonic() - t0
    assert kpis.delivered_orders == 2000
    assert seg.ok is True
    assert elapsed < 10.0, f"2000-order batch took too long: {elapsed:.2f}s"


@pytest.mark.ui
def test_t2_f06_05_deleted_csv_mid_session_falls_back_to_onboarding(tmp_path: Path) -> None:
    d = copy_primary_fixture(tmp_path / "del_mid")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            txt1 = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in txt1

            (d / "olist_orders_dataset.csv").unlink()
            page.reload(wait_until="domcontentloaded")
            txt2 = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in txt2
            assert "Traceback" not in txt2


# ===========================================================================
# F7 — Overview KPIs (5 edge cases)
# ===========================================================================


def test_t2_f07_01_zero_delivered_orders_yields_empty_kpi_summary_without_zerodiv(
    tmp_path: Path,
) -> None:
    from unidata.analytics import compute_kpis

    _, prepared = _load_and_prepare(build_fix_no_deliv(tmp_path / "no_deliv_kpi"))
    kpis = compute_kpis(prepared)
    assert kpis.is_empty is True
    assert kpis.product_revenue == 0.0
    assert kpis.delivered_orders == 0
    assert kpis.unique_customers == 0
    assert kpis.avg_ticket == 0.0


def test_t2_f07_02_zero_price_item_counts_order_with_zero_revenue_excluding_freight(
    tmp_path: Path,
) -> None:
    from unidata.analytics import compute_kpis

    d = write_dataset(
        tmp_path / "zero_price",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["O1", "1", "P1", "0.00", "19.90"]],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    kpis = compute_kpis(prepared)
    assert kpis.delivered_orders == 1
    assert kpis.product_revenue == pytest.approx(0.0)
    assert kpis.avg_ticket == pytest.approx(0.0)


def test_t2_f07_03_single_customer_with_5_distinct_customer_ids(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    d = write_dataset(
        tmp_path / "five_cids",
        orders=[[f"O{i}", f"C{i}", "delivered", f"2018-05-0{i} 12:00:00"] for i in range(1, 6)],
        order_items=[[f"O{i}", "1", "P1", "100.00", "10.00"] for i in range(1, 6)],
        customers=[[f"C{i}", "U_ONE"] for i in range(1, 6)],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    kpis = compute_kpis(prepared)
    assert kpis.delivered_orders == 5
    assert kpis.unique_customers == 1
    assert kpis.avg_ticket == pytest.approx(100.00)


def test_t2_f07_04_high_precision_decimal_sums(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis
    from unidata.formatting import format_brl

    d = write_dataset(
        tmp_path / "decimal_sum",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[
            ["O1", "1", "P1", "19.99", "0.00"],
            ["O1", "2", "P1", "29.99", "0.00"],
            ["O1", "3", "P1", "0.02", "0.00"],
        ],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    kpis = compute_kpis(prepared)
    assert kpis.product_revenue == pytest.approx(50.0, abs=1e-6)
    assert normalize_brl_spaces(format_brl(kpis.product_revenue)) == "R$ 50,00"


def test_t2_f07_05_single_order_with_10_items_keeps_order_denominator(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis

    d = write_dataset(
        tmp_path / "ten_items",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["O1", str(i), "P1", "10.00", "2.00"] for i in range(1, 11)],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    kpis = compute_kpis(prepared)
    assert kpis.product_revenue == pytest.approx(100.00)
    assert kpis.delivered_orders == 1
    assert kpis.avg_ticket == pytest.approx(100.00)


# ===========================================================================
# F8 — Monthly Calendar Time Series (5 edge cases)
# ===========================================================================


def test_t2_f08_01_multi_month_gap_does_not_invent_zero_sales(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.analytics import compute_monthly_series

    d = write_dataset(
        tmp_path / "gap_months",
        orders=[
            ["O1", "C1", "delivered", "2017-01-15 12:00:00"],
            ["O2", "C2", "delivered", "2017-06-15 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "5.00"],
            ["O2", "1", "P1", "200.00", "5.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    monthly = compute_monthly_series(prepared)
    observed = monthly.dropna(subset=["product_revenue"])
    assert observed["year_month"].tolist() == ["2017-01", "2017-06"]
    for _, row in monthly.iterrows():
        if row["year_month"] not in {"2017-01", "2017-06"}:
            assert pd.isna(row["product_revenue"])


def test_t2_f08_02_single_month_dataset_handles_yoy_without_error(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.analytics import compute_monthly_series

    d = write_dataset(
        tmp_path / "single_m",
        orders=[["O1", "C1", "delivered", "2018-05-15 12:00:00"]],
        order_items=[["O1", "1", "P1", "150.00", "5.00"]],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    monthly = compute_monthly_series(prepared)
    assert len(monthly) == 1
    assert pd.isna(monthly.iloc[0]["yoy_revenue_pct"])


def test_t2_f08_03_year_boundary_crossing_nye_midnight(tmp_path: Path) -> None:
    from unidata.analytics import compute_monthly_series

    d = write_dataset(
        tmp_path / "nye",
        orders=[
            ["O1", "C1", "delivered", "2017-12-31 23:59:59"],
            ["O2", "C2", "delivered", "2018-01-01 00:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "5.00"],
            ["O2", "1", "P1", "200.00", "5.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    monthly = compute_monthly_series(prepared)
    assert monthly["year_month"].tolist() == ["2017-12", "2018-01"]


def test_t2_f08_04_yoy_comparison_when_prior_year_exists_vs_absent(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.analytics import compute_monthly_series

    d = write_dataset(
        tmp_path / "yoy_mix",
        orders=[
            ["O1", "C1", "delivered", "2017-11-10 12:00:00"],
            ["O2", "C2", "delivered", "2018-11-10 12:00:00"],
            ["O3", "C3", "delivered", "2018-12-10 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "5.00"],
            ["O2", "1", "P1", "150.00", "5.00"],
            ["O3", "1", "P1", "200.00", "5.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"], ["C3", "U3"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    monthly = compute_monthly_series(prepared).set_index("year_month")
    assert float(monthly.loc["2018-11", "yoy_revenue_pct"]) == pytest.approx(50.0, abs=0.1)
    assert pd.isna(monthly.loc["2018-12", "yoy_revenue_pct"])


def test_t2_f08_05_empty_prepared_dataset_returns_empty_monthly_schema(tmp_path: Path) -> None:
    from unidata.analytics import compute_monthly_series

    _, prepared = _load_and_prepare(build_fix_no_deliv(tmp_path / "empty_m"))
    monthly = compute_monthly_series(prepared)
    assert monthly.empty
    assert {"year_month", "product_revenue", "delivered_orders", "avg_ticket"}.issubset(
        set(monthly.columns)
    )


# ===========================================================================
# F9 — Product Category Aggregation & Translation Fallback (5 edge cases)
# ===========================================================================


def test_t2_f09_01_mixed_translated_untranslated_and_null_categories(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking

    d = write_dataset(
        tmp_path / "cat_mix",
        orders=[
            ["O1", "C1", "delivered", "2018-05-01 12:00:00"],
            ["O2", "C2", "delivered", "2018-05-02 12:00:00"],
            ["O3", "C3", "delivered", "2018-05-03 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "5.00"],
            ["O2", "1", "P2", "200.00", "5.00"],
            ["O3", "1", "P3", "300.00", "5.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"], ["C3", "U3"]],
        products=[["P1", "cama_mesa_banho"], ["P2", "slug_sem_traducao"], ["P3", ""]],
        translations=[["cama_mesa_banho", "bed_bath_table"]],
    )
    _, prepared = _load_and_prepare(d)
    cats = set(compute_category_ranking(prepared)["category"])
    assert cats == {"bed_bath_table", "slug_sem_traducao", "Não informado"}


def test_t2_f09_02_all_null_categories_aggregate_under_nao_informado(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking

    d = write_dataset(
        tmp_path / "all_null_cat",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["O1", "1", "P1", "100.00", "5.00"]],
        customers=[["C1", "U1"]],
        products=[["P1", ""]],
    )
    _, prepared = _load_and_prepare(d)
    cats = compute_category_ranking(prepared)
    assert len(cats) == 1
    assert cats.iloc[0]["category"] == "Não informado"
    assert float(cats.iloc[0]["revenue_share_pct"]) == pytest.approx(100.0)


def test_t2_f09_03_very_long_category_name_preserved_and_renders_cleanly(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking

    d = build_fix_bom_long(tmp_path / "long_cat")
    _, prepared = _load_and_prepare(d)
    cats = compute_category_ranking(prepared)
    expected = "eletrodomesticos_de_cozinha_industrial_e_automacao_residencial_premium_linha_completa"
    assert expected in set(cats["category"])


def test_t2_f09_04_tied_revenue_categories_have_deterministic_order(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.analytics import compute_category_ranking

    d = write_dataset(
        tmp_path / "tied_cats",
        orders=[
            ["O1", "C1", "delivered", "2018-05-01 12:00:00"],
            ["O2", "C2", "delivered", "2018-05-02 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "500.00", "5.00"],
            ["O2", "1", "P2", "500.00", "5.00"],
        ],
        customers=[["C1", "U1"], ["C2", "U2"]],
        products=[["P1", "cat_b"], ["P2", "cat_a"]],
    )
    _, prepared = _load_and_prepare(d)
    c1 = compute_category_ranking(prepared)
    c2 = compute_category_ranking(prepared)
    pd.testing.assert_frame_equal(c1, c2)
    assert c1["revenue_share_pct"].sum() == pytest.approx(100.0)


def test_t2_f09_05_orphan_product_id_keeps_revenue_under_nao_informado(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking

    d = write_dataset(
        tmp_path / "orphan_prod",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["O1", "1", "P999", "220.00", "5.00"]],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    assert prepared.diagnostics.items_missing_product == 1
    cats = compute_category_ranking(prepared)
    assert cats.iloc[0]["category"] == "Não informado"
    assert cats.iloc[0]["product_revenue"] == pytest.approx(220.00)


# ===========================================================================
# F10 — RFM Feature Table (5 edge cases)
# ===========================================================================


def test_t2_f10_01_same_customer_buys_twice_same_day(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_table

    d = write_dataset(
        tmp_path / "same_day",
        orders=[
            ["O1", "C1", "delivered", "2018-05-10 12:00:00"],
            ["O2", "C2", "delivered", "2018-05-10 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "100.00", "5.00"],
            ["O2", "1", "P1", "150.00", "5.00"],
        ],
        customers=[["C1", "U_SAME"], ["C2", "U_SAME"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    rfm, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "recency", "frequency", "monetary"}.issubset(set(rfm.columns))
    assert len(rfm) == 1
    assert int(rfm.iloc[0]["frequency"]) == 2
    assert int(rfm.iloc[0]["recency"]) == 0
    assert float(rfm.iloc[0]["monetary"]) == pytest.approx(250.00)


def test_t2_f10_02_customer_with_1_delivered_and_1_canceled_counts_only_delivered(
    tmp_path: Path,
) -> None:
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    rfm, _ = compute_rfm_table(prepared.items_df)
    assert {"customer_unique_id", "frequency", "monetary"}.issubset(set(rfm.columns))
    row = rfm[rfm["customer_unique_id"] == "CUST_U01"].iloc[0]
    # CUST_U01 has 3 delivered orders (1200.00) + 1 canceled (999.00)
    assert int(row["frequency"]) == 3
    assert float(row["monetary"]) == pytest.approx(1200.00)


def test_t2_f10_03_single_customer_single_order(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_table

    d = write_dataset(
        tmp_path / "one_cust",
        orders=[["O1", "C1", "delivered", "2018-05-01 12:00:00"]],
        order_items=[["O1", "1", "P1", "75.00", "5.00"]],
        customers=[["C1", "U1"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    rfm, _ = compute_rfm_table(prepared.items_df)
    assert len(rfm) == 1
    assert int(rfm.iloc[0]["recency"]) == 0
    assert int(rfm.iloc[0]["frequency"]) == 1
    assert float(rfm.iloc[0]["monetary"]) == pytest.approx(75.00)


def test_t2_f10_04_empty_items_df_returns_empty_rfm_and_none_ref_date(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_table

    _, prepared = _load_and_prepare(build_fix_no_deliv(tmp_path / "rfm_empty"))
    rfm, ref_date = compute_rfm_table(prepared.items_df)
    assert rfm.empty
    assert ref_date is None


def test_t2_f10_05_multi_year_gap_between_first_and_last_purchase_uses_max_date(
    tmp_path: Path,
) -> None:
    from unidata.segmentation import compute_rfm_table

    d = write_dataset(
        tmp_path / "gap_400d",
        orders=[
            ["O1", "C1", "delivered", "2017-01-01 12:00:00"],
            ["O2", "C2", "delivered", "2018-02-05 12:00:00"],
        ],
        order_items=[
            ["O1", "1", "P1", "50.00", "5.00"],
            ["O2", "1", "P1", "50.00", "5.00"],
        ],
        customers=[["C1", "U_GAP"], ["C2", "U_GAP"]],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    rfm, ref = compute_rfm_table(prepared.items_df)
    assert int(rfm.iloc[0]["recency"]) == 0
    assert int(rfm.iloc[0]["frequency"]) == 2


# ===========================================================================
# F11 — Reproducible K-means Clustering (5 edge cases)
# ===========================================================================


def test_t2_f11_01_fewer_than_4_unique_customers_fails_cleanly(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(build_fix_small_rfm(tmp_path / "rfm_a", variant="A"))
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is False
    assert seg.customer_count == 3
    assert seg.cluster_summary is None
    assert seg.error_message and len(seg.error_message) > 10


def test_t2_f11_02_fewer_than_4_unique_rfm_points_fails_cleanly(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(build_fix_small_rfm(tmp_path / "rfm_b", variant="B"))
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is False
    assert seg.cluster_summary is None
    assert seg.error_message


def test_t2_f11_03_zero_variance_rfm_across_6_customers_fails_cleanly(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(build_fix_small_rfm(tmp_path / "rfm_c", variant="C"))
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is False
    assert seg.cluster_summary is None
    assert seg.error_message


def test_t2_f11_04_single_dimension_zero_variance_frequency_eq_1(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    # 8 one-time buyers (F=1 constant), varying R & M across 8 distinct points
    d = write_dataset(
        tmp_path / "f_const",
        orders=[[f"O{i}", f"C{i}", "delivered", f"2018-0{i}-01 12:00:00"] for i in range(1, 9)],
        order_items=[[f"O{i}", "1", "P1", f"{i * 50:.2f}", "5.00"] for i in range(1, 9)],
        customers=[[f"C{i}", f"U{i}"] for i in range(1, 9)],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    seg = compute_rfm_and_clusters(prepared.items_df)
    if seg.ok:
        assert seg.cluster_summary is not None
        assert len(seg.cluster_summary) == 4
        assert not seg.cluster_summary.isna().any().any()
    else:
        assert seg.error_message


def test_t2_f11_05_extreme_monetary_outlier_converges_without_nan(tmp_path: Path) -> None:
    from unidata.segmentation import compute_rfm_and_clusters

    prices = [50.0, 60.0, 75.0, 90.0, 110.0, 130.0, 160.0, 100000.0]
    d = write_dataset(
        tmp_path / "outlier",
        orders=[[f"O{i}", f"C{i}", "delivered", f"2018-0{i}-10 12:00:00"] for i in range(1, 9)],
        order_items=[[f"O{i}", "1", "P1", f"{p:.2f}", "5.00"] for i, p in enumerate(prices, start=1)],
        customers=[[f"C{i}", f"U{i}"] for i in range(1, 9)],
        products=[["P1", "cama_mesa_banho"]],
    )
    _, prepared = _load_and_prepare(d)
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is True
    assert len(seg.cluster_summary) == 4
    assert int(seg.cluster_summary["customer_count"].sum()) == 8
    assert not seg.cluster_summary[["median_recency", "median_frequency", "median_monetary"]].isna().any().any()


# ===========================================================================
# F12 — Deterministic Explainable Recommendations (5 edge cases)
# ===========================================================================


def test_t2_f12_01_empty_kpis_returns_empty_recommendations(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(build_fix_no_deliv(tmp_path / "rec_empty"))
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        compute_rfm_and_clusters(prepared.items_df),
        "—",
        "—",
    )
    assert recs == []


def test_t2_f12_02_failed_segmentation_omits_clientes_keeps_valid_categories(
    tmp_path: Path,
) -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(build_fix_small_rfm(tmp_path / "rec_small", variant="A"))
    seg = compute_rfm_and_clusters(prepared.items_df)
    assert seg.ok is False
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        seg,
        "Mai/2018–Jul/2018",
        "Insuficiente",
    )
    assert all(r.category != "Clientes" for r in recs)
    assert any(r.category in {"Sazonalidade", "Produtos"} for r in recs)


def test_t2_f12_03_single_active_month_omits_seasonality_comparison(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series, filter_prepared_data
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    one_month = filter_prepared_data(prepared, start_ym="2017-11", end_ym="2017-11")
    recs = generate_recommendations(
        compute_kpis(one_month),
        compute_monthly_series(one_month),
        compute_category_ranking(one_month),
        compute_rfm_and_clusters(one_month.items_df),
        "Nov/2017",
        "Período filtrado",
    )
    assert all(r.category != "Sazonalidade" for r in recs)


def test_t2_f12_04_leading_category_nao_informado_handled_honestly(tmp_path: Path) -> None:
    from unidata.analytics import compute_category_ranking, compute_kpis, compute_monthly_series
    from unidata.recommendations import generate_recommendations
    from unidata.segmentation import compute_rfm_and_clusters

    d = write_dataset(
        tmp_path / "null_leader",
        orders=[[f"O{i}", f"C{i}", "delivered", f"2018-0{i}-10 12:00:00"] for i in range(1, 6)],
        order_items=[
            ["O1", "1", "P_NULL", "400.00", "5.00"],
            ["O2", "1", "P_NULL", "400.00", "5.00"],
            ["O3", "1", "P_HB", "100.00", "5.00"],
            ["O4", "1", "P_HB", "50.00", "5.00"],
            ["O5", "1", "P_HB", "50.00", "5.00"],
        ],
        customers=[[f"C{i}", f"U{i}"] for i in range(1, 6)],
        products=[["P_NULL", ""], ["P_HB", "beleza_saude"]],
    )
    _, prepared = _load_and_prepare(d)
    recs = generate_recommendations(
        compute_kpis(prepared),
        compute_monthly_series(prepared),
        compute_category_ranking(prepared),
        compute_rfm_and_clusters(prepared.items_df),
        "Jan/2018–Mai/2018",
        "Base completa",
    )
    prod_recs = [r for r in recs if r.category == "Produtos"]
    assert len(prod_recs) >= 1, "Expected at least one Produtos recommendation when 'Não informado' leads"
    txt = f"{prod_recs[0].title} {prod_recs[0].observation} {prod_recs[0].evidence}".lower()
    assert "beleza_saude" in txt or "classific" in txt or "não informado" in txt


def test_t2_f12_05_zero_forbidden_causal_or_predictive_terms_in_recommendations() -> None:
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
    bad_patterns = (
        r"\bprevis[ãa]o\b",
        r"\baumentar[áa]\b",
        r"\bvai aumentar\b",
        r"\bgarantido\b",
        r"\bclientes fi[ée]is\b",
        r"\bmelhor segmento\b",
    )
    for rec in recs:
        combined = f"{rec.title} {rec.observation} {rec.evidence}".lower()
        for pat in bad_patterns:
            assert not re.search(pat, combined), f"Forbidden term matching {pat!r} in {combined!r}"


# ===========================================================================
# F13 — Interactive Temporal Filtering (5 edge cases)
# ===========================================================================


def test_t2_f13_01_empty_filter_window_returns_empty_kpis() -> None:
    from unidata.analytics import compute_kpis, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    empty_slice = filter_prepared_data(prepared, start_ym="2017-02", end_ym="2017-02")
    kpis = compute_kpis(empty_slice)
    assert kpis.is_empty is True
    assert kpis.delivered_orders == 0
    assert kpis.product_revenue == 0.0


def test_t2_f13_02_inverted_range_returns_empty_safely() -> None:
    from unidata.analytics import compute_kpis, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    inverted = filter_prepared_data(prepared, start_ym="2018-11", end_ym="2017-01")
    assert compute_kpis(inverted).is_empty is True


def test_t2_f13_03_filter_bounds_outside_dataset_equivalent_to_full() -> None:
    from unidata.analytics import compute_kpis, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    wide = filter_prepared_data(prepared, start_ym="2015-01", end_ym="2020-12")
    kpis = compute_kpis(wide)
    assert kpis.delivered_orders == 42
    assert kpis.product_revenue == pytest.approx(10920.00)


def test_t2_f13_04_narrow_filter_with_under_4_customers_handles_rfm_honestly() -> None:
    from unidata.analytics import filter_prepared_data
    from unidata.segmentation import compute_rfm_and_clusters

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    # 2017-05 has 4 customers (U19..U22), check narrower subset (<4) via 2017-11 (8) or slice of 2 items
    narrow = filter_prepared_data(prepared, start_ym="2017-05", end_ym="2017-05")
    assert len(narrow.orders_df) == 4
    # Drop to 2 customers to simulate <4 customer window
    tiny_items = narrow.items_df.head(2)
    seg = compute_rfm_and_clusters(tiny_items)
    assert seg.ok is False


def test_t2_f13_05_open_ended_one_sided_filter_works_cleanly() -> None:
    from unidata.analytics import compute_kpis, filter_prepared_data

    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    after_2018 = filter_prepared_data(prepared, start_ym="2018-01", end_ym=None)
    assert compute_kpis(after_2018).delivered_orders == 30
    before_2018 = filter_prepared_data(prepared, start_ym=None, end_ym="2017-12")
    assert compute_kpis(before_2018).delivered_orders == 12


# ===========================================================================
# F14 — Dark REKKI/Operate Streamlit Dashboard (5 edge cases)
# ===========================================================================


@pytest.mark.ui
def test_t2_f14_01_ui_renders_arquivo_ausente_without_traceback(tmp_path: Path) -> None:
    empty = tmp_path / "empty_ui"
    empty.mkdir()
    with launch_streamlit_app(empty) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in text
            assert "olist_order_items_dataset.csv" in text
            assert "Kaggle" in text or "kaggle" in text
            assert "Traceback" not in text
            assert not page_errs


@pytest.mark.ui
def test_t2_f14_02_ui_renders_schema_error_cleanly_on_missing_column(tmp_path: Path) -> None:
    import pandas as pd

    bad = copy_primary_fixture(tmp_path / "bad_col_ui")
    orders_p = bad / "olist_orders_dataset.csv"
    pd.read_csv(orders_p).drop(columns=["order_status"]).to_csv(orders_p, index=False)

    with launch_streamlit_app(bad) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "olist_orders_dataset.csv" in text
            assert "order_status" in text
            assert "Traceback" not in text
            assert not page_errs


@pytest.mark.ui
def test_t2_f14_03_ui_renders_partial_kmeans_failure_keeping_kpis_alive(tmp_path: Path) -> None:
    d = build_fix_small_rfm(tmp_path / "partial_ui", variant="A")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "600,00" in text
            assert "Clientes" in text
            assert "Traceback" not in text
            assert not page_errs


@pytest.mark.ui
def test_t2_f14_04_long_category_labels_do_not_overflow_cards(tmp_path: Path) -> None:
    d = build_fix_bom_long(tmp_path / "long_ui")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page(viewport=(1440, 900)) as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= 1442


@pytest.mark.ui
def test_t2_f14_05_mobile_viewport_390x844_zero_horizontal_overflow() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(390, 844)) as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in text
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= 392, f"Mobile horizontal overflow: {scroll_w}"
            assert not page_errs


# ===========================================================================
# F15 — Accessible Charts, Alternative Tables & Responsiveness (5 edge cases)
# ===========================================================================


@pytest.mark.ui
def test_t2_f15_01_tablet_viewport_768x1024_clean_layout() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(768, 1024)) as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= 770, f"Tablet horizontal overflow: {scroll_w}"
            assert not page_errs


@pytest.mark.ui
def test_t2_f15_02_narrow_viewport_keeps_tables_accessible_without_body_overflow() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(390, 844)) as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            tables = page.locator("table, [data-testid='stDataFrame'], [data-testid='stTable']")
            assert tables.count() >= 1
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 392


@pytest.mark.ui
def test_t2_f15_03_long_category_label_present_untruncated_in_table(tmp_path: Path) -> None:
    d = build_fix_bom_long(tmp_path / "long_tbl")
    expected = "eletrodomesticos_de_cozinha_industrial_e_automacao_residencial_premium_linha_completa"
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page(viewport=(1440, 900)) as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert expected in text


@pytest.mark.ui
def test_t2_f15_04_empty_filter_state_replaces_charts_with_empty_explanation(tmp_path: Path) -> None:
    from unidata.analytics import compute_kpis, compute_monthly_series, filter_prepared_data
    from unidata.loader import load_olist_dataset
    from unidata.pipeline import prepare_data

    prepared = prepare_data(load_olist_dataset(PRIMARY_FIXTURE_DIR).tables)
    empty = filter_prepared_data(prepared, start_ym="2017-02", end_ym="2017-02")
    assert compute_kpis(empty).is_empty is True
    assert compute_monthly_series(empty).empty

    triggered_empty_in_ui = False
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "E-commerce Insights" in text
            # Verify rendered Plotly charts on populated data contain real traces, never blank 0..1 axes
            trace_counts = page.evaluate(
                """() => Array.from(document.querySelectorAll('.js-plotly-plot'))
                    .map(el => (el.data ? el.data.length : 1))"""
            )
            assert all(c >= 1 for c in trace_counts), f"Empty Plotly canvas detected: {trace_counts}"

            if try_select_empty_filter_in_ui(page):
                triggered_empty_in_ui = True
                empty_txt = wait_for_streamlit_ready(page).lower()
                assert any(
                    k in empty_txt for k in ("sem dados", "nenhum", "vazio", "sem cobertura", "0 pedido", "limpar", "voltar")
                ), f"Expected empty-filter explanation in UI, got: {empty_txt[:300]}"
                empty_plots = page.evaluate("() => document.querySelectorAll('.js-plotly-plot').length")
                assert empty_plots == 0, f"Expected 0 Plotly charts during empty filter state, got {empty_plots}"
                assert "Traceback" not in empty_txt
                restored = click_reset_filter(page)
                assert "10.920,00" in restored
            assert not page_errs

    if not triggered_empty_in_ui:
        # Exercise empty-coverage UI state directly via zero-delivered fixture in Playwright
        nd_dir = build_fix_no_deliv(tmp_path / "ui_empty_coverage")
        with launch_streamlit_app(nd_dir) as (url, _):
            with open_playwright_page() as (page, _, page_errs):
                page.goto(url, wait_until="domcontentloaded")
                empty_txt = wait_for_streamlit_ready(page).lower()
                assert any(
                    k in empty_txt for k in ("sem dados", "nenhum", "vazio", "sem cobertura", "entreg", "0 pedido")
                ), f"Expected explicit empty-coverage explanation in UI, got: {empty_txt[:300]}"
                empty_plots = page.evaluate("() => document.querySelectorAll('.js-plotly-plot').length")
                assert empty_plots == 0, f"Expected 0 Plotly charts in empty-coverage state, got {empty_plots}"
                assert "traceback" not in empty_txt
                assert not page_errs


@pytest.mark.ui
def test_t2_f15_05_reduced_motion_preference_respected() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(reduced_motion="reduce") as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            text = normalize_brl_spaces(wait_for_streamlit_ready(page))
            assert "10.920,00" in text
            assert not page_errs


# ===========================================================================
# F16 — Methodology, Provenance & CC BY-NC-SA 4.0 Disclosure (5 edge cases)
# ===========================================================================


@pytest.mark.ui
def test_t2_f16_01_provenance_accessible_during_partial_kmeans_failure(tmp_path: Path) -> None:
    d = build_fix_small_rfm(tmp_path / "prov_small", variant="A")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "CC BY-NC-SA 4.0" in text


@pytest.mark.ui
def test_t2_f16_02_provenance_reachable_without_hover_on_mobile() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page(viewport=(390, 844)) as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "Olist" in text and "CC BY-NC-SA 4.0" in text


@pytest.mark.ui
def test_t2_f16_03_diagnostics_counts_reconcile_delivered_and_excluded() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = normalize_brl_spaces(expand_methodology_section(page))
            lower = text.lower()
            assert any(k in lower for k in ("lido", "entreg", "exclu", "diagnóstic", "qualidade"))
            assert re.search(r"(?<![\d.,])\b46\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b42\b(?![\d.,])", text)
            assert re.search(r"(?<![\d.,])\b4\b(?![\d.,%])", text)


@pytest.mark.ui
def test_t2_f16_04_diagnostics_reflects_translation_absent(tmp_path: Path) -> None:
    d = build_fix_no_trans(tmp_path / "no_trans_diag")
    with launch_streamlit_app(d) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            wait_for_streamlit_ready(page)
            text = expand_methodology_section(page)
            assert "cama_mesa_banho" in text
            assert re.search(
                r"tradu[çc][ãa]o.{0,80}(?:ausente|n[ãa]o\s+carregad|indispon[íi]vel|n[ãa]o\s+encontrad|sem\s+tradu|fallback|portugu[êe]s)"
                r"|(?:ausente|n[ãa]o\s+carregad|sem\s+tradu).{0,60}tradu[çc][ãa]o"
                r"|product_category_name_translation\.csv",
                text,
                re.I | re.S,
            ), "Missing explicit translation-absent diagnostics notice in expanded methodology section"


@pytest.mark.ui
def test_t2_f16_05_never_claims_100k_orders_when_running_on_synthetic_fixture() -> None:
    with launch_streamlit_app(PRIMARY_FIXTURE_DIR) as (url, _):
        with open_playwright_page() as (page, _, _):
            page.goto(url, wait_until="domcontentloaded")
            text = wait_for_streamlit_ready(page)
            assert "100.000 pedidos" not in text.lower()
            assert "42" in text


# ===========================================================================
# F17 — Automated Test Suite on Synthetic Fixtures (5 edge cases)
# ===========================================================================


def test_t2_f17_01_unit_tests_pass_when_workspace_data_dir_is_empty(repo_root: Path) -> None:
    assert list((repo_root / "data").glob("*.csv")) == []
    unit_files = sorted(p for p in (repo_root / "tests").glob("test_*.py"))
    assert unit_files
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *[str(p) for p in unit_files], "-q"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_t2_f17_02_e2e_fixtures_not_mutated_by_helper_calls(tmp_path: Path) -> None:
    before = sorted(p.name for p in PRIMARY_FIXTURE_DIR.iterdir())
    copy_dir = copy_primary_fixture(tmp_path / "copy_only")
    assert sorted(p.name for p in copy_dir.iterdir()) == before
    assert sorted(p.name for p in PRIMARY_FIXTURE_DIR.iterdir()) == before


def test_t2_f17_03_negative_schema_fixtures_report_exact_missing_column(tmp_path: Path) -> None:
    import pandas as pd
    from unidata.loader import load_olist_dataset

    d = copy_primary_fixture(tmp_path / "neg_schema")
    p = d / "olist_order_items_dataset.csv"
    pd.read_csv(p).drop(columns=["price"]).to_csv(p, index=False)
    res = load_olist_dataset(d)
    assert res.ok is False
    assert res.errors and "price" in res.errors[0].missing_columns


def test_t2_f17_04_deterministic_kmeans_and_recs_across_pythonhashseed() -> None:
    script = (
        "import json, sys; from pathlib import Path; "
        "sys.path.insert(0, str(Path('src').resolve())); "
        "from unidata.loader import load_olist_dataset; "
        "from unidata.pipeline import prepare_data; "
        "from unidata.segmentation import compute_rfm_and_clusters; "
        "p = prepare_data(load_olist_dataset(Path('tests/e2e/fixtures/primary')).tables); "
        "s = compute_rfm_and_clusters(p.items_df); "
        "print(json.dumps(s.cluster_summary['cluster_label'].tolist()))"
    )
    outs = []
    for seed in ("0", "999"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout.strip())
    assert outs[0] == outs[1]


def test_t2_f17_05_e2e_headless_pipeline_succeeds_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    from unidata.analytics import compute_kpis
    from unidata.segmentation import compute_rfm_and_clusters

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    _, prepared = _load_and_prepare(PRIMARY_FIXTURE_DIR)
    assert compute_kpis(prepared).delivered_orders == 42
    assert compute_rfm_and_clusters(prepared.items_df).ok is True


# ===========================================================================
# F18 — Detailed "Unidata" README.md (1 always-on synthetic + 4 live m4_deliverable)
# ===========================================================================


def test_t2_f18_01_synthetic_readme_validator_catches_missing_title_and_license(
    tmp_path: Path,
) -> None:
    good = build_synthetic_readme(tmp_path / "README_good.md")
    assert validate_readme_content(good, check_links=False) == []

    bad_title = build_synthetic_readme(tmp_path / "README_no_title.md", include_title=False)
    errs_title = validate_readme_content(bad_title, check_links=False)
    assert any("# Unidata" in e for e in errs_title)

    bad_lic = build_synthetic_readme(tmp_path / "README_no_lic.md", include_license=False)
    errs_lic = validate_readme_content(bad_lic, check_links=False)
    assert any("CC BY-NC-SA" in e for e in errs_lic)

    bad_imp = build_synthetic_readme(tmp_path / "README_false_imp.md", claim_impeccable_executed=True)
    errs_imp = validate_readme_content(bad_imp, check_links=False)
    assert any("Impeccable" in e for e in errs_imp)

    # Paraphrased Impeccable false claims must be caught; negated claims must be allowed
    paraphrase_path = tmp_path / "README_paraphrase_imp.md"
    base_txt = good.read_text(encoding="utf-8")
    paraphrase_path.write_text(
        base_txt + "\nA skill Impeccable foi aplicada com sucesso na interface.\n",
        encoding="utf-8",
    )
    assert any("Impeccable" in e for e in validate_readme_content(paraphrase_path, check_links=False))

    negated_path = tmp_path / "README_negated_imp.md"
    negated_path.write_text(
        base_txt + "\nA skill Impeccable não foi aplicada neste ambiente.\n",
        encoding="utf-8",
    )
    assert validate_readme_content(negated_path, check_links=False) == []

    # Substring traps ("bootloader", "20242", "100") must NOT satisfy word-boundary checks
    tricky_path = tmp_path / "README_substrings.md"
    tricky_txt = (
        base_txt.replace("loader.py", "bootloader.py")
        .replace("random_state=42", "ano=20242")
        .replace("n_init=10", "limite=100")
    )
    tricky_path.write_text(tricky_txt, encoding="utf-8")
    tricky_errs = validate_readme_content(tricky_path, check_links=False)
    assert any("architecture/data flow" in e for e in tricky_errs)
    assert any("RFM/K-means" in e for e in tricky_errs)


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t2_f18_02_live_readme_does_not_falsely_claim_impeccable_executed(repo_root: Path) -> None:
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=False)
    imp_errs = [e for e in errs if "Impeccable" in e or "not found" in e]
    assert not imp_errs, f"Live README Impeccable check failed: {imp_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t2_f18_03_live_readme_contains_zero_broken_relative_links(repo_root: Path) -> None:
    errs = validate_readme_content(repo_root / "README.md", repo_root=repo_root, check_links=True)
    link_errs = [e for e in errs if "broken relative link" in e or "not found" in e]
    assert not link_errs, f"Broken relative links in README.md: {link_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t2_f18_04_live_readme_does_not_claim_100k_local_execution(repo_root: Path) -> None:
    readme = repo_root / "README.md"
    assert readme.is_file(), f"Missing {readme}"
    txt = readme.read_text(encoding="utf-8").lower()
    assert "executamos na base real" not in txt
    assert "synthetic" in txt or "sintétic" in txt or "fixture" in txt


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t2_f18_05_live_readme_valid_utf8_no_replacement_chars(repo_root: Path) -> None:
    readme = repo_root / "README.md"
    assert readme.is_file(), f"Missing {readme}"
    txt = readme.read_text(encoding="utf-8")
    assert "\ufffd" not in txt


# ===========================================================================
# F19 — Project Showcase Presentation (1 always-on synthetic + 4 live m4_deliverable)
# ===========================================================================


def test_t2_f19_01_synthetic_showcase_validator_catches_missing_section_and_brand_leak(
    tmp_path: Path,
) -> None:
    good = build_synthetic_showcase(tmp_path / "pres_good")
    assert validate_showcase_dir(good) == []

    missing_s8 = build_synthetic_showcase(tmp_path / "pres_no_s8", include_section_8=False)
    assert any("Conclusão" in e for e in validate_showcase_dir(missing_s8))

    leak = build_synthetic_showcase(tmp_path / "pres_leak", leak_coxinha=True)
    assert any("Coxinh" in e for e in validate_showcase_dir(leak))

    # Regression test: valid CSS mask-image / HTML id="task-1" must NOT false-positive on "sk-"
    css_safe = build_synthetic_showcase(tmp_path / "pres_css_mask")
    html_p = css_safe / "showcase.html"
    orig_html = html_p.read_text(encoding="utf-8")
    html_p.write_text(
        orig_html.replace(
            "</head>",
            "<style>.card{-webkit-mask-image:linear-gradient(#000,transparent);mask-image:none}</style></head>",
        ).replace("<body>", "<body><div id='task-1' class='desk-grid'></div>"),
        encoding="utf-8",
    )
    assert validate_showcase_dir(css_safe) == []

    # Regression test: realistic sk-proj-... key MUST trigger failure
    leaked_key = build_synthetic_showcase(tmp_path / "pres_secret_key")
    fake_sk = "sk-proj-" + "abcdef1234567890abcd"
    (leaked_key / "showcase.html").write_text(
        orig_html.replace("</body>", f"<!-- {fake_sk} --></body>"),
        encoding="utf-8",
    )
    assert any("forbidden" in e for e in validate_showcase_dir(leaked_key))

    # Branding leak in SOURCES.md and secret leak in presentation/README.md must also be caught
    sources_leak = build_synthetic_showcase(tmp_path / "pres_sources_leak")
    (sources_leak / "SOURCES.md").write_text(
        (sources_leak / "SOURCES.md").read_text(encoding="utf-8") + "\nTemplate Coxinh.IA\n",
        encoding="utf-8",
    )
    assert any("SOURCES.md" in e and "Coxinh" in e for e in validate_showcase_dir(sources_leak))

    readme_secret = build_synthetic_showcase(tmp_path / "pres_readme_secret")
    fake_ghp = "ghp_" + "1234567890abcdefghij1234"
    (readme_secret / "README.md").write_text(f"# Pres\nToken: {fake_ghp}\n", encoding="utf-8")
    assert any("presentation/README.md" in e and "forbidden" in e for e in validate_showcase_dir(readme_secret))


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
@pytest.mark.ui
def test_t2_f19_02_live_showcase_works_offline_without_fatal_errors(repo_root: Path) -> None:
    html_file = repo_root / "presentation" / "showcase.html"
    assert html_file.is_file(), f"Missing {html_file}"
    with open_playwright_page(viewport=(1440, 900), offline=True) as (page, console_errs, page_errs):
        page.goto(html_file.resolve().as_uri(), wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        assert not page_errs, f"Offline showcase page errors: {page_errs}"
        assert len(page.locator("body").inner_text().strip()) > 100


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t2_f19_03_live_showcase_contains_zero_quiz_or_secrets(repo_root: Path) -> None:
    errs = validate_showcase_dir(repo_root / "presentation")
    sec_errs = [e for e in errs if "forbidden" in e or "Missing" in e]
    assert not sec_errs, f"Showcase forbidden content: {sec_errs}"


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
@pytest.mark.ui
def test_t2_f19_04_live_showcase_responsive_at_390_and_768(repo_root: Path) -> None:
    html_file = repo_root / "presentation" / "showcase.html"
    assert html_file.is_file(), f"Missing {html_file}"
    url = html_file.resolve().as_uri()
    for vp in ((390, 844), (768, 1024)):
        with open_playwright_page(viewport=vp) as (page, _, page_errs):
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
            assert scroll_w <= vp[0] + 2, f"Showcase overflow at {vp}: {scroll_w}"
            assert not page_errs


@pytest.mark.m4_deliverable
@pytest.mark.deliverable
def test_t2_f19_05_live_sources_md_records_factual_status_matrix(repo_root: Path) -> None:
    errs = validate_showcase_dir(repo_root / "presentation")
    src_errs = [e for e in errs if "SOURCES.md" in e or "Missing" in e]
    assert not src_errs, f"SOURCES.md errors: {src_errs}"


# ===========================================================================
# F20 — Final .zip Deliverable (3 always-on synthetic + 2 live m6_release_gate)
# ===========================================================================


def test_t2_f20_01_synthetic_zip_audit_catches_leaked_olist_csv(tmp_path: Path) -> None:
    good_zip = build_synthetic_zip(tmp_path / "good.zip")
    assert validate_zip_deliverable(good_zip) == []

    bad_zip = build_synthetic_zip(tmp_path / "leaked_csv.zip", include_olist_csv=True)
    errs = validate_zip_deliverable(bad_zip)
    assert any("olist_orders_dataset.csv" in e for e in errs)


def test_t2_f20_02_synthetic_zip_audit_catches_leaked_venv_or_agents(tmp_path: Path) -> None:
    bad_venv = build_synthetic_zip(tmp_path / "leaked_venv.zip", include_venv=True)
    assert any(".venv/" in e for e in validate_zip_deliverable(bad_venv))

    bad_agents = build_synthetic_zip(tmp_path / "leaked_agents.zip", include_agents=True)
    assert any(".agents/" in e for e in validate_zip_deliverable(bad_agents))


def test_t2_f20_03_synthetic_zip_audit_catches_missing_readme_or_showcase(tmp_path: Path) -> None:
    no_readme = build_synthetic_zip(tmp_path / "no_readme.zip", omit_readme=True)
    assert any("README.md" in e for e in validate_zip_deliverable(no_readme))

    no_show = build_synthetic_zip(tmp_path / "no_show.zip", omit_showcase=True)
    assert any("showcase.html" in e for e in validate_zip_deliverable(no_show))


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t2_f20_04_live_zip_uses_posix_paths_and_no_duplicates(repo_root: Path) -> None:
    errs = validate_zip_deliverable(repo_root / "unidata-ecommerce-insights.zip")
    path_errs = [
        e for e in errs
        if any(k in e for k in ("backslash", "unsafe", "duplicate", "Missing deliverable"))
    ]
    assert not path_errs, f"Zip POSIX/path issues: {path_errs}"


@pytest.mark.m6_release_gate
@pytest.mark.deliverable
def test_t2_f20_05_live_zip_fails_loudly_never_skipped(repo_root: Path, tmp_path: Path) -> None:
    zip_path = repo_root / "unidata-ecommerce-insights.zip"
    assert zip_path.is_file(), f"AssertionError: Missing deliverable {zip_path.name}"

    # Also verify validator fails explicitly on absent zip and test_tier1 has zero pytest.skip
    missing_errs = validate_zip_deliverable(tmp_path / "nonexistent.zip")
    assert missing_errs and "Missing deliverable" in missing_errs[0]
    t1_tree = ast.parse((Path(__file__).resolve().parent / "test_tier1_features.py").read_text(encoding="utf-8"))
    for node in ast.walk(t1_tree):
        if isinstance(node, ast.Attribute) and node.attr == "skip":
            raise AssertionError("pytest.skip bypass found in test_tier1_features.py")
