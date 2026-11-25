"""Shared pytest fixtures and src/ path resolution for Unidata tests."""

from __future__ import annotations

from collections.abc import Callable
import getpass
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def pytest_configure(config: pytest.Config) -> None:
    """Fallback basetemp into .pytest_cache if OS pytest-of-<user> is inaccessible."""
    if getattr(config.option, "basetemp", None) is None:
        user = getpass.getuser() or "unknown"
        default_root = Path(tempfile.gettempdir()) / f"pytest-of-{user}"
        if default_root.exists():
            try:
                next(os.scandir(default_root), None)
            except PermissionError:
                fallback = PROJECT_ROOT / ".pytest_cache" / "basetemp"
                fallback.mkdir(parents=True, exist_ok=True)
                config.option.basetemp = str(fallback)

from unidata.config import OPTIONAL_FILES, REQUIRED_FILES  # noqa: E402
from unidata.loader import load_olist_dataset  # noqa: E402


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    """Return the root directory containing isolated synthetic fixtures."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def standard_olist_dir(fixtures_root: Path) -> Path:
    """Return path to the standard synthetic Olist fixture directory."""
    return fixtures_root / "standard_olist"


@pytest.fixture(scope="session")
def edge_cases_olist_dir(fixtures_root: Path) -> Path:
    """Return path to the edge-cases synthetic Olist fixture directory."""
    return fixtures_root / "edge_cases_olist"


@pytest.fixture(scope="session")
def empty_delivered_dir(fixtures_root: Path) -> Path:
    """Return path to the empty-delivered synthetic Olist fixture directory."""
    return fixtures_root / "empty_delivered"


@pytest.fixture
def standard_tables(standard_olist_dir: Path) -> dict[str, pd.DataFrame]:
    """Load and return a fresh copy of the standard synthetic tables."""
    result = load_olist_dataset(standard_olist_dir)
    assert result.ok is True
    return {name: df.copy() for name, df in result.tables.items()}


@pytest.fixture
def missing_all_files_dir(tmp_path: Path) -> Path:
    """Return an existing empty directory with no Olist CSV files."""
    target = tmp_path / "empty_data"
    target.mkdir()
    return target


@pytest.fixture
def partial_missing_files_dir(tmp_path: Path, standard_olist_dir: Path) -> Path:
    """Copy only 2 of the 4 required CSVs into a temporary directory."""
    target = tmp_path / "partial_data"
    target.mkdir()
    for key in ("orders", "customers"):
        filename = REQUIRED_FILES[key]
        shutil.copy2(standard_olist_dir / filename, target / filename)
    return target


@pytest.fixture
def no_translation_dir(tmp_path: Path, standard_olist_dir: Path) -> Path:
    """Copy standard_olist without the optional category translation CSV."""
    target = tmp_path / "no_translation"
    target.mkdir()
    for filename in REQUIRED_FILES.values():
        shutil.copy2(standard_olist_dir / filename, target / filename)
    return target


@pytest.fixture
def make_missing_column_dir(
    tmp_path: Path, standard_olist_dir: Path
) -> Callable[[str, str], Path]:
    """Factory creating a directory where one required/optional column is dropped."""

    def _factory(file_key: str, column_to_drop: str) -> Path:
        # Short, deterministic directory name: embedding full column names can exceed the
        # Windows 260-character path limit when the project is extracted to a deep path.
        digest = hashlib.sha1(f"{file_key}:{column_to_drop}".encode("utf-8")).hexdigest()[:8]
        target = tmp_path / f"mc_{digest}"
        target.mkdir(parents=True, exist_ok=True)
        all_files = {**REQUIRED_FILES, **OPTIONAL_FILES}
        for key, filename in all_files.items():
            src = standard_olist_dir / filename
            if src.is_file():
                shutil.copy2(src, target / filename)

        target_csv = target / all_files[file_key]
        df = pd.read_csv(target_csv, encoding="utf-8-sig", dtype=str)
        df = df.drop(columns=[column_to_drop])
        df.to_csv(target_csv, index=False, encoding="utf-8-sig")
        return target

    return _factory


@pytest.fixture
def make_corrupted_csv_dir(
    tmp_path: Path, standard_olist_dir: Path
) -> Callable[[str, bytes], Path]:
    """Factory creating a directory where one CSV file contains custom/corrupted bytes."""

    def _factory(file_key: str, raw_bytes: bytes) -> Path:
        target = tmp_path / f"corrupted_{file_key}"
        target.mkdir(parents=True, exist_ok=True)
        all_files = {**REQUIRED_FILES, **OPTIONAL_FILES}
        for filename in all_files.values():
            src = standard_olist_dir / filename
            if src.is_file():
                shutil.copy2(src, target / filename)
        (target / all_files[file_key]).write_bytes(raw_bytes)
        return target

    return _factory
