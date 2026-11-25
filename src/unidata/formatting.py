"""Locale-independent Brazilian Portuguese (pt-BR) and BRL formatting utilities."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from unidata.config import PT_BR_MONTH_ABBR

_YM_PATTERN = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


def _to_finite_float(value: Any) -> float | None:
    """Convert numeric inputs to finite float, returning None for invalid/non-finite values."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, Decimal, np.number)):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(num):
        return None
    return num


def format_brl(value: float | int | None) -> str:
    """Format a numeric value as Brazilian Real (e.g. 1234.56 -> 'R$ 1.234,56')."""
    num = _to_finite_float(value)
    if num is None:
        return "—"
    rounded = round(num, 2)
    if rounded == 0.0:
        rounded = 0.0
    abs_str = f"{abs(rounded):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if rounded < 0:
        return f"-R$ {abs_str}"
    return f"R$ {abs_str}"


def format_int_pt(value: int | float | None) -> str:
    """Format an integer with pt-BR dot thousands separator (e.g. 1234 -> '1.234')."""
    if isinstance(value, (bool, np.bool_)):
        return "—"
    if isinstance(value, (int, np.integer)):
        integer = int(value)
        return f"{integer:,}".replace(",", ".")
    num = _to_finite_float(value)
    if num is None:
        return "—"
    integer = int(round(num))
    return f"{integer:,}".replace(",", ".")


def format_pct_pt(value: float | int | None, decimals: int = 1) -> str:
    """Format percentage points in pt-BR (e.g. 12.34 -> '12,3%')."""
    num = _to_finite_float(value)
    if num is None:
        return "—"
    d = max(0, int(decimals))
    rounded = round(num, d)
    if rounded == 0.0:
        rounded = 0.0
    formatted = (
        f"{rounded:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    )
    return f"{formatted}%"


def format_ratio_pct_pt(value: float | int | None, decimals: int = 1) -> str:
    """Format a 0..1 ratio as a pt-BR percentage (e.g. 0.1234 -> '12,3%')."""
    num = _to_finite_float(value)
    if num is None:
        return "—"
    return format_pct_pt(num * 100.0, decimals=decimals)


def format_date_pt(dt: datetime | date | pd.Timestamp | str | None) -> str:
    """Format a date/timestamp as 'DD/MM/YYYY', returning '—' for null or invalid inputs."""
    if dt is None or isinstance(dt, (bool, int, float, np.number)):
        return "—"
    try:
        ts = pd.to_datetime(dt, errors="coerce")
    except (TypeError, ValueError):
        return "—"
    if pd.isna(ts):
        return "—"
    return ts.strftime("%d/%m/%Y")


def format_month_pt(ym: str | datetime | date | pd.Timestamp | None) -> str:
    """Format 'YYYY-MM' (or date/timestamp) as pt-BR 'MMM/YYYY' (e.g. '2017-11' -> 'Nov/2017')."""
    if ym is None or isinstance(ym, (bool, int, float, np.number)):
        return "—"

    year: int
    month: int
    if isinstance(ym, (datetime, date, pd.Timestamp)):
        try:
            if pd.isna(ym):
                return "—"
        except (TypeError, ValueError):
            return "—"
        year = int(ym.year)
        month = int(ym.month)
    elif isinstance(ym, str):
        match = _YM_PATTERN.fullmatch(ym.strip())
        if match is None:
            return "—"
        year = int(match.group(1))
        month = int(match.group(2))
        day_group = match.group(3)
        if year < 1:
            return "—"
        if day_group is not None:
            try:
                date(year, month, int(day_group))
            except ValueError:
                return "—"
    else:
        return "—"

    abbr = PT_BR_MONTH_ABBR.get(month)
    if abbr is None:
        return "—"
    return f"{abbr}/{year}"
