"""Central configuration, schemas, constants, and RFM parameters for Unidata."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR: Path = PROJECT_ROOT / "data"


def get_data_dir() -> Path:
    """Return configured data directory from UNIDATA_DATA_DIR or DEFAULT_DATA_DIR."""
    override = os.environ.get("UNIDATA_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DATA_DIR

REQUIRED_FILES: dict[str, str] = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
}

OPTIONAL_FILES: dict[str, str] = {
    "category_translation": "product_category_name_translation.csv",
}

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "orders": ("order_id", "customer_id", "order_status", "order_purchase_timestamp"),
    "order_items": ("order_id", "order_item_id", "product_id", "price"),
    "customers": ("customer_id", "customer_unique_id"),
    "products": ("product_id", "product_category_name"),
    "category_translation": ("product_category_name", "product_category_name_english"),
}

OPTIONAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "category_translation": ("product_category_name", "product_category_name_english"),
}

ID_COLUMNS: tuple[str, ...] = (
    "order_id",
    "customer_id",
    "customer_unique_id",
    "product_id",
    "order_item_id",
)

TEXT_COLUMNS: tuple[str, ...] = (
    "order_status",
    "product_category_name",
    "product_category_name_english",
)

DELIVERED_STATUS: str = "delivered"
UNKNOWN_CATEGORY_LABEL: str = "Não informado"


@dataclass(frozen=True)
class RFMConfig:
    """Reproducible parameters for RFM feature transformation and K-means clustering."""

    n_clusters: int = 4
    random_state: int = 42
    n_init: int = 10
    log_transform_frequency: bool = True
    log_transform_monetary: bool = True
    min_customers: int = 4


APP_TITLE: str = "Unidata"
APP_SUBTITLE: str = "E-commerce Insights"
DATASET_NAME: str = "Brazilian E-Commerce Public Dataset by Olist"
KAGGLE_DATASET_URL: str = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
DATASET_LICENSE: str = "CC BY-NC-SA 4.0"
DATASET_LICENSE_URL: str = "https://creativecommons.org/licenses/by-nc-sa/4.0/"

PROVENANCE_NOTE_PT: str = (
    "Dados históricos do marketplace brasileiro Olist (Kaggle, licença CC BY-NC-SA 4.0, "
    "uso exclusivamente não comercial). Valores monetários em BRL são nominais do período "
    "da base (aproximadamente 2016–2018), sem correção inflacionária e sem frete na receita "
    "de produtos. Padrões observados são descritivos e não implicam causalidade ou previsão."
)

PT_BR_MONTH_ABBR: dict[int, str] = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}
