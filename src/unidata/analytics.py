"""Headless temporal filtering, KPIs, monthly series, and category aggregations."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import numbers
import re

import numpy as np
import pandas as pd

from unidata.config import UNKNOWN_CATEGORY_LABEL
from unidata.pipeline import ITEMS_COLUMNS, ORDERS_COLUMNS, PreparedDataset

_YM_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

MONTHLY_SERIES_COLUMNS: list[str] = [
    "year_month",
    "product_revenue",
    "delivered_orders",
    "avg_ticket",
    "yoy_revenue_pct",
]

CATEGORY_RANKING_COLUMNS: list[str] = [
    "category",
    "product_revenue",
    "revenue_share_pct",
    "items_count",
    "delivered_orders",
]


@dataclass(frozen=True)
class KPISummary:
    """Executive KPI summary computed over a PreparedDataset slice."""

    product_revenue: float
    delivered_orders: int
    unique_customers: int
    avg_ticket: float
    is_empty: bool
    period_start: pd.Timestamp | None
    period_end: pd.Timestamp | None


def _normalize_ym_bound(value: str | None, param_name: str) -> str | None:
    """Normalize and validate an optional 'YYYY-MM' filter boundary."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"O parâmetro '{param_name}' deve ser uma string no formato 'YYYY-MM' ou None."
        )
    cleaned = value.strip()
    if not cleaned:
        return None
    if _YM_REGEX.fullmatch(cleaned) is None:
        raise ValueError(
            f"Formato inválido para '{param_name}': '{cleaned}'. Use 'YYYY-MM' (ex.: '2017-11')."
        )
    return cleaned


def _empty_monthly_series_df() -> pd.DataFrame:
    """Return an empty monthly series DataFrame with canonical columns and dtypes."""
    return pd.DataFrame(
        {
            "year_month": pd.Series(dtype="string"),
            "product_revenue": pd.Series(dtype="float64"),
            "delivered_orders": pd.Series(dtype="int64"),
            "avg_ticket": pd.Series(dtype="float64"),
            "yoy_revenue_pct": pd.Series(dtype="float64"),
        },
        columns=MONTHLY_SERIES_COLUMNS,
    )


def _empty_category_ranking_df() -> pd.DataFrame:
    """Return an empty category ranking DataFrame with canonical columns and dtypes."""
    return pd.DataFrame(
        {
            "category": pd.Series(dtype="string"),
            "product_revenue": pd.Series(dtype="float64"),
            "revenue_share_pct": pd.Series(dtype="float64"),
            "items_count": pd.Series(dtype="int64"),
            "delivered_orders": pd.Series(dtype="int64"),
        },
        columns=CATEGORY_RANKING_COLUMNS,
    )


def filter_prepared_data(
    prepared: PreparedDataset,
    start_ym: str | None = None,
    end_ym: str | None = None,
) -> PreparedDataset:
    """Return a non-mutating PreparedDataset filtered inclusively by 'YYYY-MM' bounds."""
    if not isinstance(prepared, PreparedDataset):
        raise ValueError("O parâmetro 'prepared' deve ser um PreparedDataset válido.")

    norm_start = _normalize_ym_bound(start_ym, "start_ym")
    norm_end = _normalize_ym_bound(end_ym, "end_ym")

    items_src = prepared.items_df
    orders_src = prepared.orders_df
    warnings = list(prepared.diagnostics.warnings)

    if norm_start is not None and norm_end is not None and norm_start > norm_end:
        filtered_items = items_src.iloc[0:0].copy().reset_index(drop=True)
        filtered_orders = orders_src.iloc[0:0].copy().reset_index(drop=True)
        warnings.append(
            "Intervalo temporal invertido: o mês inicial é posterior ao mês final; nenhum registro retornado."
        )
    else:
        items_ym = items_src["year_month"].astype("string")
        orders_ym = orders_src["year_month"].astype("string")

        items_mask = pd.Series(True, index=items_src.index, dtype=bool)
        orders_mask = pd.Series(True, index=orders_src.index, dtype=bool)

        if norm_start is not None:
            items_mask &= items_ym.ge(norm_start).fillna(False)
            orders_mask &= orders_ym.ge(norm_start).fillna(False)
        if norm_end is not None:
            items_mask &= items_ym.le(norm_end).fillna(False)
            orders_mask &= orders_ym.le(norm_end).fillna(False)

        filtered_items = items_src.loc[items_mask].copy().reset_index(drop=True)
        filtered_orders = orders_src.loc[orders_mask].copy().reset_index(drop=True)

    if list(filtered_items.columns) != ITEMS_COLUMNS and all(
        col in filtered_items.columns for col in ITEMS_COLUMNS
    ):
        filtered_items = filtered_items[ITEMS_COLUMNS]
    if list(filtered_orders.columns) != ORDERS_COLUMNS and all(
        col in filtered_orders.columns for col in ORDERS_COLUMNS
    ):
        filtered_orders = filtered_orders[ORDERS_COLUMNS]

    if filtered_orders.empty:
        orders_delivered = 0
        unique_customers_delivered = 0
        min_purchase_date = None
        max_purchase_date = None
    else:
        orders_delivered = int(filtered_orders["order_id"].nunique())
        unique_customers_delivered = int(filtered_orders["customer_unique_id"].nunique())
        valid_ts = filtered_orders["order_purchase_timestamp"].dropna()
        min_purchase_date = pd.Timestamp(valid_ts.min()) if not valid_ts.empty else None
        max_purchase_date = pd.Timestamp(valid_ts.max()) if not valid_ts.empty else None

    items_missing_category = (
        int(filtered_items["product_category_name"].isna().sum())
        if not filtered_items.empty and "product_category_name" in filtered_items.columns
        else 0
    )

    updated_diagnostics = replace(
        prepared.diagnostics,
        orders_delivered=orders_delivered,
        unique_customers_delivered=unique_customers_delivered,
        items_missing_category=items_missing_category,
        min_purchase_date=min_purchase_date,
        max_purchase_date=max_purchase_date,
        warnings=warnings,
    )

    return PreparedDataset(
        items_df=filtered_items,
        orders_df=filtered_orders,
        diagnostics=updated_diagnostics,
    )


