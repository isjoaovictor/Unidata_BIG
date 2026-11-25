"""Unit tests for unidata.config, unidata.formatting, and unidata.loader."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from unidata import config
from unidata.formatting import (
    format_brl,
    format_date_pt,
    format_int_pt,
    format_month_pt,
    format_pct_pt,
    format_ratio_pct_pt,
)
from unidata.loader import LoadResult, SchemaError, load_olist_dataset


# ---------------------------------------------------------------------------
# config.py tests
# ---------------------------------------------------------------------------


def test_config_constants_and_rfm_defaults() -> None:
    assert config.DEFAULT_DATA_DIR == config.PROJECT_ROOT / "data"
    assert set(config.REQUIRED_FILES.keys()) == {
        "orders",
        "order_items",
        "customers",
        "products",
    }
    assert config.OPTIONAL_FILES == {
        "category_translation": "product_category_name_translation.csv"
    }
    assert config.OPTIONAL_COLUMNS == {
        "category_translation": (
            "product_category_name",
            "product_category_name_english",
        )
    }
    for key in (*config.REQUIRED_FILES.keys(), *config.OPTIONAL_FILES.keys()):
        assert key in config.REQUIRED_COLUMNS
        assert len(config.REQUIRED_COLUMNS[key]) >= 2

    rfm = config.RFMConfig()
    assert rfm.n_clusters == 4
    assert rfm.random_state == 42
    assert rfm.n_init == 10
    assert rfm.log_transform_frequency is True
    assert rfm.log_transform_monetary is True
    assert rfm.min_customers == 4
    assert config.DELIVERED_STATUS == "delivered"
    assert config.UNKNOWN_CATEGORY_LABEL == "Não informado"
    assert len(config.PT_BR_MONTH_ABBR) == 12


def test_get_data_dir_with_and_without_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("UNIDATA_DATA_DIR", raising=False)
    assert config.get_data_dir() == config.DEFAULT_DATA_DIR

    monkeypatch.setenv("UNIDATA_DATA_DIR", "   ")
    assert config.get_data_dir() == config.DEFAULT_DATA_DIR

    custom_dir = tmp_path / "custom_olist"
    monkeypatch.setenv("UNIDATA_DATA_DIR", f"  {custom_dir}  ")
    assert config.get_data_dir() == custom_dir


# ---------------------------------------------------------------------------
# formatting.py tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1234.56, "R$ 1.234,56"),
        (0, "R$ 0,00"),
        (-0.001, "R$ 0,00"),
        (-1234.5, "-R$ 1.234,50"),
        (Decimal("9876543.21"), "R$ 9.876.543,21"),
        (np.float64(42.5), "R$ 42,50"),
        (None, "—"),
        (float("nan"), "—"),
        (float("inf"), "—"),
        (float("-inf"), "—"),
        (True, "—"),
        (False, "—"),
        ("123.45", "—"),
    ],
)
def test_format_brl_cases(value: object, expected: str) -> None:
    assert format_brl(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (1234, "1.234"),
        (1234567, "1.234.567"),
        (-1234, "-1.234"),
        (99.6, "100"),
        (None, "—"),
        (np.nan, "—"),
        (float("inf"), "—"),
        (True, "—"),
    ],
)
def test_format_int_pt_cases(value: object, expected: str) -> None:
    assert format_int_pt(value) == expected  # type: ignore[arg-type]


def test_format_int_pt_preserves_large_64bit_integer_precision() -> None:
    assert format_int_pt(1234567890123456789) == "1.234.567.890.123.456.789"
    assert format_int_pt(-1234567890123456789) == "-1.234.567.890.123.456.789"
    assert format_int_pt(np.int64(1234567890123456789)) == "1.234.567.890.123.456.789"


def test_format_pct_pt_and_ratio_pct_pt() -> None:
    assert format_pct_pt(12.34) == "12,3%"
    assert format_pct_pt(12.36, decimals=1) == "12,4%"
    assert format_pct_pt(1234.56, decimals=2) == "1.234,56%"
    assert format_pct_pt(-0.01, decimals=1) == "0,0%"
    assert format_pct_pt(-5.25, decimals=1) == "-5,2%"
    assert format_pct_pt(None) == "—"
    assert format_pct_pt(True) == "—"

    assert format_ratio_pct_pt(0.1234) == "12,3%"
    assert format_ratio_pct_pt(1.0, decimals=0) == "100%"
    assert format_ratio_pct_pt(float("nan")) == "—"
    assert format_ratio_pct_pt(False) == "—"


def test_format_date_pt_handles_naive_tz_aware_and_invalid() -> None:
    assert format_date_pt(datetime(2017, 11, 15, 14, 30)) == "15/11/2017"
    assert format_date_pt(date(2018, 1, 5)) == "05/01/2018"
    assert format_date_pt(pd.Timestamp("2017-10-05 10:00:00")) == "05/10/2017"
    tz_ts = pd.Timestamp("2017-10-05 10:00:00", tz=timezone.utc)
    assert format_date_pt(tz_ts) == "05/10/2017"
    assert format_date_pt("2018-02-28") == "28/02/2018"

    assert format_date_pt(None) == "—"
    assert format_date_pt(pd.NaT) == "—"
    assert format_date_pt("invalid-date") == "—"
    assert format_date_pt(True) == "—"
    assert format_date_pt(0) == "—"  # type: ignore[arg-type]


def test_format_month_pt_handles_valid_and_invalid() -> None:
    assert format_month_pt("2017-11") == "Nov/2017"
    assert format_month_pt("2018-01-25") == "Jan/2018"
    assert format_month_pt("2016-09") == "Set/2016"
    assert format_month_pt(pd.Timestamp("2017-05-03")) == "Mai/2017"
    assert format_month_pt(date(2017, 12, 1)) == "Dez/2017"

    assert format_month_pt("2017-13") == "—"
    assert format_month_pt("2017-00") == "—"
    assert format_month_pt("2017-11-99") == "—"
    assert format_month_pt("2017-02-29") == "—"
    assert format_month_pt("2020-02-29") == "Fev/2020"
    assert format_month_pt("Nov/2017") == "—"
    assert format_month_pt(None) == "—"
    assert format_month_pt(pd.NaT) == "—"
    assert format_month_pt(False) == "—"


# ---------------------------------------------------------------------------
# loader.py tests
# ---------------------------------------------------------------------------


def test_load_standard_olist_success(standard_olist_dir: Path) -> None:
    result = load_olist_dataset(standard_olist_dir)

    assert isinstance(result, LoadResult)
    assert result.ok is True
    assert result.data_dir == standard_olist_dir
    assert result.missing_files == []
    assert result.errors == []
    assert result.has_translation is True
    assert result.onboarding_message_pt == ""
    assert set(result.tables.keys()) == {
        "orders",
        "order_items",
        "customers",
        "products",
        "category_translation",
    }
    assert "order_payments" not in result.tables


def test_load_olist_dataset_defaults_to_env_override(
    monkeypatch: pytest.MonkeyPatch, standard_olist_dir: Path
) -> None:
    monkeypatch.setenv("UNIDATA_DATA_DIR", str(standard_olist_dir))
    result = load_olist_dataset(None)

    assert result.ok is True
    assert result.data_dir == standard_olist_dir
    assert len(result.tables["orders"]) == 8


def test_utf8_bom_and_leading_zero_ids_preserved(standard_olist_dir: Path) -> None:
    raw_bytes = (standard_olist_dir / "olist_orders_dataset.csv").read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")

    result = load_olist_dataset(standard_olist_dir)
    orders = result.tables["orders"]
    customers = result.tables["customers"]

    assert "order_id" in orders.columns
    assert not any(col.startswith("\ufeff") for col in orders.columns)
    assert orders["order_id"].iloc[0] == "0001001"
    assert isinstance(orders["order_id"].iloc[0], str)
    assert customers["customer_id"].iloc[0] == "000010"
    assert customers["customer_id"].iloc[1] == "000011"
    assert pd.api.types.is_datetime64_any_dtype(orders["order_purchase_timestamp"])
    assert pd.api.types.is_numeric_dtype(result.tables["order_items"]["price"])


def test_missing_optional_translation_still_succeeds(
    no_translation_dir: Path,
) -> None:
    result = load_olist_dataset(no_translation_dir)

    assert result.ok is True
    assert result.has_translation is False
    assert result.missing_files == []
    assert result.errors == []
    assert "category_translation" not in result.tables


def test_missing_directory_and_empty_directory_onboarding(
    tmp_path: Path, missing_all_files_dir: Path
) -> None:
    nonexistent = tmp_path / "does_not_exist"
    for target in (nonexistent, missing_all_files_dir):
        result = load_olist_dataset(target)
        assert result.ok is False
        assert result.tables == {}
        assert result.has_translation is False
        assert set(result.missing_files) == set(config.REQUIRED_FILES.values())
        for expected_filename in config.REQUIRED_FILES.values():
            assert expected_filename in result.onboarding_message_pt
        assert str(target) in result.onboarding_message_pt
        assert "kaggle.com" in result.onboarding_message_pt
        assert "CC BY-NC-SA 4.0" in result.onboarding_message_pt


def test_partial_missing_files_lists_only_absent_required_files(
    partial_missing_files_dir: Path,
) -> None:
    result = load_olist_dataset(partial_missing_files_dir)

    assert result.ok is False
    assert set(result.missing_files) == {
        "olist_order_items_dataset.csv",
        "olist_products_dataset.csv",
    }
    assert "olist_orders_dataset.csv" not in result.missing_files
    assert "olist_customers_dataset.csv" not in result.missing_files
    assert "product_category_name_translation.csv" not in result.missing_files


@pytest.mark.parametrize(
    ("file_key", "missing_col"),
    [
        ("orders", "order_purchase_timestamp"),
        ("order_items", "price"),
        ("customers", "customer_unique_id"),
        ("products", "product_category_name"),
        ("category_translation", "product_category_name_english"),
    ],
)
def test_missing_required_columns_returns_schema_error(
    make_missing_column_dir: object,
    file_key: str,
    missing_col: str,
) -> None:
    target_dir = make_missing_column_dir(file_key, missing_col)  # type: ignore[operator]
    result = load_olist_dataset(target_dir)

    assert result.ok is False
    assert len(result.errors) == 1
    err = result.errors[0]
    assert isinstance(err, SchemaError)
    assert err.file_key == file_key
    assert missing_col in err.missing_columns
    assert missing_col in err.message_pt
    assert err.filename in result.onboarding_message_pt


def test_empty_file_and_invalid_encoding_handled_without_traceback(
    make_corrupted_csv_dir: object,
) -> None:
    empty_dir = make_corrupted_csv_dir("orders", b"")  # type: ignore[operator]
    empty_result = load_olist_dataset(empty_dir)
    assert empty_result.ok is False
    assert len(empty_result.errors) == 1
    assert empty_result.errors[0].file_key == "orders"
    assert "vazio" in empty_result.errors[0].message_pt.lower()

    bad_enc_dir = make_corrupted_csv_dir("customers", b"\xff\xfe\x00\x00invalid")  # type: ignore[operator]
    bad_enc_result = load_olist_dataset(bad_enc_dir)
    assert bad_enc_result.ok is False
    assert len(bad_enc_result.errors) == 1
    assert bad_enc_result.errors[0].file_key == "customers"
    assert "utf-8" in bad_enc_result.errors[0].message_pt.lower()


def test_malformed_csv_and_nan_string_ids_not_turned_into_literal_nan(
    tmp_path: Path, standard_olist_dir: Path
) -> None:
    # Extra unquoted fields trigger ParserError
    target = tmp_path / "malformed"
    target.mkdir()
    for key, fname in config.REQUIRED_FILES.items():
        (target / fname).write_bytes((standard_olist_dir / fname).read_bytes())
    (target / config.REQUIRED_FILES["products"]).write_text(
        "product_id,product_category_name\nP1,cat1\nP2,cat2,extra1,extra2\n",
        encoding="utf-8",
    )
    bad_res = load_olist_dataset(target)
    assert bad_res.ok is False
    assert len(bad_res.errors) == 1
    assert bad_res.errors[0].file_key == "products"

    # Verify null IDs in CSV stay null (never literal "nan")
    null_id_dir = tmp_path / "null_id"
    null_id_dir.mkdir()
    for fname in config.REQUIRED_FILES.values():
        (null_id_dir / fname).write_bytes((standard_olist_dir / fname).read_bytes())
    (null_id_dir / config.REQUIRED_FILES["orders"]).write_text(
        "order_id,customer_id,order_status,order_purchase_timestamp\n"
        "0001,,DELIVERED,2017-10-05T10:00:00+00:00\n",
        encoding="utf-8",
    )
    ok_res = load_olist_dataset(null_id_dir)
    assert ok_res.ok is True
    orders_df = ok_res.tables["orders"]
    assert pd.isna(orders_df["customer_id"].iloc[0])
    assert orders_df["order_status"].iloc[0] == "delivered"
    ts = orders_df["order_purchase_timestamp"].iloc[0]
    assert ts.tzinfo is None


def test_bom_and_whitespace_padded_headers_preserve_string_ids(
    tmp_path: Path, standard_olist_dir: Path
) -> None:
    target = tmp_path / "bom_ws_headers"
    target.mkdir()
    for fname in config.REQUIRED_FILES.values():
        (target / fname).write_bytes((standard_olist_dir / fname).read_bytes())

    (target / config.REQUIRED_FILES["orders"]).write_bytes(
        (
            "\ufeff order_id , customer_id , order_status , order_purchase_timestamp \n"
            "0000123,0000456,delivered,2017-11-15T14:30:00Z\n"
            "1e5,0000456,DELIVERED,2017-11-16 10:00:00\n"
        ).encode("utf-8")
    )
    (target / config.REQUIRED_FILES["order_items"]).write_text(
        " order_id , order_item_id , product_id , price \n"
        "0000123,1,0009,10.50\n"
        "1e5,2,1e4,20.00\n",
        encoding="utf-8",
    )

    res = load_olist_dataset(target)
    assert res.ok is True
    assert res.errors == []
    orders_df = res.tables["orders"]
    items_df = res.tables["order_items"]

    assert orders_df["order_id"].tolist() == ["0000123", "1e5"]
    assert orders_df["customer_id"].tolist() == ["0000456", "0000456"]
    assert items_df["order_id"].tolist() == ["0000123", "1e5"]
    assert items_df["order_item_id"].tolist() == ["1", "2"]
    assert items_df["product_id"].tolist() == ["0009", "1e4"]
    assert items_df["price"].tolist() == pytest.approx([10.50, 20.00])


def test_duplicate_stripped_header_names_return_schema_error(
    tmp_path: Path, standard_olist_dir: Path
) -> None:
    target = tmp_path / "dup_headers"
    target.mkdir()
    for fname in config.REQUIRED_FILES.values():
        (target / fname).write_bytes((standard_olist_dir / fname).read_bytes())

    (target / config.REQUIRED_FILES["orders"]).write_text(
        "order_id, order_id ,customer_id,order_status,order_purchase_timestamp\n"
        "0001,0002,C1,delivered,2017-11-15 10:00:00\n",
        encoding="utf-8",
    )

    res = load_olist_dataset(target)
    assert res.ok is False
    assert len(res.errors) == 1
    err = res.errors[0]
    assert err.file_key == "orders"
    assert err.filename == config.REQUIRED_FILES["orders"]
    assert "order_id" in err.message_pt


@pytest.mark.parametrize(
    ("raw_timestamps", "expected_timestamps"),
    [
        (
            ["2017-11-15T14:30:00Z", "2017-11-16 10:00:00"],
            [pd.Timestamp("2017-11-15 14:30:00"), pd.Timestamp("2017-11-16 10:00:00")],
        ),
        (
            ["2017-11-16 10:00:00", "2017-11-15T14:30:00Z"],
            [pd.Timestamp("2017-11-16 10:00:00"), pd.Timestamp("2017-11-15 14:30:00")],
        ),
        (
            ["2017-11-15T14:30:00Z", "2017-11-17T12:00:00-03:00", "not-a-date"],
            [
                pd.Timestamp("2017-11-15 14:30:00"),
                pd.Timestamp("2017-11-17 15:00:00"),
                pd.NaT,
            ],
        ),
    ],
)
def test_loader_handles_mixed_naive_and_tz_aware_timestamps(
    tmp_path: Path,
    standard_olist_dir: Path,
    raw_timestamps: list[str],
    expected_timestamps: list[pd.Timestamp],
) -> None:
    target = tmp_path / "mixed_ts"
    target.mkdir()
    for fname in config.REQUIRED_FILES.values():
        (target / fname).write_bytes((standard_olist_dir / fname).read_bytes())

    lines = ["order_id,customer_id,order_status,order_purchase_timestamp"]
    for idx, raw_ts in enumerate(raw_timestamps, start=1):
        lines.append(f"O{idx},C1,delivered,{raw_ts}")
    (target / config.REQUIRED_FILES["orders"]).write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    res = load_olist_dataset(target)
    assert res.ok is True
    ts_col = res.tables["orders"]["order_purchase_timestamp"]
    assert pd.api.types.is_datetime64_any_dtype(ts_col)
    assert getattr(ts_col.dt, "tz", None) is None
    for actual, expected in zip(ts_col.tolist(), expected_timestamps, strict=True):
        if pd.isna(expected):
            assert pd.isna(actual)
        else:
            assert actual == expected


def test_loader_and_config_have_zero_streamlit_imports() -> None:
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {src_dir!r}); "
                "import unidata.config, unidata.formatting, unidata.loader; "
                "assert 'streamlit' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
