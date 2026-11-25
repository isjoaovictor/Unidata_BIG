"""Headless RFM feature computation and reproducible K-means customer segmentation."""

from __future__ import annotations

from dataclasses import dataclass
import numbers
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from unidata.config import RFMConfig
from unidata.formatting import format_brl, format_int_pt

RFM_TABLE_COLUMNS: list[str] = [
    "customer_unique_id",
    "recency",
    "frequency",
    "monetary",
]

RFM_CLUSTERED_COLUMNS: list[str] = [
    "customer_unique_id",
    "recency",
    "frequency",
    "monetary",
    "cluster_id",
    "cluster_label",
]

CLUSTER_SUMMARY_COLUMNS: list[str] = [
    "cluster_id",
    "cluster_label",
    "profile_description",
    "customer_count",
    "customer_pct",
    "median_recency",
    "median_frequency",
    "median_monetary",
    "avg_ticket",
]

_REQUIRED_RFM_ITEM_COLUMNS: tuple[str, ...] = (
    "customer_unique_id",
    "order_id",
    "order_purchase_timestamp",
    "price",
)


@dataclass
class SegmentationResult:
    """Output container for RFM feature calculation and K-means clustering."""

    ok: bool
    error_message: str | None
    rfm_df: pd.DataFrame | None
    cluster_summary: pd.DataFrame | None
    reference_date: pd.Timestamp | None
    customer_count: int
    model_info: dict[str, Any]


def _empty_rfm_df() -> pd.DataFrame:
    """Return an empty RFM table with canonical columns and dtypes."""
    return pd.DataFrame(
        {
            "customer_unique_id": pd.Series(dtype="string"),
            "recency": pd.Series(dtype="int64"),
            "frequency": pd.Series(dtype="int64"),
            "monetary": pd.Series(dtype="float64"),
        },
        columns=RFM_TABLE_COLUMNS,
    )


