"""Headless relational preparation pipeline for Olist delivered orders and items."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from unidata.config import (
    DELIVERED_STATUS,
    REQUIRED_COLUMNS,
    UNKNOWN_CATEGORY_LABEL,
)

ITEMS_COLUMNS: list[str] = [
    "order_id",
    "order_item_id",
    "product_id",
    "price",
    "customer_id",
    "customer_unique_id",
    "order_purchase_timestamp",
    "year_month",
    "product_category_name",
    "product_category_name_display",
]

ORDERS_COLUMNS: list[str] = [
    "order_id",
    "customer_id",
    "customer_unique_id",
    "order_purchase_timestamp",
    "year_month",
    "order_product_revenue",
    "items_count",
]

_REQUIRED_INPUT_TABLES: tuple[str, ...] = (
    "orders",
    "order_items",
    "customers",
    "products",
)

_SENTINEL_EMPTY_VALUES = {"", "nan", "none", "<na>", "nat"}
_CANONICAL_TS_DTYPE = pd.to_datetime(["2000-01-01"], errors="coerce").dtype


@dataclass
class DataDiagnostics:
    """Data quality and filtering diagnostics produced by prepare_data."""

    orders_total_read: int
    orders_delivered: int
    orders_excluded_status: int
    orders_invalid_timestamp: int
    items_total_read: int
    items_in_delivered_orders: int
    items_dropped_invalid_price_or_key: int
    customers_total_read: int
    customers_duplicate_keys_dropped: int
    orders_missing_customer: int
    products_total_read: int
    products_duplicate_keys_dropped: int
    items_missing_product: int
    items_missing_category: int
    translation_loaded: bool
    min_purchase_date: pd.Timestamp | None
    max_purchase_date: pd.Timestamp | None
    unique_customers_delivered: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreparedDataset:
    """Normalized, non-duplicated relational dataset ready for downstream analytics."""

    items_df: pd.DataFrame
    orders_df: pd.DataFrame
    diagnostics: DataDiagnostics


def _clean_id_series(series: pd.Series) -> pd.Series:
    """Normalize identifier values to stripped strings while preserving leading zeros and nulls."""
    if series.empty:
        return pd.Series(pd.array([], dtype="string"), index=series.index)

    def _normalize(val: object) -> object:
        if val is None:
            return pd.NA
        try:
            if pd.isna(val):
                return pd.NA
        except (TypeError, ValueError):
            pass

        if isinstance(val, bool):
            return pd.NA
        if isinstance(val, (int, np.integer)):
            return str(int(val))
        if isinstance(val, (float, np.floating)):
            if not np.isfinite(val):
                return pd.NA
            if float(val).is_integer():
                return str(int(val))
            return str(val)

        text = str(val).strip()
        if text.lower() in _SENTINEL_EMPTY_VALUES:
            return pd.NA
        return text

    return pd.Series([_normalize(v) for v in series.tolist()], index=series.index, dtype="string")


def _clean_text_series(series: pd.Series) -> pd.Series:
    """Strip text entries and normalize blank/sentinel values to pd.NA."""
    if series.empty:
        return pd.Series(pd.array([], dtype="string"), index=series.index)

    def _normalize(val: object) -> object:
        if val is None:
            return pd.NA
        try:
            if pd.isna(val):
                return pd.NA
        except (TypeError, ValueError):
            pass
        text = str(val).strip()
        if text.lower() in _SENTINEL_EMPTY_VALUES:
            return pd.NA
        return text

    return pd.Series([_normalize(v) for v in series.tolist()], index=series.index, dtype="string")


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse timestamps to UTC-normalized tz-naive datetime64 safely."""
    if series.empty or series.isna().all():
        return pd.Series(pd.NaT, index=series.index, dtype=_CANONICAL_TS_DTYPE)

    if pd.api.types.is_datetime64_any_dtype(series):
        tz = getattr(series.dt, "tz", None)
        parsed = series.dt.tz_convert("UTC").dt.tz_localize(None) if tz is not None else series
        return parsed.astype(_CANONICAL_TS_DTYPE)

    try:
        parsed_utc = pd.to_datetime(series, errors="coerce", format="mixed", utc=True)
        return parsed_utc.dt.tz_localize(None).astype(_CANONICAL_TS_DTYPE)
    except (TypeError, ValueError):
        def _parse_one(val: object) -> pd.Timestamp:
            if val is None:
                return pd.NaT
            try:
                if pd.isna(val):
                    return pd.NaT
                ts = pd.to_datetime(val, errors="coerce", utc=True)
            except (TypeError, ValueError):
                return pd.NaT
            if pd.isna(ts):
                return pd.NaT
            if getattr(ts, "tzinfo", None) is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            return ts

        return pd.Series(
            [_parse_one(v) for v in series.tolist()],
            index=series.index,
            dtype=_CANONICAL_TS_DTYPE,
        )


