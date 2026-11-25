"""Streamlit entry point for Unidata ("E-commerce Insights")."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from unidata.analytics import (  # noqa: E402
    compute_category_ranking,
    compute_kpis,
    compute_monthly_series,
    filter_prepared_data,
)
from unidata.config import OPTIONAL_FILES, REQUIRED_FILES, get_data_dir  # noqa: E402
from unidata.formatting import format_date_pt, format_month_pt  # noqa: E402
from unidata.loader import LoadResult, load_olist_dataset  # noqa: E402
from unidata.pipeline import PreparedDataset, prepare_data  # noqa: E402
from unidata.recommendations import generate_recommendations  # noqa: E402
from unidata.segmentation import SegmentationResult, compute_rfm_and_clusters  # noqa: E402
from unidata.ui.sections import (  # noqa: E402
    render_categories_section,
    render_customers_section,
    render_empty_coverage_state,
    render_empty_filter_state,
    render_header,
    render_kpi_grid,
    render_loading_skeleton,
    render_methodology_section,
    render_missing_or_invalid_state,
    render_recommendations_section,
    render_seasonality_section,
)
from unidata.ui.theme import inject_rekki_theme  # noqa: E402

_ALL_YEARS_OPTION = "Todos os anos"
_START_ALL_OPTION = "Início"
_END_ALL_OPTION = "Fim"


def _build_dataset_snapshot(
    data_dir: Path,
) -> tuple[str, tuple[tuple[str, bool, int, int], ...]]:
    """Capture resolved directory path and (filename, exists, mtime_ns, size) for cache invalidation."""
    resolved = str(data_dir.resolve())
    entries: list[tuple[str, bool, int, int]] = []
    for filename in (*REQUIRED_FILES.values(), *OPTIONAL_FILES.values()):
        file_path = data_dir / filename
        if file_path.is_file():
            stat_info = file_path.stat()
            entries.append(
                (filename, True, int(stat_info.st_mtime_ns), int(stat_info.st_size))
            )
        else:
            entries.append((filename, False, 0, 0))
    return resolved, tuple(entries)


@st.cache_data(show_spinner=False)
def load_and_prepare_cached(
    data_dir_str: str,
    snapshot: tuple[tuple[str, bool, int, int], ...],
) -> tuple[LoadResult, PreparedDataset | None]:
    """Load local Olist CSVs and run relational preparation, cached by filesystem snapshot."""
    del snapshot
    load_result = load_olist_dataset(data_dir_str)
    if not load_result.ok:
        return load_result, None
    return load_result, prepare_data(load_result.tables)


@st.cache_data(show_spinner=False)
def compute_segmentation_cached(
    data_dir_str: str,
    snapshot: tuple[tuple[str, bool, int, int], ...],
    start_ym: str | None,
    end_ym: str | None,
) -> SegmentationResult:
    """Compute reproducible RFM + K-means segmentation for the active temporal window."""
    _, prepared = load_and_prepare_cached(data_dir_str, snapshot)
    if prepared is None:
        return compute_rfm_and_clusters(pd.DataFrame())
    filtered = filter_prepared_data(prepared, start_ym=start_ym, end_ym=end_ym)
    return compute_rfm_and_clusters(filtered.items_df)


def _on_year_change() -> None:
    """Reset month boundaries whenever the selected year changes."""
    st.session_state["filter_start_ym"] = _START_ALL_OPTION
    st.session_state["filter_end_ym"] = _END_ALL_OPTION


def _reset_filters() -> None:
    """Restore full-period temporal filters."""
    st.session_state["filter_year"] = _ALL_YEARS_OPTION
    st.session_state["filter_start_ym"] = _START_ALL_OPTION
    st.session_state["filter_end_ym"] = _END_ALL_OPTION


def _format_month_option(value: str) -> str:
    """Format month dropdown options with both ISO YYYY-MM and pt-BR MMM/YYYY."""
    if value in (_START_ALL_OPTION, _END_ALL_OPTION):
        return value
    return f"{value} ({format_month_pt(value)})"


def main() -> None:
    """Run the Unidata Streamlit dashboard application."""
    st.set_page_config(
        page_title="Unidata — E-commerce Insights",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_rekki_theme()

    data_dir = get_data_dir()
    data_dir_str, snapshot = _build_dataset_snapshot(data_dir)

    loading_slot = st.empty()
    with loading_slot.container():
        render_loading_skeleton()
    load_result, prepared = load_and_prepare_cached(data_dir_str, snapshot)
    loading_slot.empty()

    if not load_result.ok or prepared is None:
        render_header(
            period_text="Base indisponível",
            is_filtered=False,
            data_notice="Aguardando arquivos CSV locais da Olist",
            scope_label="Aguardando dados",
            show_section_nav=False,
        )
        render_missing_or_invalid_state(load_result)
        render_methodology_section(None, None, data_dir)
        return

    if prepared.orders_df.empty:
        render_header(
            period_text="Sem cobertura de entregas",
            is_filtered=False,
            data_notice="Nenhum pedido entregue válido após limpeza",
            scope_label="Sem cobertura",
            show_section_nav=False,
        )
        render_empty_coverage_state(prepared.diagnostics)
        render_methodology_section(prepared.diagnostics, None, data_dir)
        return

    base_min_ym = str(prepared.orders_df["year_month"].min())
    base_max_ym = str(prepared.orders_df["year_month"].max())
    years = sorted({str(ym)[:4] for ym in prepared.orders_df["year_month"].dropna()})
    all_months = [
        p.strftime("%Y-%m")
        for p in pd.period_range(base_min_ym, base_max_ym, freq="M")
    ]

    if "filter_year" not in st.session_state or st.session_state["filter_year"] not in (
        _ALL_YEARS_OPTION,
        *years,
    ):
        st.session_state["filter_year"] = _ALL_YEARS_OPTION

    selected_year = str(st.session_state["filter_year"])
    scoped_months = (
        all_months
        if selected_year == _ALL_YEARS_OPTION
        else [ym for ym in all_months if ym.startswith(f"{selected_year}-")]
    )
    start_options = [_START_ALL_OPTION, *scoped_months]
    end_options = [_END_ALL_OPTION, *scoped_months]

    if (
        "filter_start_ym" not in st.session_state
        or st.session_state["filter_start_ym"] not in start_options
    ):
        st.session_state["filter_start_ym"] = _START_ALL_OPTION
    if (
        "filter_end_ym" not in st.session_state
        or st.session_state["filter_end_ym"] not in end_options
    ):
        st.session_state["filter_end_ym"] = _END_ALL_OPTION

    with st.container():
        col_year, col_start, col_end, col_reset = st.columns(
            [1.1, 1.5, 1.5, 0.9], vertical_alignment="bottom"
        )
        with col_year:
            selected_year = st.selectbox(
                "Ano analisado",
                options=[_ALL_YEARS_OPTION, *years],
                key="filter_year",
                on_change=_on_year_change,
            )
        scoped_months = (
            all_months
            if selected_year == _ALL_YEARS_OPTION
            else [ym for ym in all_months if ym.startswith(f"{selected_year}-")]
        )
        start_options = [_START_ALL_OPTION, *scoped_months]
        end_options = [_END_ALL_OPTION, *scoped_months]
        if st.session_state["filter_start_ym"] not in start_options:
            st.session_state["filter_start_ym"] = _START_ALL_OPTION
        if st.session_state["filter_end_ym"] not in end_options:
            st.session_state["filter_end_ym"] = _END_ALL_OPTION

        with col_start:
            selected_start = st.selectbox(
                "Mês inicial",
                options=start_options,
                format_func=_format_month_option,
                key="filter_start_ym",
            )
        with col_end:
            selected_end = st.selectbox(
                "Mês final",
                options=end_options,
                format_func=_format_month_option,
                key="filter_end_ym",
            )
        with col_reset:
            st.button(
                "Limpar filtro",
                key="reset_filter_btn",
                on_click=_reset_filters,
                width="stretch",
            )

    year_start = f"{selected_year}-01" if selected_year != _ALL_YEARS_OPTION else None
    year_end = f"{selected_year}-12" if selected_year != _ALL_YEARS_OPTION else None
    month_start = None if selected_start == _START_ALL_OPTION else str(selected_start)
    month_end = None if selected_end == _END_ALL_OPTION else str(selected_end)

    eff_start = (
        max(year_start, month_start)
        if year_start and month_start
        else (month_start or year_start)
    )
    eff_end = (
        min(year_end, month_end)
        if year_end and month_end
        else (month_end or year_end)
    )

    is_filtered = eff_start is not None or eff_end is not None
    filtered = filter_prepared_data(prepared, start_ym=eff_start, end_ym=eff_end)
    kpis = compute_kpis(filtered)

    base_span = (
        f"{format_date_pt(prepared.diagnostics.min_purchase_date)} a "
        f"{format_date_pt(prepared.diagnostics.max_purchase_date)}"
    )
    data_notice = f"Cobertura da base local: {base_span}"

    if kpis.is_empty:
        empty_period = f"{eff_start or base_min_ym} a {eff_end or base_max_ym}"
        render_header(
            period_text=empty_period,
            is_filtered=True,
            data_notice=data_notice,
            scope_label="Recorte sem dados",
            show_section_nav=False,
        )
        render_empty_filter_state(eff_start, eff_end, _reset_filters)
        render_methodology_section(filtered.diagnostics, None, data_dir)
        return

    period_label = (
        f"{format_date_pt(kpis.period_start)} a {format_date_pt(kpis.period_end)}"
    )
    monthly_df = compute_monthly_series(filtered)
    categories_df = compute_category_ranking(filtered)
    seg_result = compute_segmentation_cached(
        data_dir_str,
        snapshot,
        eff_start,
        eff_end,
    )
    rfm_scope_label = (
        "Período filtrado (recorte selecionado)"
        if is_filtered
        else "Base completa"
    )
    recs = generate_recommendations(
        kpis=kpis,
        monthly_df=monthly_df,
        categories_df=categories_df,
        seg_result=seg_result,
        period_label=period_label,
        rfm_scope_label=rfm_scope_label,
    )

    render_header(
        period_text=period_label,
        is_filtered=is_filtered,
        data_notice=data_notice,
    )
    render_kpi_grid(kpis, period_label)
    render_seasonality_section(monthly_df, period_label)
    render_customers_section(seg_result, rfm_scope_label)
    render_categories_section(categories_df, period_label)
    render_recommendations_section(
        recs=recs,
        seg_ok=seg_result.ok,
        month_count=len(monthly_df),
    )
    render_methodology_section(filtered.diagnostics, seg_result, data_dir)


if __name__ == "__main__":
    main()