def _format_median_pt(value: float) -> str:
    """Format a median count/days value cleanly in pt-BR."""
    if float(value).is_integer():
        return format_int_pt(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def _segment_letter(idx: int) -> str:
    """Return alphabetical segment identifier ('A', 'B', ..., 'AA', ...)."""
    if 0 <= idx < 26:
        return chr(65 + idx)
    return f"S{idx + 1}"


def _build_semantic_label(
    idx: int,
    med_recency: float,
    med_frequency: float,
    med_monetary: float,
    global_med_recency: float,
    global_med_frequency: float,
    global_med_monetary: float,
) -> tuple[str, str]:
    """Build transparent, non-misleading semantic cluster label and profile description."""
    prefix = f"Segmento {_segment_letter(idx)}"

    rec_tag = (
        "compra recente"
        if med_recency <= global_med_recency
        else "compra mais antiga"
    )
    mon_tag = (
        "maior gasto"
        if med_monetary >= global_med_monetary
        else "menor gasto"
    )
    has_higher_freq = med_frequency > max(1.0, global_med_frequency)

    if has_higher_freq:
        cluster_label = f"{prefix} — Maior recorrência, {rec_tag} e {mon_tag}"
    else:
        cluster_label = f"{prefix} — {mon_tag.capitalize()} e {rec_tag}"

    profile_description = (
        f"Recência mediana de {_format_median_pt(med_recency)} dia(s), "
        f"frequência mediana de {_format_median_pt(med_frequency)} pedido(s) "
        f"e gasto mediano de {format_brl(med_monetary)} "
        f"(critério relativo às medianas da base: recência ≤ {_format_median_pt(global_med_recency)} d, "
        f"gasto ≥ {format_brl(global_med_monetary)})."
    )
    return cluster_label, profile_description


def compute_rfm_table(items_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Aggregate per-customer_unique_id Recency, Frequency, and Monetary features."""
    if not isinstance(items_df, pd.DataFrame):
        raise ValueError("O parâmetro 'items_df' deve ser um pandas DataFrame.")

    missing_cols = [
        col for col in _REQUIRED_RFM_ITEM_COLUMNS if col not in items_df.columns
    ]
    if missing_cols:
        raise ValueError(
            "Colunas obrigatórias ausentes em items_df para cálculo de RFM: "
            f"{', '.join(missing_cols)}."
        )

    if items_df.empty:
        return _empty_rfm_df(), None

    cust_series = items_df["customer_unique_id"].astype("string").str.strip()
    cust_series = cust_series.mask(cust_series == "", pd.NA)

    order_series = items_df["order_id"].astype("string").str.strip()
    order_series = order_series.mask(order_series == "", pd.NA)

    ts_raw = items_df["order_purchase_timestamp"]
    if pd.api.types.is_datetime64_any_dtype(ts_raw):
        tz = getattr(ts_raw.dt, "tz", None)
        ts_series = (
            ts_raw.dt.tz_convert("UTC").dt.tz_localize(None)
            if tz is not None
            else ts_raw
        )
    else:
        try:
            ts_parsed = pd.to_datetime(ts_raw, errors="coerce", format="mixed", utc=True)
        except (TypeError, ValueError):
            ts_parsed = pd.to_datetime(ts_raw, errors="coerce", utc=True)
        ts_series = ts_parsed.dt.tz_localize(None)

    price_series = pd.to_numeric(items_df["price"], errors="coerce").astype("float64")

    valid_mask = (
        cust_series.notna()
        & order_series.notna()
        & ts_series.notna()
        & price_series.notna()
        & np.isfinite(price_series)
        & (price_series >= 0.0)
    )
    if not valid_mask.any():
        return _empty_rfm_df(), None

    work = pd.DataFrame(
        {
            "customer_unique_id": cust_series.loc[valid_mask],
            "order_id": order_series.loc[valid_mask],
            "order_purchase_timestamp": ts_series.loc[valid_mask],
            "price": price_series.loc[valid_mask],
        }
    )

    reference_date = pd.Timestamp(work["order_purchase_timestamp"].max())

    grouped = work.groupby("customer_unique_id", as_index=False).agg(
        last_purchase=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary=("price", "sum"),
    )

    grouped["recency"] = (reference_date - grouped["last_purchase"]).dt.days.astype("int64")
    grouped["frequency"] = grouped["frequency"].astype("int64")
    grouped["monetary"] = grouped["monetary"].astype("float64")
    grouped["customer_unique_id"] = grouped["customer_unique_id"].astype("string")

    rfm_df = (
        grouped[RFM_TABLE_COLUMNS]
        .sort_values("customer_unique_id", ascending=True, kind="mergesort")
        .reset_index(drop=True)
    )
    return rfm_df, reference_date


def compute_rfm_and_clusters(
    items_df: pd.DataFrame,
    config: RFMConfig | None = None,
) -> SegmentationResult:
    """Compute RFM features and reproducible K-means clusters with degenerate-input guards."""
    cfg = config if config is not None else RFMConfig()
    if not isinstance(cfg, RFMConfig):
        raise ValueError("O parâmetro 'config' deve ser uma instância de RFMConfig ou None.")

    for field_name in ("n_clusters", "min_customers", "n_init"):
        val = getattr(cfg, field_name)
        if (
            isinstance(val, (bool, np.bool_))
            or not isinstance(val, numbers.Integral)
            or int(val) < 1
        ):
            raise ValueError(
                "Configuração RFM inválida: 'n_clusters', 'min_customers' e 'n_init' "
                "devem ser inteiros >= 1."
            )

    if cfg.random_state is not None:
        if (
            isinstance(cfg.random_state, (bool, np.bool_))
            or not isinstance(cfg.random_state, numbers.Integral)
            or int(cfg.random_state) < 0
        ):
            raise ValueError(
                "Configuração RFM inválida: 'random_state' deve ser um inteiro >= 0 ou None."
            )

    n_clusters = int(cfg.n_clusters)
    min_customers = int(cfg.min_customers)
    n_init = int(cfg.n_init)
    random_state = int(cfg.random_state) if cfg.random_state is not None else None

    feature_names = [
        "recency",
        "log1p(frequency)" if cfg.log_transform_frequency else "frequency",
        "log1p(monetary)" if cfg.log_transform_monetary else "monetary",
    ]
    model_info: dict[str, Any] = {
        "algorithm": "KMeans",
        "n_clusters": n_clusters,
        "random_state": random_state,
        "n_init": n_init,
        "log_transform_frequency": bool(cfg.log_transform_frequency),
        "log_transform_monetary": bool(cfg.log_transform_monetary),
        "scaler": "StandardScaler",
        "min_customers": min_customers,
        "reference_date": None,
        "features": feature_names,
        "constant_features": [],
    }

    rfm_df, reference_date = compute_rfm_table(items_df)
    customer_count = int(len(rfm_df))
    model_info["reference_date"] = reference_date

    if rfm_df.empty or reference_date is None:
        return SegmentationResult(
            ok=False,
            error_message=(
                "Não há clientes com pedidos entregues válidos no recorte para calcular a segmentação RFM."
            ),
            rfm_df=rfm_df,
            cluster_summary=None,
            reference_date=reference_date,
            customer_count=customer_count,
            model_info=model_info,
        )

    min_required = max(min_customers, n_clusters)
    if customer_count < min_required:
        return SegmentationResult(
            ok=False,
            error_message=(
                f"Segmentação RFM indisponível: são necessários pelo menos {min_required} "
                f"clientes únicos para formar {n_clusters} clusters "
                f"(encontrados: {customer_count})."
            ),
            rfm_df=rfm_df,
            cluster_summary=None,
            reference_date=reference_date,
            customer_count=customer_count,
            model_info=model_info,
        )

    r_vals = rfm_df["recency"].to_numpy(dtype="float64")
    f_raw = rfm_df["frequency"].to_numpy(dtype="float64")
    m_raw = rfm_df["monetary"].to_numpy(dtype="float64")
    f_vals = np.log1p(f_raw) if cfg.log_transform_frequency else f_raw
    m_vals = np.log1p(m_raw) if cfg.log_transform_monetary else m_raw

    X = np.column_stack([r_vals, f_vals, m_vals])
    if not np.all(np.isfinite(X)):
        return SegmentationResult(
            ok=False,
            error_message=(
                "Segmentação RFM indisponível: foram encontrados valores não finitos nas métricas RFM."
            ),
            rfm_df=rfm_df,
            cluster_summary=None,
            reference_date=reference_date,
            customer_count=customer_count,
            model_info=model_info,
        )

    col_stds = np.std(X, axis=0)
    zero_var_cols = [
        name for name, std_val in zip(feature_names, col_stds) if np.isclose(std_val, 0.0)
    ]
    model_info["constant_features"] = zero_var_cols
    if len(zero_var_cols) == len(feature_names):
        cols_str = ", ".join(zero_var_cols)
        return SegmentationResult(
            ok=False,
            error_message=(
                "Segmentação RFM indisponível: variância nula detectada em todas as dimensões "
                f"({cols_str}); não é possível segmentar clientes com perfis idênticos."
            ),
            rfm_df=rfm_df,
            cluster_summary=None,
            reference_date=reference_date,
            customer_count=customer_count,
            model_info=model_info,
        )

    distinct_rows = int(np.unique(X, axis=0).shape[0])
    if distinct_rows < n_clusters:
        return SegmentationResult(
            ok=False,
            error_message=(
                f"Segmentação RFM indisponível: há apenas {distinct_rows} perfil(is) RFM "
                f"distinto(s), insuficiente para formar {n_clusters} clusters."
            ),
            rfm_df=rfm_df,
            cluster_summary=None,
            reference_date=reference_date,
            customer_count=customer_count,
            model_info=model_info,
        )

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(
        n_clusters=n_clusters,
        random_state=random_state,
        n_init=n_init,
    )
    raw_labels = kmeans.fit_predict(X_scaled)

    unique_raw_labels = np.unique(raw_labels)
    if len(unique_raw_labels) < n_clusters:
        return SegmentationResult(
            ok=False,
            error_message=(
                f"Segmentação RFM indisponível: o K-means formou apenas {len(unique_raw_labels)} "
                f"cluster(s) distinto(s) para k={n_clusters}."
            ),
            rfm_df=rfm_df,
            cluster_summary=None,
            reference_date=reference_date,
            customer_count=customer_count,
            model_info=model_info,
        )

    global_med_r = float(np.median(r_vals))
    global_med_f = float(np.median(f_raw))
    global_med_m = float(np.median(m_raw))

    raw_stats: list[dict[str, Any]] = []
    for raw_id in unique_raw_labels.tolist():
        mask = raw_labels == raw_id
        sub_r = r_vals[mask]
        sub_f = f_raw[mask]
        sub_m = m_raw[mask]
        sub_z = X_scaled[mask]

        score = float(np.mean(sub_z[:, 1]) + np.mean(sub_z[:, 2]) - np.mean(sub_z[:, 0]))
        med_r = float(np.median(sub_r))
        med_f = float(np.median(sub_f))
        med_m = float(np.median(sub_m))
        count_c = int(np.sum(mask))
        sum_f = float(np.sum(sub_f))
        sum_m = float(np.sum(sub_m))
        avg_ticket = float(sum_m / sum_f) if sum_f > 0.0 else 0.0

        raw_stats.append(
            {
                "raw_id": int(raw_id),
                "score": score,
                "customer_count": count_c,
                "customer_pct": float((count_c / customer_count) * 100.0),
                "median_recency": med_r,
                "median_frequency": med_f,
                "median_monetary": med_m,
                "avg_ticket": avg_ticket,
            }
        )

    raw_stats.sort(
        key=lambda item: (
            -round(item["score"], 9),
            -round(item["median_monetary"], 9),
            -round(item["median_frequency"], 9),
            round(item["median_recency"], 9),
            -item["customer_count"],
            item["raw_id"],
        )
    )

    raw_to_ordered_id: dict[int, int] = {}
    ordered_id_to_label: dict[int, str] = {}
    summary_rows: list[dict[str, Any]] = []

    for ordered_id, item in enumerate(raw_stats):
        raw_id = item["raw_id"]
        raw_to_ordered_id[raw_id] = ordered_id
        label, desc = _build_semantic_label(
            idx=ordered_id,
            med_recency=item["median_recency"],
            med_frequency=item["median_frequency"],
            med_monetary=item["median_monetary"],
            global_med_recency=global_med_r,
            global_med_frequency=global_med_f,
            global_med_monetary=global_med_m,
        )
        ordered_id_to_label[ordered_id] = label
        summary_rows.append(
            {
                "cluster_id": ordered_id,
                "cluster_label": label,
                "profile_description": desc,
                "customer_count": item["customer_count"],
                "customer_pct": item["customer_pct"],
                "median_recency": item["median_recency"],
                "median_frequency": item["median_frequency"],
                "median_monetary": item["median_monetary"],
                "avg_ticket": item["avg_ticket"],
            }
        )

    ordered_ids = np.array([raw_to_ordered_id[int(r)] for r in raw_labels], dtype="int64")
    clustered_rfm = rfm_df.copy()
    clustered_rfm["cluster_id"] = pd.Series(ordered_ids, dtype="int64")
    clustered_rfm["cluster_label"] = pd.Series(
        [ordered_id_to_label[int(cid)] for cid in ordered_ids],
        dtype="string",
    )
    clustered_rfm = clustered_rfm[RFM_CLUSTERED_COLUMNS]

    cluster_summary = pd.DataFrame(summary_rows, columns=CLUSTER_SUMMARY_COLUMNS)
    cluster_summary["cluster_id"] = cluster_summary["cluster_id"].astype("int64")
    cluster_summary["cluster_label"] = cluster_summary["cluster_label"].astype("string")
    cluster_summary["profile_description"] = cluster_summary["profile_description"].astype("string")
    cluster_summary["customer_count"] = cluster_summary["customer_count"].astype("int64")
    cluster_summary["customer_pct"] = cluster_summary["customer_pct"].astype("float64")
    cluster_summary["median_recency"] = cluster_summary["median_recency"].astype("float64")
    cluster_summary["median_frequency"] = cluster_summary["median_frequency"].astype("float64")
    cluster_summary["median_monetary"] = cluster_summary["median_monetary"].astype("float64")
    cluster_summary["avg_ticket"] = cluster_summary["avg_ticket"].astype("float64")

    return SegmentationResult(
        ok=True,
        error_message=None,
        rfm_df=clustered_rfm,
        cluster_summary=cluster_summary,
        reference_date=reference_date,
        customer_count=customer_count,
        model_info=model_info,
    )