def _validate_input_tables(tables: Mapping[str, pd.DataFrame]) -> None:
    """Ensure required tables and columns are present before transforming."""
    if not isinstance(tables, Mapping):
        raise ValueError(
            "O parâmetro 'tables' deve ser um mapeamento de nomes de tabela para DataFrames."
        )

    for table_key in _REQUIRED_INPUT_TABLES:
        if table_key not in tables or tables[table_key] is None:
            raise ValueError(f"Tabela obrigatória ausente: '{table_key}'.")
        df = tables[table_key]
        if not isinstance(df, pd.DataFrame):
            raise ValueError(
                f"A entrada '{table_key}' deve ser um pandas DataFrame."
            )
        missing_cols = [
            col for col in REQUIRED_COLUMNS[table_key] if col not in df.columns
        ]
        if missing_cols:
            raise ValueError(
                f"Colunas obrigatórias ausentes na tabela '{table_key}': "
                f"{', '.join(missing_cols)}."
            )


def _empty_items_df() -> pd.DataFrame:
    """Return an empty items DataFrame with canonical columns and dtypes."""
    return pd.DataFrame(
        {
            "order_id": pd.Series(dtype="string"),
            "order_item_id": pd.Series(dtype="string"),
            "product_id": pd.Series(dtype="string"),
            "price": pd.Series(dtype="float64"),
            "customer_id": pd.Series(dtype="string"),
            "customer_unique_id": pd.Series(dtype="string"),
            "order_purchase_timestamp": pd.Series(dtype=_CANONICAL_TS_DTYPE),
            "year_month": pd.Series(dtype="string"),
            "product_category_name": pd.Series(dtype="string"),
            "product_category_name_display": pd.Series(dtype="string"),
        },
        columns=ITEMS_COLUMNS,
    )


def _empty_orders_df() -> pd.DataFrame:
    """Return an empty orders DataFrame with canonical columns and dtypes."""
    return pd.DataFrame(
        {
            "order_id": pd.Series(dtype="string"),
            "customer_id": pd.Series(dtype="string"),
            "customer_unique_id": pd.Series(dtype="string"),
            "order_purchase_timestamp": pd.Series(dtype=_CANONICAL_TS_DTYPE),
            "year_month": pd.Series(dtype="string"),
            "order_product_revenue": pd.Series(dtype="float64"),
            "items_count": pd.Series(dtype="int64"),
        },
        columns=ORDERS_COLUMNS,
    )


