"""REKKI Operate dark theme tokens, accessible CSS, and HTML escaping helpers."""

from __future__ import annotations

import html

import streamlit as st

PALETTE: dict[str, str] = {
    "canvas": "#000000",
    "surface": "#040910",
    "card": "#0d0d0d",
    "control": "#1f1f1f",
    "elevated": "#2b2c2e",
    "accent": "#0063e1",
    "text": "#ffffff",
    "muted": "#858585",
    "subtle": "#979797",
    "border_card": "rgba(255,255,255,0.12)",
    "focus_ring": "#69a7ff",
    "series_primary": "#0063e1",
    "series_secondary": "#69a7ff",
    "series_teal": "#2dd4bf",
    "series_amber": "#f59e0b",
    "danger": "#f87171",
    "warning": "#fbbf24",
    "success": "#34d399",
}

THEME_CSS: str = """
:root {
    --color-canvas: #000000;
    --color-surface: #040910;
    --color-card: #0d0d0d;
    --color-control: #1f1f1f;
    --color-elevated: #2b2c2e;
    --color-accent: #0063e1;
    --color-text: #ffffff;
    --color-muted: #858585;
    --color-subtle: #979797;
    --border-card: rgba(255,255,255,0.12);
    --focus-ring: #69a7ff;
}

html,
body,
.stApp,
[data-testid="stAppViewContainer"] {
    background-color: #000000 !important;
    color: #ffffff !important;
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    overflow-x: clip;
}

[data-testid="stHeader"] {
    background-color: rgba(0, 0, 0, 0.9) !important;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}

[data-testid="stMainBlockContainer"],
.block-container {
    max-width: 1440px;
    padding: 60px 32px 48px;
    margin: 0 auto;
    box-sizing: border-box;
}

.unidata-tabular,
.kpi-value,
[data-testid="stTable"] td,
[data-testid="stTable"] th,
table td,
table th,
.unidata-rec-evidence {
    font-variant-numeric: tabular-nums;
}

.unidata-header {
    background-color: #040910;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 20px;
}

.unidata-brand-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px 16px;
    margin-bottom: 10px;
}

.unidata-brand-title-wrap {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
}

.unidata-brand-bar {
    width: 4px;
    height: 28px;
    border-radius: 2px;
    background-color: #0063e1;
    flex-shrink: 0;
}

.unidata-page-title {
    margin: 0;
    font-size: clamp(1.35rem, 2vw, 1.85rem);
    font-weight: 600;
    line-height: 1.2;
    color: #ffffff;
}

.unidata-context-line {
    margin: 4px 0 0;
    font-size: 0.9375rem;
    color: #979797;
}

.unidata-badge-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
}

.unidata-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background-color: #1f1f1f;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 0.8125rem;
    color: #ffffff;
    line-height: 1.3;
}

.unidata-pill--accent {
    border-color: #0063e1;
    background-color: rgba(0, 99, 225, 0.16);
}

.unidata-nominal-note {
    margin: 10px 0 14px;
    font-size: 0.8125rem;
    color: #858585;
    line-height: 1.45;
}

.unidata-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.unidata-nav a {
    display: inline-flex;
    align-items: center;
    min-height: 40px;
    padding: 8px 14px;
    border-radius: 8px;
    background-color: #1f1f1f;
    border: 1px solid rgba(255,255,255,0.12);
    color: #ffffff !important;
    text-decoration: none !important;
    font-size: 0.875rem;
    font-weight: 500;
    transition: background-color 140ms ease, border-color 140ms ease;
}

.unidata-nav a:hover {
    background-color: #2b2c2e;
    border-color: #0063e1;
}

.unidata-section-head {
    margin: 28px 0 12px;
    padding-top: 20px;
    border-top: 1px solid rgba(255,255,255,0.1);
}

.unidata-section-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    line-height: 1.3;
    color: #ffffff;
}

.unidata-section-subtitle {
    margin: 4px 0 0;
    font-size: 0.875rem;
    color: #979797;
    line-height: 1.45;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 16px;
}

.kpi-card {
    background-color: #0d0d0d;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 20px 24px;
    min-width: 0;
}

.kpi-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #979797;
    margin-bottom: 8px;
}

.kpi-value {
    font-size: clamp(1.45rem, 2.2vw, 2.15rem);
    font-weight: 600;
    color: #ffffff;
    line-height: 1.15;
    margin-bottom: 8px;
    overflow-wrap: anywhere;
}

.kpi-sub {
    font-size: 0.8125rem;
    color: #858585;
    line-height: 1.4;
}

.unidata-card {
    background-color: #0d0d0d;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 14px;
}

.unidata-card--surface {
    background-color: #040910;
}

.unidata-alert-card {
    background-color: #0d0d0d;
    border: 1px solid rgba(255,255,255,0.12);
    border-left: 4px solid #0063e1;
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 16px;
}

.unidata-alert-card--warning {
    border-left-color: #fbbf24;
}

.unidata-alert-card--error {
    border-left-color: #f87171;
}

.unidata-alert-title {
    margin: 0 0 8px;
    font-size: 1.05rem;
    font-weight: 600;
    color: #ffffff;
}

.unidata-alert-body {
    margin: 0 0 8px;
    font-size: 0.9375rem;
    color: #ffffff;
    line-height: 1.5;
}

.unidata-alert-list {
    margin: 8px 0 12px 18px;
    padding: 0;
    color: #ffffff;
    font-size: 0.9rem;
    line-height: 1.55;
}

.unidata-rec-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-top: 8px;
}

.unidata-rec-card {
    background-color: #0d0d0d;
    border: 1px solid rgba(255,255,255,0.12);
    border-left: 4px solid #0063e1;
    border-radius: 16px;
    padding: 20px 24px;
    min-width: 0;
}

.unidata-rec-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
}

.unidata-rec-cat {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    background-color: #1f1f1f;
    border: 1px solid rgba(255,255,255,0.12);
    color: #69a7ff;
}

.unidata-rec-period {
    font-size: 0.8125rem;
    color: #858585;
}

.unidata-rec-title {
    margin: 0 0 8px;
    font-size: 1.05rem;
    font-weight: 600;
    color: #ffffff;
    line-height: 1.35;
}

.unidata-rec-obs {
    margin: 0 0 10px;
    font-size: 0.9375rem;
    color: #ffffff;
    line-height: 1.5;
}

.unidata-rec-evidence {
    background-color: #040910;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 10px;
    font-size: 0.875rem;
    color: #ffffff;
    line-height: 1.45;
}

.unidata-rec-caveat {
    margin: 0;
    font-size: 0.8125rem;
    color: #858585;
    line-height: 1.45;
}

.unidata-summary-box {
    background-color: #040910;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    padding: 14px 18px;
    margin: 10px 0 16px;
    font-size: 0.9rem;
    color: #ffffff;
    line-height: 1.5;
}

.unidata-mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 0.8125rem;
}

/* Data tables rendered via st.table */
[data-testid="stTable"] {
    background-color: #0d0d0d;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 6px 12px;
    overflow-x: auto;
    max-width: 100%;
    box-sizing: border-box;
    margin-bottom: 16px;
}

[data-testid="stTable"] table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
    color: #ffffff;
}

[data-testid="stTable"] th {
    color: #979797 !important;
    font-weight: 600;
    text-align: left;
    border-bottom: 1px solid rgba(255,255,255,0.12) !important;
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
    padding: 10px 10px !important;
}

[data-testid="stTable"] td {
    color: #ffffff !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
    padding: 10px 10px !important;
}

/* Streamlit controls */
.stSelectbox [data-baseweb="select"] > div {
    min-height: 42px;
    background-color: #1f1f1f !important;
    border-color: rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #ffffff !important;
}

.stSelectbox [data-baseweb="select"]:hover > div {
    background-color: #2b2c2e !important;
    border-color: #0063e1 !important;
}

.stButton > button {
    min-height: 42px;
    border-radius: 8px !important;
    background-color: #1f1f1f !important;
    color: #ffffff !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    font-weight: 500;
    padding: 0 16px;
}

.stButton > button:hover {
    background-color: #2b2c2e !important;
    border-color: #0063e1 !important;
}

[data-testid="stRadio"] > div {
    gap: 8px;
}

[data-testid="stExpander"] {
    background-color: #0d0d0d !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 16px !important;
    margin-top: 24px;
}

[data-testid="stExpander"] summary {
    padding: 14px 18px !important;
    color: #ffffff !important;
    font-weight: 600;
}

/* High-visibility keyboard focus indicator (#69a7ff) */
.stApp button:focus-visible,
.stApp a:focus-visible,
.stApp summary:focus-visible,
.stApp input:focus-visible,
.stApp select:focus-visible,
.stApp textarea:focus-visible,
.stApp [tabindex]:focus-visible,
.stApp [role="button"]:focus-visible,
.stApp [role="combobox"]:focus-visible,
.stApp [role="radio"]:focus-visible,
.stApp [role="slider"]:focus-visible,
.stApp [role="tab"]:focus-visible {
    outline: 2px solid #69a7ff !important;
    outline-offset: 2px !important;
    box-shadow: 0 0 0 3px rgba(105, 167, 255, 0.35) !important;
}

.stSelectbox [data-baseweb="select"]:has(:focus-visible) > div {
    border-color: #69a7ff !important;
    box-shadow: 0 0 0 3px rgba(105, 167, 255, 0.35) !important;
}

/* Skeleton loading */
.unidata-skeleton-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin: 12px 0;
}

.unidata-skeleton {
    height: 112px;
    border-radius: 16px;
    border: 1px solid rgba(255,255,255,0.12);
    background-color: #0d0d0d;
    animation: unidata-pulse 1.4s ease-in-out infinite;
}

@keyframes unidata-pulse {
    0%, 100% {
        opacity: 0.55;
    }
    50% {
        opacity: 0.9;
    }
}

@media (max-width: 1024px) {
    .kpi-grid,
    .unidata-skeleton-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .unidata-rec-grid {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 768px) {
    [data-testid="stMainBlockContainer"],
    .block-container {
        padding: 56px 16px 36px;
    }
}

@media (max-width: 640px) {
    .kpi-grid,
    .unidata-skeleton-grid {
        grid-template-columns: 1fr;
    }
    .unidata-header,
    .kpi-card,
    .unidata-card,
    .unidata-alert-card,
    .unidata-rec-card {
        padding: 16px;
    }
}

@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
        scroll-behavior: auto !important;
    }
}
"""


def esc(value: object) -> str:
    """Escape arbitrary text safely for HTML fragment interpolation."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def inject_rekki_theme() -> None:
    """Inject the REKKI Operate dark CSS design system into the Streamlit page."""
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
