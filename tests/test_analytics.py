"""Unit and integration tests for unidata.analytics."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from unidata.analytics import (
    CATEGORY_RANKING_COLUMNS,
    MONTHLY_SERIES_COLUMNS,
    KPISummary,
    compute_category_ranking,
    compute_kpis,
    compute_monthly_series,
    filter_prepared_data,
)
from unidata.config import UNKNOWN_CATEGORY_LABEL
from unidata.loader import load_olist_dataset
from unidata.pipeline import ITEMS_COLUMNS, ORDERS_COLUMNS, PreparedDataset, prepare_data


def _build_synthetic_prepared(
    rows: list[tuple[str, str, str, str, float, str | None]],
) -> object:
    """Build a PreparedDataset from (order_id, cust_uid, ts, prod_id, price, cat) tuples."""
    orders_seen: dict[str, tuple[str, str]] = {}
    customers_seen: dict[str, str] = {}
    products_seen: dict[str, str | None] = {}
    item_rows = []

    for idx, (order_id, cust_uid, ts, prod_id, price, cat) in enumerate(rows, start=1):
        cust_id = f"CID_{order_id}"
        orders_seen.setdefault(order_id, (cust_id, ts))
        customers_seen.setdefault(cust_id, cust_uid)
        products_seen.setdefault(prod_id, cat)
        item_rows.append(
            {
                "order_id": order_id,
                "order_item_id": str(idx),
                "product_id": prod_id,
                "price": price,
            }
        )

    tables = {
        "orders": pd.DataFrame(
            [
                {
                    "order_id": oid,
                    "customer_id": cid,
                    "order_status": "delivered",
                    "order_purchase_timestamp": ts,
                }
                for oid, (cid, ts) in orders_seen.items()
            ]
        ),
        "order_items": pd.DataFrame(item_rows),
        "customers": pd.DataFrame(
            [
                {"customer_id": cid, "customer_unique_id": cuid}
                for cid, cuid in customers_seen.items()
            ]
        ),
        "products": pd.DataFrame(
            [
                {"product_id": pid, "product_category_name": cat}
                for pid, cat in products_seen.items()
            ]
        ),
    }
    return prepare_data(tables)


def test_compute_kpis_standard_olist_exact_metrics(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    kpis = compute_kpis(prepared)

    assert isinstance(kpis, KPISummary)
    assert kpis.is_empty is False
    assert kpis.product_revenue == pytest.approx(900.00)
    assert kpis.delivered_orders == 5
    assert kpis.unique_customers == 4
    assert kpis.avg_ticket == pytest.approx(180.00)
    assert kpis.period_start == pd.Timestamp("2017-10-05 10:00:00")
    assert kpis.period_end == pd.Timestamp("2018-01-25 12:00:00")


def test_compute_kpis_ignores_order_payments_inflation(
    standard_olist_dir: Path, standard_tables: dict[str, pd.DataFrame]
) -> None:
    payments_df = pd.read_csv(
        standard_olist_dir / "olist_order_payments_dataset.csv",
        encoding="utf-8-sig",
        dtype={"order_id": str},
    )
    prepared = prepare_data({**standard_tables, "order_payments": payments_df})
    kpis = compute_kpis(prepared)

    assert kpis.product_revenue == pytest.approx(900.00)
    assert kpis.avg_ticket == pytest.approx(180.00)


def test_analytics_handles_empty_delivered_dataset_safely(
    empty_delivered_dir: Path,
) -> None:
    load_res = load_olist_dataset(empty_delivered_dir)
    assert load_res.ok is True
    empty_prepared = prepare_data(load_res.tables)

    kpis = compute_kpis(empty_prepared)
    assert kpis == KPISummary(
        product_revenue=0.0,
        delivered_orders=0,
        unique_customers=0,
        avg_ticket=0.0,
        is_empty=True,
        period_start=None,
        period_end=None,
    )

    monthly = compute_monthly_series(empty_prepared)
    assert monthly.empty
    assert list(monthly.columns) == MONTHLY_SERIES_COLUMNS

    cats = compute_category_ranking(empty_prepared)
    assert cats.empty
    assert list(cats.columns) == CATEGORY_RANKING_COLUMNS


def test_compute_kpis_zero_price_delivered_order() -> None:
    prepared = _build_synthetic_prepared(
        [("O1", "U1", "2018-03-10 10:00:00", "P1", 0.0, "livros_tecnicos")]
    )
    kpis = compute_kpis(prepared)

    assert kpis.is_empty is False
    assert kpis.delivered_orders == 1
    assert kpis.unique_customers == 1
    assert kpis.product_revenue == pytest.approx(0.0)
    assert kpis.avg_ticket == pytest.approx(0.0)


def test_compute_monthly_series_chronology_and_gap_honesty(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    kpis = compute_kpis(prepared)
    monthly = compute_monthly_series(prepared)

    assert list(monthly.columns) == MONTHLY_SERIES_COLUMNS
    assert list(monthly["year_month"]) == ["2017-10", "2017-11", "2018-01"]
    assert "2017-12" not in set(monthly["year_month"])
    assert list(monthly["delivered_orders"]) == [1, 2, 2]
    assert monthly["product_revenue"].tolist() == pytest.approx([150.50, 280.00, 469.50])
    assert monthly["avg_ticket"].tolist() == pytest.approx([150.50, 140.00, 234.75])
    assert monthly["product_revenue"].sum() == pytest.approx(kpis.product_revenue)
    assert int(monthly["delivered_orders"].sum()) == kpis.delivered_orders
    assert monthly["yoy_revenue_pct"].isna().all()


def test_compute_monthly_series_exact_calendar_key_yoy_percentage_points() -> None:
    # Include gaps so row offset != 12 months; exact calendar lookup must match 2017-11 -> 2018-11
    prepared = _build_synthetic_prepared(
        [
            ("O1", "U1", "2017-10-10 10:00:00", "P1", 0.0, "cat_a"),
            ("O2", "U2", "2017-11-10 10:00:00", "P1", 100.0, "cat_a"),
            ("O3", "U3", "2018-10-10 10:00:00", "P1", 80.0, "cat_a"),
            ("O4", "U4", "2018-11-10 10:00:00", "P1", 150.0, "cat_a"),
            ("O5", "U5", "2018-12-10 10:00:00", "P1", 200.0, "cat_a"),
        ]
    )
    monthly = compute_monthly_series(prepared).set_index("year_month")

    assert np.isnan(monthly.loc["2017-10", "yoy_revenue_pct"])
    assert np.isnan(monthly.loc["2017-11", "yoy_revenue_pct"])
    # Prior year 2017-10 had 0.0 revenue -> NaN (no ZeroDivisionError / inf)
    assert np.isnan(monthly.loc["2018-10", "yoy_revenue_pct"])
    # 2018-11 vs 2017-11: (150 - 100) / 100 * 100 = 50.0 percentage points
    assert monthly.loc["2018-11", "yoy_revenue_pct"] == pytest.approx(50.0)
    # 2017-12 absent -> NaN
    assert np.isnan(monthly.loc["2018-12", "yoy_revenue_pct"])


def test_compute_category_ranking_translation_and_fallback(
    standard_tables: dict[str, pd.DataFrame],
    no_translation_dir: Path,
) -> None:
    prepared = prepare_data(standard_tables)
    ranking = compute_category_ranking(prepared)

    assert list(ranking.columns) == CATEGORY_RANKING_COLUMNS
    assert list(ranking["category"]) == [
        "sports_leisure",
        "bed_bath_table",
        "pc_gamer",
        UNKNOWN_CATEGORY_LABEL,
    ]
    assert ranking["product_revenue"].tolist() == pytest.approx([420.0, 300.0, 100.0, 80.0])
    assert ranking["revenue_share_pct"].sum() == pytest.approx(100.0)
    assert ranking["revenue_share_pct"].iloc[0] == pytest.approx((420.0 / 900.0) * 100.0)
    # Order 0001004 has 2 items in sports_leisure -> items_count=2, delivered_orders=1
    assert int(ranking.loc[0, "items_count"]) == 2
    assert int(ranking.loc[0, "delivered_orders"]) == 1

    no_trans_prepared = prepare_data(load_olist_dataset(no_translation_dir).tables)
    pt_ranking = compute_category_ranking(no_trans_prepared)
    assert list(pt_ranking["category"]) == [
        "esporte_lazer",
        "cama_mesa_banho",
        "pc_gamer",
        UNKNOWN_CATEGORY_LABEL,
    ]


def test_compute_category_ranking_top_n_preserves_full_share_and_tie_breaks() -> None:
    prepared = _build_synthetic_prepared(
        [
            ("O1", "U1", "2018-01-01 10:00:00", "P1", 100.0, "zeta"),
            ("O2", "U2", "2018-01-02 10:00:00", "P2", 50.0, "alfa"),
            ("O3", "U3", "2018-01-03 10:00:00", "P2", 50.0, "alfa"),
            ("O4", "U4", "2018-01-04 10:00:00", "P3", 100.0, "beta"),
            ("O4", "U4", "2018-01-04 10:00:00", "P3", 0.0, "beta"),
        ]
    )
    # Revenues all 100.0 (33.33% each):
    # alfa: 2 orders, 2 items; beta: 1 order, 2 items; zeta: 1 order, 1 item
    full = compute_category_ranking(prepared)
    assert list(full["category"]) == ["alfa", "beta", "zeta"]
    assert full["revenue_share_pct"].tolist() == pytest.approx([100.0 / 3, 100.0 / 3, 100.0 / 3])

    top2 = compute_category_ranking(prepared, top_n=2)
    assert list(top2["category"]) == ["alfa", "beta"]
    assert top2["revenue_share_pct"].tolist() == pytest.approx([100.0 / 3, 100.0 / 3])

    top0 = compute_category_ranking(prepared, top_n=0)
    assert top0.empty
    assert list(top0.columns) == CATEGORY_RANKING_COLUMNS

    with pytest.raises(ValueError):
        compute_category_ranking(prepared, top_n=-1)
    with pytest.raises(ValueError):
        compute_category_ranking(prepared, top_n=True)  # type: ignore[arg-type]


def test_compute_category_ranking_zero_total_revenue_avoids_nan() -> None:
    prepared = _build_synthetic_prepared(
        [
            ("O1", "U1", "2018-01-01 10:00:00", "P1", 0.0, "cat_a"),
            ("O2", "U2", "2018-01-02 10:00:00", "P2", 0.0, None),
        ]
    )
    ranking = compute_category_ranking(prepared)
    assert list(ranking["category"]) == [UNKNOWN_CATEGORY_LABEL, "cat_a"]
    assert ranking["revenue_share_pct"].tolist() == pytest.approx([0.0, 0.0])


def test_compute_category_ranking_permutation_invariant_on_float64_ulp_ties() -> None:
    # 0.3 + 0.2 + 0.1 == 0.6000000000000001 vs 0.1 + 0.2 + 0.3 == 0.6 in naive float64 sum
    prepared = _build_synthetic_prepared(
        [
            ("O1", "U1", "2018-01-01 10:00:00", "P1", 0.3, "alfa"),
            ("O2", "U2", "2018-01-02 10:00:00", "P1", 0.2, "alfa"),
            ("O3", "U3", "2018-01-03 10:00:00", "P1", 0.1, "alfa"),
            ("O4", "U4", "2018-01-04 10:00:00", "P2", 0.1, "beta"),
            ("O5", "U5", "2018-01-05 10:00:00", "P2", 0.2, "beta"),
            ("O6", "U6", "2018-01-06 10:00:00", "P2", 0.3, "beta"),
        ]
    )
    baseline = compute_category_ranking(prepared)
    assert list(baseline["category"]) == ["alfa", "beta"]

    reordered_a = PreparedDataset(
        items_df=prepared.items_df.iloc[[2, 1, 0, 5, 4, 3]].reset_index(drop=True),
        orders_df=prepared.orders_df,
        diagnostics=prepared.diagnostics,
    )
    reordered_b = PreparedDataset(
        items_df=prepared.items_df.sample(frac=1.0, random_state=17).reset_index(drop=True),
        orders_df=prepared.orders_df,
        diagnostics=prepared.diagnostics,
    )
    pd.testing.assert_frame_equal(compute_category_ranking(reordered_a), baseline)
    pd.testing.assert_frame_equal(compute_category_ranking(reordered_b), baseline)

    # Also ensure beta=[0.3, 0.2, 0.1] vs alfa=[0.1, 0.2, 0.3] still breaks true tie alphabetically
    swapped = _build_synthetic_prepared(
        [
            ("O1", "U1", "2018-01-01 10:00:00", "P1", 0.1, "alfa"),
            ("O2", "U2", "2018-01-02 10:00:00", "P1", 0.2, "alfa"),
            ("O3", "U3", "2018-01-03 10:00:00", "P1", 0.3, "alfa"),
            ("O4", "U4", "2018-01-04 10:00:00", "P2", 0.3, "beta"),
            ("O5", "U5", "2018-01-05 10:00:00", "P2", 0.2, "beta"),
            ("O6", "U6", "2018-01-06 10:00:00", "P2", 0.1, "beta"),
        ]
    )
    assert list(compute_category_ranking(swapped)["category"]) == ["alfa", "beta"]


def test_compute_category_ranking_accepts_numbers_integral_and_rejects_invalid_top_n(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)

    top2_np = compute_category_ranking(prepared, top_n=np.int64(2))  # type: ignore[arg-type]
    assert len(top2_np) == 2
    assert list(top2_np["category"]) == ["sports_leisure", "bed_bath_table"]

    top1_np32 = compute_category_ranking(prepared, top_n=np.int32(1))  # type: ignore[arg-type]
    assert len(top1_np32) == 1

    top0_np = compute_category_ranking(prepared, top_n=np.int64(0))  # type: ignore[arg-type]
    assert top0_np.empty
    assert list(top0_np.columns) == CATEGORY_RANKING_COLUMNS

    for invalid_top_n in (True, False, np.bool_(True), -1, np.int64(-1), 1.5, "2"):
        with pytest.raises(ValueError):
            compute_category_ranking(prepared, top_n=invalid_top_n)  # type: ignore[arg-type]


def test_filter_prepared_data_bounds_immutability_and_diagnostics(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    orig_items = prepared.items_df.copy(deep=True)
    orig_orders = prepared.orders_df.copy(deep=True)
    orig_diag_orders = prepared.diagnostics.orders_delivered
    orig_warnings_len = len(prepared.diagnostics.warnings)

    # Normalization of "" -> None returns full copy
    unbounded = filter_prepared_data(prepared, start_ym="", end_ym="  ")
    pd.testing.assert_frame_equal(unbounded.items_df, prepared.items_df)
    pd.testing.assert_frame_equal(unbounded.orders_df, prepared.orders_df)

    # Single-month slice
    nov = filter_prepared_data(prepared, start_ym="2017-11", end_ym="2017-11")
    nov_kpis = compute_kpis(nov)
    assert nov_kpis.delivered_orders == 2
    assert nov_kpis.product_revenue == pytest.approx(280.00)
    assert nov.diagnostics.orders_delivered == 2
    assert nov.diagnostics.unique_customers_delivered == 2
    assert nov.diagnostics.min_purchase_date == pd.Timestamp("2017-11-15 14:30:00")
    assert nov.diagnostics.max_purchase_date == pd.Timestamp("2017-11-20 09:15:00")

    # Open-ended bounds
    since_jan = filter_prepared_data(prepared, start_ym="2018-01")
    assert list(since_jan.orders_df["year_month"]) == ["2018-01", "2018-01"]
    until_nov = filter_prepared_data(prepared, end_ym="2017-11")
    assert list(until_nov.orders_df["year_month"]) == ["2017-10", "2017-11", "2017-11"]

    # Out-of-bounds empty window preserves schema & timestamp dtype
    gap = filter_prepared_data(prepared, start_ym="2017-12", end_ym="2017-12")
    assert gap.items_df.empty
    assert gap.orders_df.empty
    assert list(gap.items_df.columns) == ITEMS_COLUMNS
    assert list(gap.orders_df.columns) == ORDERS_COLUMNS
    assert gap.items_df["order_purchase_timestamp"].dtype == prepared.items_df["order_purchase_timestamp"].dtype
    assert gap.orders_df["order_purchase_timestamp"].dtype == prepared.orders_df["order_purchase_timestamp"].dtype
    assert gap.diagnostics.orders_delivered == 0
    assert gap.diagnostics.min_purchase_date is None
    assert gap.diagnostics.max_purchase_date is None

    # Inverted range returns empty slice with pt-BR warning
    inverted = filter_prepared_data(prepared, start_ym="2018-01", end_ym="2017-10")
    assert inverted.items_df.empty
    assert inverted.orders_df.empty
    assert any("invertido" in w.lower() for w in inverted.diagnostics.warnings)

    # Original PreparedDataset remained completely untouched
    pd.testing.assert_frame_equal(prepared.items_df, orig_items)
    pd.testing.assert_frame_equal(prepared.orders_df, orig_orders)
    assert prepared.diagnostics.orders_delivered == orig_diag_orders
    assert len(prepared.diagnostics.warnings) == orig_warnings_len


@pytest.mark.parametrize("bad_ym", ["2017-13", "2017-00", "2017/11", "17-11", "abc"])
def test_filter_prepared_data_invalid_ym_raises_value_error(
    standard_tables: dict[str, pd.DataFrame], bad_ym: str
) -> None:
    prepared = prepare_data(standard_tables)
    with pytest.raises(ValueError, match="YYYY-MM"):
        filter_prepared_data(prepared, start_ym=bad_ym)
    with pytest.raises(ValueError, match="YYYY-MM"):
        filter_prepared_data(prepared, end_ym=bad_ym)


def test_analytics_has_zero_streamlit_imports() -> None:
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {src_dir!r}); "
                "import unidata.analytics; "
                "assert 'streamlit' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