def compute_kpis(prepared: PreparedDataset) -> KPISummary:
    """Compute executive KPIs for product revenue, orders, unique customers, and average ticket."""
    if not isinstance(prepared, PreparedDataset):
        raise ValueError("O parâmetro 'prepared' deve ser um PreparedDataset válido.")

    items_df = prepared.items_df
    orders_df = prepared.orders_df
    if items_df.empty or orders_df.empty:
        return KPISummary(
            product_revenue=0.0,
            delivered_orders=0,
            unique_customers=0,
            avg_ticket=0.0,
            is_empty=True,
            period_start=None,
            period_end=None,
        )

    delivered_orders = int(orders_df["order_id"].nunique())
    if delivered_orders <= 0:
        return KPISummary(
            product_revenue=0.0,
            delivered_orders=0,
            unique_customers=0,
            avg_ticket=0.0,
            is_empty=True,
            period_start=None,
            period_end=None,
        )

    prices = pd.to_numeric(items_df["price"], errors="coerce")
    valid_prices = prices.loc[prices.notna() & np.isfinite(prices)]
    product_revenue = float(valid_prices.sum())
    unique_customers = int(orders_df["customer_unique_id"].nunique())
    avg_ticket = float(product_revenue / delivered_orders) if delivered_orders > 0 else 0.0

    valid_ts = orders_df["order_purchase_timestamp"].dropna()
    period_start = pd.Timestamp(valid_ts.min()) if not valid_ts.empty else None
    period_end = pd.Timestamp(valid_ts.max()) if not valid_ts.empty else None

    return KPISummary(
        product_revenue=product_revenue,
        delivered_orders=delivered_orders,
        unique_customers=unique_customers,
        avg_ticket=avg_ticket,
        is_empty=False,
        period_start=period_start,
        period_end=period_end,
    )


