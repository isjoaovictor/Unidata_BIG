"""Local CSV ingestion, schema validation, and onboarding payload for Olist data."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from unidata.config import (
    DATASET_LICENSE,
    DATASET_NAME,
    ID_COLUMNS,
    KAGGLE_DATASET_URL,
    OPTIONAL_FILES,
    REQUIRED_COLUMNS,
    REQUIRED_FILES,
    TEXT_COLUMNS,
    get_data_dir,
)


@dataclass(frozen=True)
class SchemaError:
    """Structured validation error for an Olist CSV file."""

    file_key: str
    filename: str
    message_pt: str
    missing_columns: list[str] = field(default_factory=list)


@dataclass
class LoadResult:
    """Outcome of loading and validating local Olist CSV files."""

    ok: bool
    data_dir: Path
    tables: dict[str, pd.DataFrame]
    missing_files: list[str]
    errors: list[SchemaError]
    has_translation: bool
    onboarding_message_pt: str


_SENTINEL_EMPTY_STRINGS = frozenset({"", "nan", "none", "<na>", "nat"})
_CANONICAL_TS_DTYPE = pd.to_datetime(["2000-01-01"], errors="coerce").dtype


def _clean_string_column(series: pd.Series) -> pd.Series:
    """Strip whitespace on non-null string entries without turning NaN into 'nan'."""
    if series.empty:
        return pd.Series(pd.array([], dtype="string"), index=series.index)

    as_str = series.astype("string").str.strip()
    is_sentinel = as_str.str.lower().isin(_SENTINEL_EMPTY_STRINGS)
    return as_str.mask(is_sentinel, pd.NA)


def _parse_purchase_timestamps(series: pd.Series) -> pd.Series:
    """Parse purchase timestamps to UTC-normalized tz-naive datetime64 safely."""
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


def _read_and_validate_csv(
    file_key: str,
    file_path: Path,
) -> tuple[pd.DataFrame | None, SchemaError | None]:
    """Read a single CSV with strict UTF-8(-SIG), schema checks, and type coercion."""
    filename = file_path.name

    try:
        df = pd.read_csv(
            file_path,
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=True,
        )
    except UnicodeDecodeError:
        return None, SchemaError(
            file_key=file_key,
            filename=filename,
            message_pt=(
                f"Erro de codificação ao ler '{filename}': "
                "utilize codificação UTF-8 (ou UTF-8 com BOM)."
            ),
        )
    except pd.errors.EmptyDataError:
        return None, SchemaError(
            file_key=file_key,
            filename=filename,
            message_pt=f"O arquivo '{filename}' está vazio ou sem cabeçalho.",
        )
    except pd.errors.ParserError:
        return None, SchemaError(
            file_key=file_key,
            filename=filename,
            message_pt=(
                f"O arquivo '{filename}' possui CSV malformado ou delimitador inválido."
            ),
        )
    except (OSError, ValueError) as exc:
        return None, SchemaError(
            file_key=file_key,
            filename=filename,
            message_pt=f"Falha ao ler '{filename}': {type(exc).__name__}.",
        )

    df.columns = [str(col).strip() for col in df.columns]

    if df.columns.duplicated().any():
        dup_cols = list(
            dict.fromkeys(str(col) for col in df.columns[df.columns.duplicated()])
        )
        return None, SchemaError(
            file_key=file_key,
            filename=filename,
            message_pt=(
                f"Colunas duplicadas detectadas em '{filename}': "
                f"{', '.join(dup_cols)}."
            ),
        )

    expected_cols = REQUIRED_COLUMNS[file_key]
    missing_cols = [col for col in expected_cols if col not in df.columns]
    if missing_cols:
        return None, SchemaError(
            file_key=file_key,
            filename=filename,
            message_pt=(
                f"Colunas obrigatórias ausentes em '{filename}': "
                f"{', '.join(missing_cols)}."
            ),
            missing_columns=missing_cols,
        )

    for col in (*ID_COLUMNS, *TEXT_COLUMNS):
        if col in df.columns:
            df[col] = _clean_string_column(df[col])

    if file_key == "orders":
        if "order_status" in df.columns:
            df["order_status"] = df["order_status"].str.lower()
        df["order_purchase_timestamp"] = _parse_purchase_timestamps(
            df["order_purchase_timestamp"]
        )
    elif file_key == "order_items":
        df["price"] = pd.to_numeric(df["price"], errors="coerce").astype("float64")

    return df, None


def _build_onboarding_message_pt(
    target_dir: Path,
    missing_files: list[str],
    errors: list[SchemaError],
    dir_missing: bool = False,
) -> str:
    """Compose actionable pt-BR onboarding instructions for missing or invalid files."""
    if not dir_missing and not missing_files and not errors:
        return ""

    lines: list[str] = []
    if dir_missing:
        lines.append(
            f"O diretório de dados esperado não foi encontrado: {target_dir}"
        )

    if missing_files:
        lines.append("Arquivos CSV obrigatórios ausentes:")
        for fname in missing_files:
            lines.append(f"- {fname}")

    optional_name = OPTIONAL_FILES["category_translation"]
    lines.append(
        f"Arquivo opcional de tradução de categorias: {optional_name} "
        "(se ausente, os nomes originais das categorias serão exibidos)."
    )

    if errors:
        lines.append("Erros de validação encontrados:")
        for err in errors:
            lines.append(f"- {err.filename}: {err.message_pt}")

    lines.append(
        f"Como obter os dados: baixe manualmente o '{DATASET_NAME}' no Kaggle "
        f"({KAGGLE_DATASET_URL}) — licença {DATASET_LICENSE} (uso não comercial) — "
        f"e coloque os arquivos CSV diretamente em: {target_dir}"
    )

    return "\n".join(lines)


def load_olist_dataset(data_dir: Path | str | None = None) -> LoadResult:
    """Load and validate local Olist CSV files without downloading or fabricating data."""
    target_dir = Path(data_dir) if data_dir is not None else get_data_dir()

    if not target_dir.exists() or not target_dir.is_dir():
        missing_files = list(REQUIRED_FILES.values())
        onboarding = _build_onboarding_message_pt(
            target_dir=target_dir,
            missing_files=missing_files,
            errors=[],
            dir_missing=True,
        )
        return LoadResult(
            ok=False,
            data_dir=target_dir,
            tables={},
            missing_files=missing_files,
            errors=[],
            has_translation=False,
            onboarding_message_pt=onboarding,
        )

    tables: dict[str, pd.DataFrame] = {}
    missing_files: list[str] = []
    errors: list[SchemaError] = []

    for file_key, filename in REQUIRED_FILES.items():
        file_path = target_dir / filename
        if not file_path.is_file():
            missing_files.append(filename)
            continue

        df, err = _read_and_validate_csv(file_key, file_path)
        if err is not None:
            errors.append(err)
        elif df is not None:
            tables[file_key] = df

    has_translation = False
    trans_key = "category_translation"
    trans_filename = OPTIONAL_FILES[trans_key]
    trans_path = target_dir / trans_filename
    if trans_path.is_file():
        trans_df, trans_err = _read_and_validate_csv(trans_key, trans_path)
        if trans_err is not None:
            errors.append(trans_err)
        elif trans_df is not None:
            tables[trans_key] = trans_df
            has_translation = True

    ok = len(missing_files) == 0 and len(errors) == 0
    onboarding = _build_onboarding_message_pt(
        target_dir=target_dir,
        missing_files=missing_files,
        errors=errors,
        dir_missing=False,
    )

    return LoadResult(
        ok=ok,
        data_dir=target_dir,
        tables=tables,
        missing_files=missing_files,
        errors=errors,
        has_translation=has_translation,
        onboarding_message_pt=onboarding,
    )
