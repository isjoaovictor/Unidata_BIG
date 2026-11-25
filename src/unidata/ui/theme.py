"""REKKI Operate dark theme tokens, accessible CSS, and HTML escaping helpers."""

from __future__ import annotations

import html

import streamlit as st

PALETTE: dict[str, str] = {
    "canvas": "#080b12",
    "surface": "#101622",
    "card": "#151d2b",
    "control": "#202a3a",
    "elevated": "#2a3547",
    "accent": "#4f8cff",
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
/* Unidata: calm, native-feeling surfaces and immediate interaction feedback. */
@font-face {
    font-family: "Roboto";
    font-style: normal;
    font-weight: 100 900;
    font-display: swap;
    src: url("/app/static/assets/fonts/roboto-latin.woff2") format("woff2");
}
@font-face {
    font-family: "Roboto";
    font-style: normal;
    font-weight: 100 900;
    font-display: swap;
    src: url("/app/static/assets/fonts/roboto-latin-ext.woff2") format("woff2");
    unicode-range: U+0100-00FF;
}
:root {
    font-size: 17px;
    color-scheme: dark;
    --color-canvas: #080b12;
    --color-surface: #101622;
    --color-card: #151d2b;
    --color-control: #202a3a;
    --color-elevated: #2a3547;
    --color-accent: #4f8cff;
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
    background-color: #080b12 !important;
    color: #ffffff !important;
    font-family: "Roboto", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 1rem;
    line-height: 1.55;
    font-optical-sizing: auto;
    overflow-x: clip;
}

[data-testid="stHeader"] {
    display: none !important;
}

header[data-testid="stHeader"],
header:not(.unidata-header),
[data-testid="stAppViewContainer"] > [data-testid="stHeader"],
[data-testid="stAppToolbar"],
[data-testid="stToolbar"],
#MainMenu, footer { display: none !important; }

[data-testid="stMainBlockContainer"],
.block-container {
    width: calc(100% - 290px) !important;
    max-width: none !important;
    padding: 30px 32px 48px !important;
    margin: 0 0 0 290px !important;
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
    background: linear-gradient(135deg, rgba(25,36,54,.96), rgba(14,20,31,.94));
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 20px;
}

.unidata-logo {
    width: 2.75rem;
    height: 2.75rem;
    flex: 0 0 auto;
    border-radius: .82rem;
    box-shadow: 0 8px 24px rgba(35, 104, 232, .28);
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

.unidata-brand-name {
    margin: 0 0 .2rem;
    color: #f4f7ff;
    font-family: "Eurostile", "Bank Gothic", "Arial Narrow", ui-monospace, monospace;
    font-size: 1.08rem;
    font-weight: 800;
    letter-spacing: .2em;
    line-height: 1;
    text-transform: uppercase;
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
    letter-spacing: -0.035em;
    font-optical-sizing: auto;
}

.unidata-context-line {
    margin: 4px 0 0;
    font-size: 1rem;
    color: #b7c4d8;
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
    padding: 7px 14px;
    font-size: 0.95rem;
    color: #ffffff;
    line-height: 1.3;
}

.unidata-pill--accent {
    border-color: #0063e1;
    background-color: rgba(0, 99, 225, 0.16);
}

.unidata-nominal-note {
    margin: 10px 0 14px;
    font-size: 0.95rem;
    color: #b7c4d8;
    line-height: 1.6;
}

.unidata-nav {
    display: flex;
    position: fixed;
    z-index: 1000;
    inset: 22px auto 22px 20px;
    width: 232px;
    padding: 18px 14px;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    border: 1px solid rgba(255,255,255,.14);
    border-radius: 24px;
    background: linear-gradient(160deg, rgba(35,51,74,.82), rgba(11,17,27,.88));
    box-shadow: 0 22px 64px rgba(0,0,0,.42), inset 0 1px rgba(255,255,255,.12);
    -webkit-backdrop-filter: blur(28px) saturate(155%);
    backdrop-filter: blur(28px) saturate(155%);
}

.unidata-nav::before {
    content: "UNIDATA";
    display: block;
    box-sizing: border-box;
    width: 100%;
    min-height: 64px;
    white-space: nowrap;
    margin: 3px 0 18px;
    padding: 12px 0 18px 64px;
    border-bottom: 1px solid rgba(255,255,255,.12);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect x='10' y='10' width='80' height='80' rx='22' fill='%234f8cff'/%3E%3Cpath d='M29 34V52Q29 69 50 69Q71 69 71 52V28M50 45V56' fill='none' stroke='white' stroke-width='10' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: 52px 52px;
    background-position: left center;
    color: #f5f8ff;
    font-family: "Roboto", sans-serif;
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: .04em;
}

.unidata-nav a {
    display: inline-flex;
    align-items: center;
    min-height: 50px;
    padding: 12px 14px;
    border-radius: 14px;
    background: rgba(255,255,255,.075);
    border: 1px solid rgba(255,255,255,.07);
    color: #ffffff !important;
    text-decoration: none !important;
    font-size: 1rem;
    font-weight: 600;
    transition: background-color 180ms ease, border-color 180ms ease, transform 180ms ease, box-shadow 180ms ease;
}

.unidata-nav a:hover {
    background: linear-gradient(110deg, rgba(88,151,255,.38), rgba(88,151,255,.16));
    border-color: rgba(160,195,255,.35);
    transform: translateX(2px);
    box-shadow: inset 0 1px rgba(255,255,255,.12);
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
    font-size: 0.95rem;
    color: #b7c4d8;
    line-height: 1.45;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 16px;
}

.kpi-card {
    background: linear-gradient(155deg, #192333, #121a27);
    border: 1px solid rgba(255,255,255,0.085);
    border-radius: 16px;
    padding: 20px 24px;
    min-width: 0;
    box-shadow: 0 10px 28px rgba(0,0,0,.14);
    transition: transform 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
}

.kpi-card:hover {
    transform: translateY(-2px);
    border-color: rgba(105,167,255,.34);
    box-shadow: 0 16px 34px rgba(0,0,0,.22);
}

.kpi-label {
    font-size: 0.95rem;
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
    font-size: 0.95rem;
    color: #b7c4d8;
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
    font-size: 0.95rem;
    font-weight: 600;
    background-color: #1f1f1f;
    border: 1px solid rgba(255,255,255,0.12);
    color: #69a7ff;
}

.unidata-rec-period {
    font-size: 0.95rem;
    color: #b7c4d8;
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
    font-size: 1rem;
    color: #ffffff;
    line-height: 1.45;
}

.unidata-rec-caveat {
    margin: 0;
    font-size: 0.95rem;
    color: #b7c4d8;
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
    font-size: 0.95rem;
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
    font-size: 0.95rem;
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
    transition: transform 120ms ease, background-color 160ms ease, border-color 160ms ease;
}

.stButton > button:active { transform: scale(.98); }

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
        width: 100% !important;
        padding: 20px 16px 36px !important;
        margin: 0 !important;
    }
    .unidata-nav {
        position: sticky;
        inset: auto;
        width: 100%;
        max-height: none;
        margin: 0 0 16px;
        padding: 10px;
        border-radius: 18px;
        flex-direction: row;
        flex-wrap: wrap;
    }
    .unidata-nav::before { width: 100%; margin-bottom: 3px; padding-bottom: 10px; }
    .unidata-nav a { flex: 1 1 auto; justify-content: center; }
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

@media (prefers-reduced-transparency: reduce) {
    .unidata-header { background: #111a28; }
    .unidata-nav { background: #111a28; -webkit-backdrop-filter: none; backdrop-filter: none; }
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