def compute_monthly_series(prepared: PreparedDataset) -> pd.DataFrame:
    """Aggregate monthly revenue, delivered orders, avg ticket, and exact calendar YoY (% pts)."""
    if not isinstance(prepared, PreparedDataset):
        raise ValueError("O parâmetro 'prepared' deve ser um PreparedDataset válido.")

    items_df = prepared.items_df
    orders_df = prepared.orders_df
    if items_df.empty or orders_df.empty:
        return _empty_monthly_series_df()

    work = items_df.loc[:, ["year_month", "order_id", "price"]].copy()
    work["year_month"] = work["year_month"].astype("string").str.strip()
    work["price"] = pd.to_numeric(work["price"], errors="coerce").astype("float64")
    work = work.loc[
        work["year_month"].notna()
        & (work["year_month"] != "")
        & work["order_id"].notna()
        & work["price"].notna()
        & np.isfinite(work["price"])
    ].copy()

    if work.empty:
        return _empty_monthly_series_df()

    monthly = (
        work.groupby("year_month", as_index=False, dropna=True)
        .agg(
            product_revenue=("price", "sum"),
            delivered_orders=("order_id", "nunique"),
        )
        .sort_values("year_month", ascending=True, kind="mergesort")
        .reset_index(drop=True)
    )

    monthly["product_revenue"] = monthly["product_revenue"].astype("float64")
    monthly["delivered_orders"] = monthly["delivered_orders"].astype("int64")
    monthly["avg_ticket"] = np.where(
        monthly["delivered_orders"] > 0,
        monthly["product_revenue"] / monthly["delivered_orders"],
        0.0,
    ).astype("float64")

    rev_by_ym: dict[str, float] = {
        str(ym): float(rev)
        for ym, rev in zip(monthly["year_month"], monthly["product_revenue"])
    }

    yoy_values: list[float] = []
    for ym, curr_rev in zip(monthly["year_month"], monthly["product_revenue"]):
        ym_str = str(ym)
        match = _YM_REGEX.fullmatch(ym_str)
        if match is None or not math.isfinite(float(curr_rev)):
            yoy_values.append(float("nan"))
            continue
        year_int = int(ym_str[:4])
        month_str = ym_str[5:7]
        prev_ym = f"{year_int - 1:04d}-{month_str}"
        prev_rev = rev_by_ym.get(prev_ym)
        if prev_rev is not None and math.isfinite(prev_rev) and prev_rev > 0.0:
            yoy_values.append(((float(curr_rev) - prev_rev) / prev_rev) * 100.0)
        else:
            yoy_values.append(float("nan"))

    monthly["yoy_revenue_pct"] = pd.Series(yoy_values, dtype="float64")
    monthly["year_month"] = monthly["year_month"].astype("string")
    return monthly[MONTHLY_SERIES_COLUMNS]


def compute_category_ranking(
    prepared: PreparedDataset,
    top_n: int | None = None,
) -> pd.DataFrame:
    """Rank product categories by revenue with pre-slice share (% pts) and fallback handling."""
    if not isinstance(prepared, PreparedDataset):
        raise ValueError("O parâmetro 'prepared' deve ser um PreparedDataset válido.")

    top_n_int: int | None = None
    if top_n is not None:
        if (
            isinstance(top_n, (bool, np.bool_))
            or not isinstance(top_n, numbers.Integral)
            or int(top_n) < 0
        ):
            raise ValueError("O parâmetro 'top_n' deve ser um inteiro >= 0 ou None.")
        top_n_int = int(top_n)

    items_df = prepared.items_df
    if items_df.empty or top_n_int == 0:
        return _empty_category_ranking_df()

    selected_cols = ["product_category_name_display", "price", "order_item_id", "order_id"]
    if "product_id" in items_df.columns:
        selected_cols.append("product_id")
    work = items_df.loc[:, selected_cols].copy()
    work["price"] = pd.to_numeric(work["price"], errors="coerce").astype("float64")
    work = work.loc[
        work["price"].notna()
        & np.isfinite(work["price"])
        & work["order_id"].notna()
    ].copy()

    if work.empty:
        return _empty_category_ranking_df()

    cats = work["product_category_name_display"].astype("string").str.strip()
    cats = cats.mask(cats.isna() | (cats == ""), UNKNOWN_CATEGORY_LABEL)
    work["category"] = cats.astype("string")

    pre_sort_cols = [
        col
        for col in ("category", "order_id", "order_item_id", "product_id", "price")
        if col in work.columns
    ]
    work = work.sort_values(by=pre_sort_cols, kind="mergesort").reset_index(drop=True)

    ranking = work.groupby("category", as_index=False, dropna=False).agg(
        product_revenue=("price", math.fsum),
        items_count=("order_item_id", "count"),
        delivered_orders=("order_id", "nunique"),
    )

    ranking["product_revenue"] = ranking["product_revenue"].astype("float64")
    ranking["items_count"] = ranking["items_count"].astype("int64")
    ranking["delivered_orders"] = ranking["delivered_orders"].astype("int64")

    total_revenue = math.fsum(ranking["product_revenue"].tolist())
    if total_revenue > 0.0 and math.isfinite(total_revenue):
        ranking["revenue_share_pct"] = (
            (ranking["product_revenue"] / total_revenue) * 100.0
        ).astype("float64")
    else:
        ranking["revenue_share_pct"] = pd.Series(
            np.zeros(len(ranking), dtype="float64"),
            index=ranking.index,
            dtype="float64",
        )

    ranking = (
        ranking.assign(_rev_sort=ranking["product_revenue"].round(6))
        .sort_values(
            by=["_rev_sort", "delivered_orders", "items_count", "category"],
            ascending=[False, False, False, True],
            kind="mergesort",
        )
        .drop(columns=["_rev_sort"])
        .reset_index(drop=True)
    )

    if top_n_int is not None:
        ranking = ranking.head(top_n_int).reset_index(drop=True)

    ranking["category"] = ranking["category"].astype("string")
    return ranking[CATEGORY_RANKING_COLUMNS]