def prepare_data(tables: Mapping[str, pd.DataFrame]) -> PreparedDataset:
    """Filter delivered orders, deduplicate lookups, join safely, and compute diagnostics."""
    _validate_input_tables(tables)
    warnings: list[str] = []

    # 1. Orders: status & timestamp filtering (order_payments is intentionally never used)
    orders = tables["orders"].copy()
    orders_total_read = int(len(orders))
    orders["order_id"] = _clean_id_series(orders["order_id"])
    orders["customer_id"] = _clean_id_series(orders["customer_id"])
    status_norm = _clean_text_series(orders["order_status"]).str.lower()

    delivered_mask = status_norm.eq(DELIVERED_STATUS.lower()).fillna(False)
    orders_excluded_status = int((~delivered_mask).sum())
    orders_del = orders.loc[delivered_mask].copy()

    orders_del["order_purchase_timestamp"] = _parse_timestamps(
        orders_del["order_purchase_timestamp"]
    )
    valid_ts_mask = orders_del["order_purchase_timestamp"].notna()
    orders_invalid_timestamp = int((~valid_ts_mask).sum())
    if orders_invalid_timestamp > 0:
        warnings.append(
            f"{orders_invalid_timestamp} pedido(s) entregue(s) com timestamp inválido foram descartados."
        )
    orders_del = orders_del.loc[valid_ts_mask].copy()

    missing_order_id_mask = orders_del["order_id"].isna()
    if missing_order_id_mask.any():
        dropped_oid = int(missing_order_id_mask.sum())
        warnings.append(
            f"{dropped_oid} pedido(s) entregue(s) sem order_id foram descartados."
        )
        orders_del = orders_del.loc[~missing_order_id_mask].copy()

    if orders_del["order_id"].duplicated().any():
        dup_orders = int(orders_del["order_id"].duplicated(keep="first").sum())
        warnings.append(
            f"Detectados {dup_orders} order_id(s) duplicados em pedidos entregues; mantido o primeiro registro."
        )
        orders_del = orders_del.drop_duplicates(subset=["order_id"], keep="first").copy()

    # 2. Customers deduplication & conflict detection (N:1 onto orders_del)
    customers = tables["customers"].copy()
    customers_total_read = int(len(customers))
    customers["customer_id"] = _clean_id_series(customers["customer_id"])
    customers["customer_unique_id"] = _clean_id_series(customers["customer_unique_id"])

    missing_cust_key_mask = customers["customer_id"].isna()
    if missing_cust_key_mask.any():
        dropped_ckey = int(missing_cust_key_mask.sum())
        warnings.append(
            f"{dropped_ckey} registro(s) de clientes sem customer_id foram ignorados."
        )
        customers = customers.loc[~missing_cust_key_mask].copy()

    customers_duplicate_keys_dropped = int(
        customers.duplicated(subset=["customer_id"], keep="first").sum()
    )
    if customers_duplicate_keys_dropped > 0:
        conflict_counts = customers.groupby("customer_id", dropna=True)[
            "customer_unique_id"
        ].nunique(dropna=True)
        n_conflicts = int((conflict_counts > 1).sum())
        if n_conflicts > 0:
            warnings.append(
                f"Detectados {n_conflicts} customer_id(s) duplicados com customer_unique_id conflitante; mantido o primeiro registro."
            )
        else:
            warnings.append(
                f"Detectados {customers_duplicate_keys_dropped} registro(s) duplicados em customers; mantido o primeiro registro."
            )

    customers_dedup = customers.drop_duplicates(subset=["customer_id"], keep="first")[
        ["customer_id", "customer_unique_id"]
    ]

    orders_del = orders_del.merge(
        customers_dedup,
        on="customer_id",
        how="left",
        validate="many_to_one",
    )

    missing_cust_mask = (
        orders_del["customer_id"].isna() | orders_del["customer_unique_id"].isna()
    )
    orders_missing_customer = int(missing_cust_mask.sum())
    if orders_missing_customer > 0:
        warnings.append(
            f"{orders_missing_customer} pedido(s) entregue(s) sem mapeamento válido para customer_unique_id foram excluídos."
        )
        orders_del = orders_del.loc[~missing_cust_mask].copy()

    # 3. Order items filtering & validation
    items = tables["order_items"].copy()
    items_total_read = int(len(items))
    items["order_id"] = _clean_id_series(items["order_id"])
    items["order_item_id"] = _clean_id_series(items["order_item_id"])
    items["product_id"] = _clean_id_series(items["product_id"])
    items["price"] = pd.to_numeric(items["price"], errors="coerce").astype("float64")

    eligible_order_ids = set(orders_del["order_id"].dropna().tolist())
    in_delivered_mask = items["order_id"].isin(eligible_order_ids)
    items_in_delivered_orders = int(in_delivered_mask.sum())
    items_del = items.loc[in_delivered_mask].copy()

    valid_price = (
        items_del["price"].notna()
        & np.isfinite(items_del["price"])
        & (items_del["price"] >= 0.0)
    )
    valid_keys = (
        items_del["order_id"].notna()
        & items_del["order_item_id"].notna()
        & items_del["product_id"].notna()
    )
    valid_item_mask = valid_price & valid_keys
    items_dropped_invalid_price_or_key = int((~valid_item_mask).sum())
    if items_dropped_invalid_price_or_key > 0:
        warnings.append(
            f"{items_dropped_invalid_price_or_key} item(ns) de pedidos entregues foram descartados por preço inválido ou chave ausente."
        )
        items_del = items_del.loc[valid_item_mask].copy()

    if not items_del.empty and items_del.duplicated(subset=["order_id", "order_item_id"]).any():
        dup_item_keys = int(
            items_del.duplicated(subset=["order_id", "order_item_id"], keep="first").sum()
        )
        warnings.append(
            f"Detectadas {dup_item_keys} ocorrência(s) repetida(s) de (order_id, order_item_id) nos itens entregues; linhas preservadas para auditoria."
        )

    # 4. Products & optional category_translation deduplication (N:1 onto items_del)
    products = tables["products"].copy()
    products_total_read = int(len(products))
    products["product_id"] = _clean_id_series(products["product_id"])
    products["product_category_name"] = _clean_text_series(
        products["product_category_name"]
    )

    missing_prod_key_mask = products["product_id"].isna()
    if missing_prod_key_mask.any():
        dropped_pkey = int(missing_prod_key_mask.sum())
        warnings.append(
            f"{dropped_pkey} registro(s) de produtos sem product_id foram ignorados."
        )
        products = products.loc[~missing_prod_key_mask].copy()

    products_duplicate_keys_dropped = int(
        products.duplicated(subset=["product_id"], keep="first").sum()
    )
    if products_duplicate_keys_dropped > 0:
        prod_conflicts = products.groupby("product_id", dropna=True)[
            "product_category_name"
        ].nunique(dropna=True)
        n_prod_conflicts = int((prod_conflicts > 1).sum())
        if n_prod_conflicts > 0:
            warnings.append(
                f"Detectados {n_prod_conflicts} product_id(s) duplicados com categoria conflitante; mantido o primeiro registro."
            )
        else:
            warnings.append(
                f"Detectados {products_duplicate_keys_dropped} registro(s) duplicados em products; mantido o primeiro registro."
            )

    products_dedup = products.drop_duplicates(subset=["product_id"], keep="first")[
        ["product_id", "product_category_name"]
    ]

    items_del = items_del.merge(
        products_dedup,
        on="product_id",
        how="left",
        validate="many_to_one",
    )

    known_product_ids = set(products_dedup["product_id"].dropna().tolist())
    items_missing_product = int((~items_del["product_id"].isin(known_product_ids)).sum())
    if items_missing_product > 0:
        warnings.append(
            f"{items_missing_product} item(ns) sem correspondência na tabela de produtos foram mantidos com categoria '{UNKNOWN_CATEGORY_LABEL}'."
        )

    translation_loaded = False
    if "category_translation" in tables and tables["category_translation"] is not None:
        trans_raw = tables["category_translation"]
        if not isinstance(trans_raw, pd.DataFrame):
            raise ValueError(
                "A tabela opcional 'category_translation' deve ser um pandas DataFrame."
            )
        missing_trans_cols = [
            col
            for col in REQUIRED_COLUMNS["category_translation"]
            if col not in trans_raw.columns
        ]
        if missing_trans_cols:
            raise ValueError(
                "Colunas obrigatórias ausentes na tabela 'category_translation': "
                f"{', '.join(missing_trans_cols)}."
            )

        trans_df = trans_raw.copy()
        trans_df["product_category_name"] = _clean_text_series(
            trans_df["product_category_name"]
        )
        trans_df["product_category_name_english"] = _clean_text_series(
            trans_df["product_category_name_english"]
        )
        trans_df = trans_df.loc[trans_df["product_category_name"].notna()].copy()

        if trans_df.empty:
            warnings.append("Tabela de tradução de categorias está vazia.")
        else:
            dup_trans = int(
                trans_df.duplicated(subset=["product_category_name"], keep="first").sum()
            )
            if dup_trans > 0:
                trans_conflicts = trans_df.groupby(
                    "product_category_name", dropna=True
                )["product_category_name_english"].nunique(dropna=True)
                n_t_conflicts = int((trans_conflicts > 1).sum())
                if n_t_conflicts > 0:
                    warnings.append(
                        f"Detectadas {n_t_conflicts} categoria(s) com traduções conflitantes; mantida a primeira."
                    )
                else:
                    warnings.append(
                        f"Detectadas {dup_trans} linha(s) duplicada(s) na tradução de categorias; mantida a primeira."
                    )
        trans_dedup = trans_df.drop_duplicates(
            subset=["product_category_name"], keep="first"
        )[["product_category_name", "product_category_name_english"]]

        items_del = items_del.merge(
            trans_dedup,
            on="product_category_name",
            how="left",
            validate="many_to_one",
        )
        translation_loaded = True
    else:
        items_del["product_category_name_english"] = pd.Series(
            pd.array([pd.NA] * len(items_del), dtype="string"),
            index=items_del.index,
        )

    items_missing_category = int(items_del["product_category_name"].isna().sum())
    items_del["product_category_name_display"] = (
        items_del["product_category_name_english"]
        .fillna(items_del["product_category_name"])
        .fillna(UNKNOWN_CATEGORY_LABEL)
        .astype("string")
    )

    # 5. Join orders_del metadata onto items_del (N:1) and reconcile orders_df
    orders_meta = orders_del[
        ["order_id", "customer_id", "customer_unique_id", "order_purchase_timestamp"]
    ]
    items_del = items_del.merge(
        orders_meta,
        on="order_id",
        how="inner",
        validate="many_to_one",
    )

    if items_del.empty or orders_del.empty:
        if not orders_del.empty:
            warnings.append(
                f"{len(orders_del)} pedido(s) entregue(s) sem itens válidos foram excluídos da análise."
            )
        warnings.append(
            "Nenhum pedido entregue válido restante após filtragem e limpeza."
        )
        diagnostics = DataDiagnostics(
            orders_total_read=orders_total_read,
            orders_delivered=0,
            orders_excluded_status=orders_excluded_status,
            orders_invalid_timestamp=orders_invalid_timestamp,
            items_total_read=items_total_read,
            items_in_delivered_orders=items_in_delivered_orders,
            items_dropped_invalid_price_or_key=items_dropped_invalid_price_or_key,
            customers_total_read=customers_total_read,
            customers_duplicate_keys_dropped=customers_duplicate_keys_dropped,
            orders_missing_customer=orders_missing_customer,
            products_total_read=products_total_read,
            products_duplicate_keys_dropped=products_duplicate_keys_dropped,
            items_missing_product=items_missing_product,
            items_missing_category=items_missing_category,
            translation_loaded=translation_loaded,
            min_purchase_date=None,
            max_purchase_date=None,
            unique_customers_delivered=0,
            warnings=warnings,
        )
        return PreparedDataset(
            items_df=_empty_items_df(),
            orders_df=_empty_orders_df(),
            diagnostics=diagnostics,
        )

    items_del["year_month"] = (
        items_del["order_purchase_timestamp"].dt.strftime("%Y-%m").astype("string")
    )
    items_df = (
        items_del[ITEMS_COLUMNS]
        .sort_values(
            ["order_purchase_timestamp", "order_id", "order_item_id"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    items_df["price"] = items_df["price"].astype("float64")

    orders_agg = (
        items_df.groupby("order_id", as_index=False, sort=False)
        .agg(
            order_product_revenue=("price", "sum"),
            items_count=("order_item_id", "count"),
        )
    )
    zero_item_orders = int(len(orders_del) - len(orders_agg))
    if zero_item_orders > 0:
        warnings.append(
            f"{zero_item_orders} pedido(s) entregue(s) sem itens válidos foram excluídos da análise."
        )

    orders_df = orders_del.merge(
        orders_agg,
        on="order_id",
        how="inner",
        validate="one_to_one",
    )
    orders_df["year_month"] = (
        orders_df["order_purchase_timestamp"].dt.strftime("%Y-%m").astype("string")
    )
    orders_df = (
        orders_df[ORDERS_COLUMNS]
        .sort_values(["order_purchase_timestamp", "order_id"], kind="mergesort")
        .reset_index(drop=True)
    )
    orders_df["order_product_revenue"] = orders_df["order_product_revenue"].astype(
        "float64"
    )
    orders_df["items_count"] = orders_df["items_count"].astype("int64")

    orders_delivered = int(len(orders_df))
    unique_customers_delivered = int(orders_df["customer_unique_id"].nunique())
    min_purchase_date = pd.Timestamp(orders_df["order_purchase_timestamp"].min())
    max_purchase_date = pd.Timestamp(orders_df["order_purchase_timestamp"].max())

    diagnostics = DataDiagnostics(
        orders_total_read=orders_total_read,
        orders_delivered=orders_delivered,
        orders_excluded_status=orders_excluded_status,
        orders_invalid_timestamp=orders_invalid_timestamp,
        items_total_read=items_total_read,
        items_in_delivered_orders=items_in_delivered_orders,
        items_dropped_invalid_price_or_key=items_dropped_invalid_price_or_key,
        customers_total_read=customers_total_read,
        customers_duplicate_keys_dropped=customers_duplicate_keys_dropped,
        orders_missing_customer=orders_missing_customer,
        products_total_read=products_total_read,
        products_duplicate_keys_dropped=products_duplicate_keys_dropped,
        items_missing_product=items_missing_product,
        items_missing_category=items_missing_category,
        translation_loaded=translation_loaded,
        min_purchase_date=min_purchase_date,
        max_purchase_date=max_purchase_date,
        unique_customers_delivered=unique_customers_delivered,
        warnings=warnings,
    )

    return PreparedDataset(
        items_df=items_df,
        orders_df=orders_df,
        diagnostics=diagnostics,
    )
