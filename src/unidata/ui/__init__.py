"""Streamlit presentation components for Unidata ("E-commerce Insights")."""

from unidata.ui.charts import (
    MONTHLY_METRIC_OPTIONS,
    PLOTLY_CONFIG,
    build_category_ranking_chart,
    build_monthly_trend_chart,
    build_segment_distribution_chart,
)
from unidata.ui.sections import (
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
from unidata.ui.theme import PALETTE, esc, inject_rekki_theme

__all__ = [
    "MONTHLY_METRIC_OPTIONS",
    "PALETTE",
    "PLOTLY_CONFIG",
    "build_category_ranking_chart",
    "build_monthly_trend_chart",
    "build_segment_distribution_chart",
    "esc",
    "inject_rekki_theme",
    "render_categories_section",
    "render_customers_section",
    "render_empty_coverage_state",
    "render_empty_filter_state",
    "render_header",
    "render_kpi_grid",
    "render_loading_skeleton",
    "render_methodology_section",
    "render_missing_or_invalid_state",
    "render_recommendations_section",
    "render_seasonality_section",
]
