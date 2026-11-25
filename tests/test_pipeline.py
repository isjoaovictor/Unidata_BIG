"""Unit and integration tests for unidata.pipeline."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from unidata.loader import load_olist_dataset
from unidata.pipeline import (
    ITEMS_COLUMNS,
    ORDERS_COLUMNS,
    DataDiagnostics,
    PreparedDataset,
    prepare_data,
)


def test_prepare_data_standard_olist_schemas_and_totals(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)

    assert isinstance(prepared, PreparedDataset)
    assert list(prepared.items_df.columns) == ITEMS_COLUMNS
    assert list(prepared.orders_df.columns) == ORDERS_COLUMNS
    assert len(fields(DataDiagnostics)) == 19

    diag = prepared.diagnostics
    assert diag.orders_total_read == 8
    assert diag.orders_delivered == 5
    assert diag.orders_excluded_status == 3
    assert diag.orders_invalid_timestamp == 0
    assert diag.items_total_read == 10
    assert diag.items_in_delivered_orders == 7
    assert diag.items_dropped_invalid_price_or_key == 0
    assert diag.customers_total_read == 6
    assert diag.customers_duplicate_keys_dropped == 0
    assert diag.orders_missing_customer == 0
    assert diag.products_total_read == 4
    assert diag.products_duplicate_keys_dropped == 0
    assert diag.items_missing_product == 0
    assert diag.items_missing_category == 1
    assert diag.translation_loaded is True
    assert diag.unique_customers_delivered == 4
    assert diag.min_purchase_date == pd.Timestamp("2017-10-05 10:00:00")
    assert diag.max_purchase_date == pd.Timestamp("2018-01-25 12:00:00")

    # Revenue excludes freight and non-delivered orders
    assert prepared.items_df["price"].sum() == pytest.approx(900.00)
    assert prepared.orders_df["order_product_revenue"].sum() == pytest.approx(900.00)
    assert prepared.orders_df["order_id"].nunique() == prepared.items_df["order_id"].nunique() == 5
    assert (prepared.orders_df["order_product_revenue"].sum() / diag.orders_delivered) == pytest.approx(180.00)

    # Chronological sorting and year_month format
    assert prepared.orders_df["order_purchase_timestamp"].is_monotonic_increasing
    assert prepared.items_df["order_purchase_timestamp"].is_monotonic_increasing
    assert list(prepared.orders_df["year_month"]) == [
        "2017-10",
        "2017-11",
        "2017-11",
        "2018-01",
        "2018-01",
    ]

    # Per-order revenue & item count verification
    per_order = prepared.orders_df.set_index("order_id")
    assert per_order.loc["0001001", "order_product_revenue"] == pytest.approx(150.50)
    assert per_order.loc["0001001", "items_count"] == 2
    assert per_order.loc["0001004", "order_product_revenue"] == pytest.approx(420.00)
    assert per_order.loc["0001004", "items_count"] == 2

    # Category display fallback: english -> portuguese -> "Não informado"
    cat_revenue = (
        prepared.items_df.groupby("product_category_name_display")["price"].sum().to_dict()
    )
    assert cat_revenue == pytest.approx(
        {
            "sports_leisure": 420.00,
            "bed_bath_table": 300.00,
            "pc_gamer": 100.00,
            "Não informado": 80.00,
        }
    )


def test_order_payments_ignored_even_if_present_in_tables(
    standard_olist_dir: Path, standard_tables: dict[str, pd.DataFrame]
) -> None:
    baseline = prepare_data(standard_tables)

    payments_df = pd.read_csv(
        standard_olist_dir / "olist_order_payments_dataset.csv",
        encoding="utf-8-sig",
        dtype={"order_id": str},
    )
    tables_with_payments = {**standard_tables, "order_payments": payments_df}
    with_payments = prepare_data(tables_with_payments)

    pd.testing.assert_frame_equal(baseline.items_df, with_payments.items_df)
    pd.testing.assert_frame_equal(baseline.orders_df, with_payments.orders_df)
    assert baseline.diagnostics == with_payments.diagnostics


def test_repeated_customer_unique_id_deduplication(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)

    u1_orders = prepared.orders_df.loc[
        prepared.orders_df["customer_unique_id"] == "U00001", "order_id"
    ].tolist()
    assert u1_orders == ["0001001", "0001002"]
    assert prepared.diagnostics.unique_customers_delivered == 4
    assert prepared.orders_df["customer_id"].nunique() == 5


def test_missing_optional_translation_uses_portuguese_slugs(
    no_translation_dir: Path,
) -> None:
    load_res = load_olist_dataset(no_translation_dir)
    assert load_res.ok is True
    prepared = prepare_data(load_res.tables)

    assert prepared.diagnostics.translation_loaded is False
    categories = set(prepared.items_df["product_category_name_display"].tolist())
    assert categories == {"cama_mesa_banho", "pc_gamer", "esporte_lazer", "Não informado"}


def test_edge_cases_dirty_rows_duplicates_and_missing_mappings(
    edge_cases_olist_dir: Path,
) -> None:
    load_res = load_olist_dataset(edge_cases_olist_dir)
    assert load_res.ok is True
    prepared = prepare_data(load_res.tables)
    diag = prepared.diagnostics

    assert diag.orders_total_read == 6
    assert diag.orders_excluded_status == 1
    assert diag.orders_invalid_timestamp == 1
    assert diag.orders_missing_customer == 1
    assert diag.items_total_read == 7
    assert diag.items_in_delivered_orders == 6
    assert diag.items_dropped_invalid_price_or_key == 4
    assert diag.customers_total_read == 5
    assert diag.customers_duplicate_keys_dropped == 2
    assert diag.products_total_read == 2
    assert diag.products_duplicate_keys_dropped == 1
    assert diag.items_missing_product == 1
    assert diag.items_missing_category == 1
    assert diag.translation_loaded is False

    # E005 had 0 valid items, so only E001 and E002 remain in reconciled outputs
    assert diag.orders_delivered == 2
    assert diag.unique_customers_delivered == 2
    assert list(prepared.orders_df["order_id"]) == ["E001", "E002"]
    assert prepared.items_df["price"].sum() == pytest.approx(225.00)
    assert prepared.orders_df["order_product_revenue"].sum() == pytest.approx(225.00)

    # Missing product_id item retained under "Não informado"
    e002_cat = prepared.items_df.loc[
        prepared.items_df["order_id"] == "E002", "product_category_name_display"
    ].iloc[0]
    assert e002_cat == "Não informado"

    joined_warnings = " | ".join(diag.warnings).lower()
    assert "conflitante" in joined_warnings
    assert "sem itens válidos" in joined_warnings
    assert "sem correspondência na tabela de produtos" in joined_warnings


def test_empty_delivered_orders_returns_valid_empty_dataframes(
    empty_delivered_dir: Path,
) -> None:
    load_res = load_olist_dataset(empty_delivered_dir)
    assert load_res.ok is True
    prepared = prepare_data(load_res.tables)

    assert prepared.items_df.empty
    assert prepared.orders_df.empty
    assert list(prepared.items_df.columns) == ITEMS_COLUMNS
    assert list(prepared.orders_df.columns) == ORDERS_COLUMNS
    assert prepared.diagnostics.orders_total_read == 2
    assert prepared.diagnostics.orders_excluded_status == 2
    assert prepared.diagnostics.orders_delivered == 0
    assert prepared.diagnostics.unique_customers_delivered == 0
    assert prepared.diagnostics.min_purchase_date is None
    assert prepared.diagnostics.max_purchase_date is None
    assert len(prepared.diagnostics.warnings) >= 1


def test_empty_prepared_dataset_timestamp_dtype_matches_non_empty(
    empty_delivered_dir: Path,
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    non_empty = prepare_data(standard_tables)
    empty_tables = load_olist_dataset(empty_delivered_dir).tables
    empty = prepare_data(empty_tables)

    assert (
        empty.items_df["order_purchase_timestamp"].dtype
        == non_empty.items_df["order_purchase_timestamp"].dtype
    )
    assert (
        empty.orders_df["order_purchase_timestamp"].dtype
        == non_empty.orders_df["order_purchase_timestamp"].dtype
    )


@pytest.mark.parametrize(
    ("raw_timestamps", "expected_timestamps", "expected_invalid_count"),
    [
        (
            ["2017-11-15T14:30:00Z", "2017-11-16 10:00:00"],
            [pd.Timestamp("2017-11-15 14:30:00"), pd.Timestamp("2017-11-16 10:00:00")],
            0,
        ),
        (
            ["2017-11-16 10:00:00", "2017-11-15T14:30:00Z"],
            [pd.Timestamp("2017-11-15 14:30:00"), pd.Timestamp("2017-11-16 10:00:00")],
            0,
        ),
        (
            ["2017-11-15T14:30:00Z", "2017-11-17T12:00:00-03:00", "not-a-date"],
            [pd.Timestamp("2017-11-15 14:30:00"), pd.Timestamp("2017-11-17 15:00:00")],
            1,
        ),
        (
            pd.Series(
                [
                    pd.Timestamp("2017-11-15T14:30:00Z"),
                    pd.Timestamp("2017-11-16 10:00:00"),
                ],
                dtype=object,
            ),
            [pd.Timestamp("2017-11-15 14:30:00"), pd.Timestamp("2017-11-16 10:00:00")],
            0,
        ),
        (
            pd.date_range("2017-11-15 12:00:00", periods=2, tz="America/Sao_Paulo"),
            [pd.Timestamp("2017-11-15 14:00:00"), pd.Timestamp("2017-11-16 14:00:00")],
            0,
        ),
    ],
)
def test_prepare_data_normalizes_mixed_timezones_without_dropping_valid_rows(
    raw_timestamps: object,
    expected_timestamps: list[pd.Timestamp],
    expected_invalid_count: int,
) -> None:
    ts_list = list(raw_timestamps)  # type: ignore[arg-type]
    n_rows = len(ts_list)
    order_ids = [f"O{i}" for i in range(1, n_rows + 1)]
    cust_ids = [f"C{i}" for i in range(1, n_rows + 1)]
    tables = {
        "orders": pd.DataFrame(
            {
                "order_id": order_ids,
                "customer_id": cust_ids,
                "order_status": ["delivered"] * n_rows,
                "order_purchase_timestamp": raw_timestamps,
            }
        ),
        "order_items": pd.DataFrame(
            {
                "order_id": order_ids,
                "order_item_id": ["1"] * n_rows,
                "product_id": ["P1"] * n_rows,
                "price": [100.0] * n_rows,
            }
        ),
        "customers": pd.DataFrame(
            {
                "customer_id": cust_ids,
                "customer_unique_id": [f"U{i}" for i in range(1, n_rows + 1)],
            }
        ),
        "products": pd.DataFrame(
            {
                "product_id": ["P1"],
                "product_category_name": ["beleza_saude"],
            }
        ),
    }

    prepared = prepare_data(tables)
    assert prepared.diagnostics.orders_invalid_timestamp == expected_invalid_count
    assert prepared.diagnostics.orders_delivered == len(expected_timestamps)
    assert prepared.orders_df["order_purchase_timestamp"].tolist() == expected_timestamps
    assert getattr(prepared.orders_df["order_purchase_timestamp"].dt, "tz", None) is None


def test_missing_required_table_or_column_raises_value_error(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    with pytest.raises(ValueError, match="orders"):
        prepare_data({})

    broken_tables = {**standard_tables}
    broken_tables["order_items"] = broken_tables["order_items"].drop(columns=["price"])
    with pytest.raises(ValueError, match="price"):
        prepare_data(broken_tables)


def test_direct_prepare_data_preserves_numeric_and_leading_zero_ids() -> None:
    tables = {
        "orders": pd.DataFrame(
            {
                "order_id": ["00099", "00100"],
                "customer_id": [1.0, 2.0],
                "order_status": ["delivered", "delivered"],
                "order_purchase_timestamp": [
                    "2018-01-01 10:00:00",
                    "2018-01-02 10:00:00",
                ],
            }
        ),
        "order_items": pd.DataFrame(
            {
                "order_id": ["00099", "00100"],
                "order_item_id": [1, 1],
                "product_id": ["P1", "P2"],
                "price": [50.0, 75.0],
            }
        ),
        "customers": pd.DataFrame(
            {
                "customer_id": [1.0, 2.0],
                "customer_unique_id": ["U1", "U2"],
            }
        ),
        "products": pd.DataFrame(
            {
                "product_id": ["P1", "P2"],
                "product_category_name": ["beleza_saude", None],
            }
        ),
    }

    prepared = prepare_data(tables)
    assert list(prepared.orders_df["order_id"]) == ["00099", "00100"]
    assert list(prepared.orders_df["customer_id"]) == ["1", "2"]
    assert prepared.items_df["price"].sum() == pytest.approx(125.0)


def test_core_pipeline_has_zero_streamlit_imports() -> None:
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {src_dir!r}); "
                "import unidata.config, unidata.formatting, unidata.loader, unidata.pipeline; "
                "assert 'streamlit' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
