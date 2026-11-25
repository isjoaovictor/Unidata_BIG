"""Unit and integration tests for unidata.segmentation."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from unidata.config import RFMConfig
from unidata.loader import load_olist_dataset
from unidata.pipeline import prepare_data
from unidata.segmentation import (
    CLUSTER_SUMMARY_COLUMNS,
    RFM_CLUSTERED_COLUMNS,
    RFM_TABLE_COLUMNS,
    SegmentationResult,
    compute_rfm_and_clusters,
    compute_rfm_table,
)


def _make_items_df(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    """Build an items DataFrame from (customer_unique_id, order_id, timestamp, price)."""
    return pd.DataFrame(
        [
            {
                "customer_unique_id": cust_uid,
                "order_id": order_id,
                "order_purchase_timestamp": pd.Timestamp(ts),
                "price": float(price),
            }
            for cust_uid, order_id, ts, price in rows
        ]
    )


def test_compute_rfm_table_standard_olist_customer_unique_id_and_ref_date(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    rfm_df, ref_date = compute_rfm_table(prepared.items_df)

    assert list(rfm_df.columns) == RFM_TABLE_COLUMNS
    assert ref_date == pd.Timestamp("2018-01-25 12:00:00")
    assert list(rfm_df["customer_unique_id"]) == ["U00001", "U00002", "U00003", "U00004"]

    by_cust = rfm_df.set_index("customer_unique_id")
    # U00001 merges customer_ids 000010 & 000011 -> 2 orders, last 2017-11-15 14:30:00 -> 70 days
    assert int(by_cust.loc["U00001", "recency"]) == 70
    assert int(by_cust.loc["U00001", "frequency"]) == 2
    assert float(by_cust.loc["U00001", "monetary"]) == pytest.approx(350.50)

    assert int(by_cust.loc["U00002", "recency"]) == 66
    assert int(by_cust.loc["U00002", "frequency"]) == 1
    assert float(by_cust.loc["U00002", "monetary"]) == pytest.approx(80.00)

    assert int(by_cust.loc["U00003", "recency"]) == 14
    assert int(by_cust.loc["U00003", "frequency"]) == 1
    assert float(by_cust.loc["U00003", "monetary"]) == pytest.approx(420.00)

    assert int(by_cust.loc["U00004", "recency"]) == 0
    assert int(by_cust.loc["U00004", "frequency"]) == 1
    assert float(by_cust.loc["U00004", "monetary"]) == pytest.approx(49.50)


def test_compute_rfm_table_same_day_repeat_purchases() -> None:
    items_df = _make_items_df(
        [
            ("U1", "O1", "2018-05-10 09:00:00", 120.0),
            ("U1", "O1", "2018-05-10 09:00:00", 30.0),
            ("U1", "O2", "2018-05-10 18:00:00", 50.0),
        ]
    )
    rfm_df, ref_date = compute_rfm_table(items_df)

    assert ref_date == pd.Timestamp("2018-05-10 18:00:00")
    assert len(rfm_df) == 1
    assert int(rfm_df.loc[0, "recency"]) == 0
    assert int(rfm_df.loc[0, "frequency"]) == 2
    assert float(rfm_df.loc[0, "monetary"]) == pytest.approx(200.0)


def test_compute_rfm_missing_columns_raises_value_error() -> None:
    bad_df = pd.DataFrame({"customer_unique_id": ["U1"], "price": [10.0]})
    with pytest.raises(ValueError, match="order_id"):
        compute_rfm_table(bad_df)


def test_compute_rfm_and_clusters_empty_delivered_returns_clean_failure(
    empty_delivered_dir: Path,
) -> None:
    prepared = prepare_data(load_olist_dataset(empty_delivered_dir).tables)
    rfm_df, ref_date = compute_rfm_table(prepared.items_df)
    assert rfm_df.empty
    assert list(rfm_df.columns) == RFM_TABLE_COLUMNS
    assert ref_date is None

    seg = compute_rfm_and_clusters(prepared.items_df)
    assert isinstance(seg, SegmentationResult)
    assert seg.ok is False
    assert seg.customer_count == 0
    assert seg.cluster_summary is None
    assert seg.reference_date is None
    assert seg.error_message is not None and len(seg.error_message.strip()) > 0


def test_compute_rfm_and_clusters_standard_olist_and_rich_fixture(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    seg = compute_rfm_and_clusters(prepared.items_df)

    assert seg.ok is True
    assert seg.error_message is None
    assert seg.customer_count == 4
    assert seg.reference_date == pd.Timestamp("2018-01-25 12:00:00")
    assert seg.rfm_df is not None
    assert seg.cluster_summary is not None
    assert list(seg.rfm_df.columns) == RFM_CLUSTERED_COLUMNS
    assert list(seg.cluster_summary.columns) == CLUSTER_SUMMARY_COLUMNS
    assert len(seg.cluster_summary) == 4
    assert int(seg.cluster_summary["customer_count"].sum()) == 4
    assert seg.cluster_summary["customer_pct"].sum() == pytest.approx(100.0)
    assert seg.model_info["n_clusters"] == 4
    assert seg.model_info["random_state"] == 42
    assert seg.model_info["n_init"] == 10
    assert seg.model_info["scaler"] == "StandardScaler"
    assert seg.model_info["log_transform_frequency"] is True
    assert seg.model_info["log_transform_monetary"] is True
    assert seg.model_info["reference_date"] == pd.Timestamp("2018-01-25 12:00:00")

    # Semantic labels must follow Segmento A/B/C/D and avoid misleading hype terms
    labels = seg.cluster_summary["cluster_label"].tolist()
    assert [lbl.split(" — ")[0] for lbl in labels] == [
        "Segmento A",
        "Segmento B",
        "Segmento C",
        "Segmento D",
    ]
    joined_labels = " | ".join(labels).lower()
    for forbidden in ("melhor segmento", "clientes fiéis", "vip", "propensão"):
        assert forbidden not in joined_labels


def test_compute_rfm_and_clusters_reproducible_and_permutation_invariant() -> None:
    items_df = _make_items_df(
        [
            ("U01", "O01", "2018-04-01 10:00:00", 40.0),
            ("U02", "O02", "2018-04-02 10:00:00", 55.0),
            ("U03", "O03", "2018-04-05 10:00:00", 70.0),
            ("U04", "O04", "2018-02-01 10:00:00", 90.0),
            ("U05", "O05", "2018-01-10 10:00:00", 110.0),
            ("U06", "O06", "2018-01-05 10:00:00", 60.0),
            ("U07", "O07", "2018-03-01 10:00:00", 250.0),
            ("U07", "O08", "2018-04-10 10:00:00", 300.0),
            ("U08", "O09", "2018-03-15 10:00:00", 220.0),
            ("U08", "O10", "2018-04-12 10:00:00", 280.0),
            ("U09", "O11", "2018-02-20 10:00:00", 150.0),
            ("U09", "O12", "2018-03-20 10:00:00", 180.0),
            ("U09", "O13", "2018-04-15 10:00:00", 210.0),
            ("U10", "O14", "2018-04-14 10:00:00", 400.0),
            ("U11", "O15", "2018-01-02 10:00:00", 35.0),
            ("U12", "O16", "2018-02-14 10:00:00", 130.0),
        ]
    )

    seg_a = compute_rfm_and_clusters(items_df)
    seg_b = compute_rfm_and_clusters(items_df)
    shuffled = items_df.sample(frac=1.0, random_state=99).reset_index(drop=True)
    seg_shuffled = compute_rfm_and_clusters(shuffled)

    assert seg_a.ok is True
    assert seg_b.ok is True
    assert seg_shuffled.ok is True
    assert seg_a.rfm_df is not None and seg_b.rfm_df is not None and seg_shuffled.rfm_df is not None
    assert seg_a.cluster_summary is not None and seg_b.cluster_summary is not None and seg_shuffled.cluster_summary is not None

    pd.testing.assert_frame_equal(seg_a.rfm_df, seg_b.rfm_df)
    pd.testing.assert_frame_equal(seg_a.cluster_summary, seg_b.cluster_summary)
    pd.testing.assert_frame_equal(seg_a.rfm_df, seg_shuffled.rfm_df)
    pd.testing.assert_frame_equal(seg_a.cluster_summary, seg_shuffled.cluster_summary)

    # Check summary metrics invariants
    assert (seg_a.cluster_summary["median_recency"] >= 0).all()
    assert (seg_a.cluster_summary["median_frequency"] >= 1).all()
    assert (seg_a.cluster_summary["median_monetary"] > 0).all()
    assert (seg_a.cluster_summary["avg_ticket"] > 0).all()


def test_degenerate_guard_insufficient_customers(edge_cases_olist_dir: Path) -> None:
    prepared = prepare_data(load_olist_dataset(edge_cases_olist_dir).tables)
    seg = compute_rfm_and_clusters(prepared.items_df)

    assert seg.ok is False
    assert seg.customer_count == 2
    assert seg.cluster_summary is None
    assert seg.error_message is not None
    assert "clientes" in seg.error_message.lower()


def test_constant_frequency_dimension_converges_and_records_constant_features() -> None:
    # 8 one-time buyers (frequency=1 constant), varying R & M across 8 distinct points
    items_df = _make_items_df(
        [
            (f"U{i}", f"O{i}", f"2018-01-{10 + i:02d} 10:00:00", 50.0 + i * 25.0)
            for i in range(1, 9)
        ]
    )
    seg = compute_rfm_and_clusters(items_df)

    assert seg.ok is True
    assert seg.customer_count == 8
    assert seg.cluster_summary is not None
    assert len(seg.cluster_summary) == 4
    assert int(seg.cluster_summary["customer_count"].sum()) == 8
    assert not seg.cluster_summary.isna().any().any()
    assert seg.model_info["constant_features"] == ["log1p(frequency)"]
    assert not any(
        "recorrência" in lbl.lower()
        for lbl in seg.cluster_summary["cluster_label"].tolist()
    )


def test_degenerate_guard_all_constant_features_and_fewer_distinct_points() -> None:
    # 6 customers with identical (R, F, M)
    identical_df = _make_items_df(
        [(f"U{i}", f"O{i}", "2018-02-01 10:00:00", 100.0) for i in range(1, 7)]
    )
    seg_ident = compute_rfm_and_clusters(identical_df)
    assert seg_ident.ok is False
    assert seg_ident.cluster_summary is None
    assert seg_ident.error_message is not None
    assert "variância nula" in seg_ident.error_message.lower()
    assert seg_ident.model_info["constant_features"] == [
        "recency",
        "log1p(frequency)",
        "log1p(monetary)",
    ]

    # 6 customers with non-zero variance on all 3 axes, but only 2 distinct (R, F, M) vectors
    two_profiles_df = _make_items_df(
        [
            ("U1", "O1a", "2018-01-01 10:00:00", 50.0),
            ("U2", "O2a", "2018-01-01 10:00:00", 50.0),
            ("U3", "O3a", "2018-01-01 10:00:00", 50.0),
            ("U4", "O4a", "2018-02-01 10:00:00", 100.0),
            ("U4", "O4b", "2018-02-01 10:00:00", 100.0),
            ("U5", "O5a", "2018-02-01 10:00:00", 100.0),
            ("U5", "O5b", "2018-02-01 10:00:00", 100.0),
            ("U6", "O6a", "2018-02-01 10:00:00", 100.0),
            ("U6", "O6b", "2018-02-01 10:00:00", 100.0),
        ]
    )
    seg_two = compute_rfm_and_clusters(two_profiles_df)
    assert seg_two.ok is False
    assert seg_two.cluster_summary is None
    assert seg_two.error_message is not None
    assert "distinto" in seg_two.error_message.lower()


def test_extreme_monetary_outlier_and_custom_rfm_config(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)
    items_outlier = prepared.items_df.copy()
    items_outlier.loc[items_outlier["customer_unique_id"] == "U00003", "price"] = 50000.0

    seg_outlier = compute_rfm_and_clusters(items_outlier)
    assert seg_outlier.ok is True
    assert seg_outlier.cluster_summary is not None
    assert seg_outlier.cluster_summary["median_monetary"].notna().all()

    custom_cfg = RFMConfig(
        n_clusters=2,
        random_state=42,
        n_init=10,
        log_transform_frequency=False,
        log_transform_monetary=False,
        min_customers=4,
    )
    seg_custom = compute_rfm_and_clusters(prepared.items_df, config=custom_cfg)
    assert seg_custom.ok is True
    assert seg_custom.cluster_summary is not None
    assert len(seg_custom.cluster_summary) == 2
    assert seg_custom.model_info["log_transform_frequency"] is False
    assert seg_custom.model_info["log_transform_monetary"] is False
    assert seg_custom.model_info["features"] == ["recency", "frequency", "monetary"]


def test_compute_rfm_and_clusters_rejects_bool_and_non_integral_config_params(
    standard_tables: dict[str, pd.DataFrame],
) -> None:
    prepared = prepare_data(standard_tables)

    invalid_configs = [
        RFMConfig(n_clusters=True),  # type: ignore[arg-type]
        RFMConfig(n_clusters=False),  # type: ignore[arg-type]
        RFMConfig(min_customers=True),  # type: ignore[arg-type]
        RFMConfig(n_init=True),  # type: ignore[arg-type]
        RFMConfig(random_state=True),  # type: ignore[arg-type]
        RFMConfig(n_clusters=2.5),  # type: ignore[arg-type]
        RFMConfig(min_customers=4.5),  # type: ignore[arg-type]
        RFMConfig(n_init=10.5),  # type: ignore[arg-type]
        RFMConfig(random_state=1.5),  # type: ignore[arg-type]
        RFMConfig(random_state=-1),
    ]
    for bad_cfg in invalid_configs:
        with pytest.raises(ValueError):
            compute_rfm_and_clusters(prepared.items_df, config=bad_cfg)

    valid_np_none_cfg = RFMConfig(
        n_clusters=np.int64(2),  # type: ignore[arg-type]
        min_customers=np.int64(4),  # type: ignore[arg-type]
        n_init=np.int64(5),  # type: ignore[arg-type]
        random_state=None,  # type: ignore[arg-type]
    )
    seg_none_rs = compute_rfm_and_clusters(prepared.items_df, config=valid_np_none_cfg)
    assert seg_none_rs.ok is True
    assert seg_none_rs.model_info["n_clusters"] == 2
    assert seg_none_rs.model_info["random_state"] is None


def test_segmentation_has_zero_streamlit_imports() -> None:
    src_dir = str(Path(__file__).resolve().parents[1] / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {src_dir!r}); "
                "import unidata.segmentation; "
                "assert 'streamlit' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
