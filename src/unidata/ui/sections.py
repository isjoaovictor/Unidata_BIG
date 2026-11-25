"""Section renderers for Unidata Streamlit UI covering all 7 operational states."""

from __future__ import annotations

from collections.abc import Callable
import base64
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from unidata.analytics import KPISummary
from unidata.config import (
    APP_SUBTITLE,
    APP_TITLE,
    DATASET_LICENSE,
    DATASET_LICENSE_URL,
    DATASET_NAME,
    KAGGLE_DATASET_URL,
    OPTIONAL_FILES,
    PROVENANCE_NOTE_PT,
    REQUIRED_FILES,
    RFMConfig,
)
from unidata.formatting import (
    format_brl,
    format_date_pt,
    format_int_pt,
    format_month_pt,
    format_pct_pt,
)
from unidata.loader import LoadResult
from unidata.pipeline import DataDiagnostics
from unidata.recommendations import Recommendation
from unidata.segmentation import SegmentationResult
from unidata.ui.charts import (
    MONTHLY_METRIC_OPTIONS,
    PLOTLY_CONFIG,
    build_category_ranking_chart,
    build_monthly_trend_chart,
    build_segment_distribution_chart,
)
from unidata.ui.theme import esc


def _render_html(html_block: str) -> None:
    """Render an HTML block via st.markdown without accidental Markdown code-block indentation."""
    cleaned = "\n".join(line.lstrip() for line in html_block.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


def _format_scalar_pt(value: float) -> str:
    """Format integer or 1-decimal scalar cleanly in pt-BR."""
    if float(value).is_integer():
        return format_int_pt(int(round(value)))
    return f"{value:.1f}".replace(".", ",")


def render_header(
    period_text: str,
    is_filtered: bool,
    data_notice: str,
    scope_label: str | None = None,
    show_section_nav: bool = True,
) -> None:
    """Render compact Operate-mode dashboard header with provenance and anchor navigation."""
    logo_path = Path(__file__).resolve().parents[3] / "design" / "unidata-app-icon.svg"
    logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    scope_badge = scope_label or ("Recorte filtrado" if is_filtered else "Base completa")
    nav_links = (
        """
        <a href="#visao-geral">Visão geral</a>
        <a href="#sazonalidade">Sazonalidade</a>
        <a href="#clientes">Clientes</a>
        <a href="#categorias">Categorias</a>
        <a href="#recomendacoes">Recomendações</a>
        <a href="#sobre-os-dados">Sobre os dados</a>
        """
        if show_section_nav
        else '<a href="#sobre-os-dados">Sobre os dados</a>'
    )
    _render_html(
        f"""
        <header class="unidata-header">
            <div class="unidata-brand-row">
                <div class="unidata-brand-title-wrap">
                    <img class="unidata-logo" src="data:image/svg+xml;base64,{logo_data}" alt="" aria-hidden="true">
                    <div>
                        <div class="unidata-brand-name">UNIDATA</div>
                        <h1 class="unidata-page-title">{esc(APP_TITLE)} — {esc(APP_SUBTITLE)}</h1>
                        <p class="unidata-context-line">Análise histórica da base Olist · {esc(data_notice)}</p>
                    </div>
                </div>
                <div class="unidata-badge-row">
                    <span class="unidata-pill unidata-pill--accent">
                        Período analisado: <strong>{esc(period_text)}</strong>
                    </span>
                    <span class="unidata-pill">{esc(scope_badge)}</span>
                </div>
            </div>
            <p class="unidata-nominal-note">
                Valores nominais em BRL (R$), sem correção inflacionária e sem frete na receita de produtos.
                Resultados refletem exclusivamente o padrão histórico observado nos arquivos locais carregados.
            </p>
            <nav class="unidata-nav" aria-label="Seções do painel">
                {nav_links}
            </nav>
        </header>
        """
    )


def render_loading_skeleton() -> None:
    """Render transient loading skeleton placeholders while preparing local CSVs."""
    _render_html(
        """
        <div class="unidata-card unidata-card--surface" role="status" aria-live="polite">
            <p class="unidata-alert-title">Carregando e validando dados locais…</p>
            <p class="unidata-alert-body">
                Preparando base local da Olist e calculando métricas executivas e segmentação RFM.
            </p>
            <div class="unidata-skeleton-grid" aria-hidden="true">
                <div class="unidata-skeleton"></div>
                <div class="unidata-skeleton"></div>
                <div class="unidata-skeleton"></div>
                <div class="unidata-skeleton"></div>
            </div>
        </div>
        """
    )


def render_missing_or_invalid_state(load_result: LoadResult) -> None:
    """Render onboarding/error guidance when required local CSVs are missing or invalid."""
    required_list = load_result.missing_files or list(REQUIRED_FILES.values())
    missing_items_html = "".join(
        f"<li><code class='unidata-mono'>{esc(fname)}</code></li>"
        for fname in required_list
    )

    errors_html = ""
    if load_result.errors:
        err_rows = []
        for err in load_result.errors:
            cols_info = (
                f" (colunas ausentes: <code class='unidata-mono'>{esc(', '.join(err.missing_columns))}</code>)"
                if err.missing_columns
                else ""
            )
            err_rows.append(
                f"<li><strong>{esc(err.filename)}</strong>: {esc(err.message_pt)}{cols_info}</li>"
            )
        errors_html = (
            "<p class='unidata-alert-body'><strong>Erros de validação detectados:</strong></p>"
            f"<ul class='unidata-alert-list'>{''.join(err_rows)}</ul>"
        )

    optional_name = OPTIONAL_FILES["category_translation"]
    _render_html(
        f"""
        <section class="unidata-alert-card unidata-alert-card--error" aria-label="Base local ausente ou inválida">
            <h2 class="unidata-alert-title">Arquivo ausente ou inválido na pasta de dados local</h2>
            <p class="unidata-alert-body">
                Nenhuma métrica foi fabricada. Para iniciar a análise, coloque os arquivos CSV oficiais da Olist em:
                <code class="unidata-mono">{esc(load_result.data_dir)}</code>
            </p>
            <p class="unidata-alert-body"><strong>Arquivos obrigatórios esperados:</strong></p>
            <ul class="unidata-alert-list">{missing_items_html}</ul>
            <p class="unidata-alert-body">
                <strong>Arquivo opcional:</strong> <code class='unidata-mono'>{esc(optional_name)}</code>
                (quando ausente, os nomes originais das categorias em português ou "Não informado" são mantidos).
            </p>
            {errors_html}
            <p class="unidata-alert-body">
                <strong>Como obter os dados:</strong> baixe manualmente o
                <a href="{esc(KAGGLE_DATASET_URL)}" target="_blank" rel="noopener noreferrer">{esc(DATASET_NAME)} no Kaggle</a>
                (licença <strong>{esc(DATASET_LICENSE)}</strong>, uso exclusivamente não comercial) e extraia os CSVs na pasta indicada acima.
            </p>
        </section>
        """
    )


def render_empty_coverage_state(diagnostics: DataDiagnostics) -> None:
    """Render zero-coverage state when CSVs load cleanly but 0 delivered orders remain."""
    _render_html(
        f"""
        <section class="unidata-alert-card unidata-alert-card--warning" aria-label="Dados sem cobertura">
            <h2 class="unidata-alert-title">Dados sem cobertura de pedidos entregues válidos</h2>
            <p class="unidata-alert-body">
                Os arquivos CSV foram validados, porém nenhum pedido entregue válido com itens e preço positivo
                permaneceu após a filtragem (<code class="unidata-mono">order_status == 'delivered'</code>).
                Nenhum valor foi fabricado para gráficos ou KPIs.
            </p>
            <ul class="unidata-alert-list unidata-tabular">
                <li>Pedidos lidos na base: <strong>{esc(format_int_pt(diagnostics.orders_total_read))}</strong></li>
                <li>Pedidos excluídos por status diferente de entregue: <strong>{esc(format_int_pt(diagnostics.orders_excluded_status))}</strong></li>
                <li>Pedidos entregues com timestamp inválido: <strong>{esc(format_int_pt(diagnostics.orders_invalid_timestamp))}</strong></li>
                <li>Pedidos entregues sem customer_unique_id válido: <strong>{esc(format_int_pt(diagnostics.orders_missing_customer))}</strong></li>
            </ul>
        </section>
        """
    )


def render_empty_filter_state(
    start_ym: str | None,
    end_ym: str | None,
    on_reset: Callable[[], None],
) -> None:
    """Render empty-filter state with clear explanation and one-click reset action."""
    start_txt = format_month_pt(start_ym) if start_ym else "Início"
    end_txt = format_month_pt(end_ym) if end_ym else "Fim"
    inverted_note = (
        " O intervalo selecionado está invertido (mês inicial posterior ao mês final)."
        if start_ym and end_ym and start_ym > end_ym
        else ""
    )

    _render_html(
        f"""
        <section class="unidata-alert-card unidata-alert-card--warning" aria-label="Filtro sem dados">
            <h2 class="unidata-alert-title">Filtro sem dados no período selecionado</h2>
            <p class="unidata-alert-body">
                Nenhum pedido entregue válido foi encontrado no recorte <strong>{esc(start_txt)}</strong> até
                <strong>{esc(end_txt)}</strong>.{esc(inverted_note)}
                Os gráficos permanecem ocultos até o retorno a um intervalo com cobertura.
            </p>
        </section>
        """
    )
    st.button(
        "Limpar filtro (voltar ao período completo)",
        key="reset_filter_empty",
        on_click=on_reset,
    )


def render_kpi_grid(kpis: KPISummary, period_label: str) -> None:
    """Render the 4 executive KPI cards in a responsive CSS grid."""
    _render_html(
        f"""
        <div id="visao-geral" class="unidata-section-head">
            <h2 class="unidata-section-title">Visão geral</h2>
            <p class="unidata-section-subtitle">
                Indicadores executivos calculados sobre pedidos entregues no período analisado ({esc(period_label)}).
            </p>
        </div>
        <div class="kpi-grid">
            <article class="kpi-card">
                <div class="kpi-label">Receita de produtos</div>
                <div class="kpi-value">{esc(format_brl(kpis.product_revenue))}</div>
                <div class="kpi-sub">Soma de price (sem frete; valores nominais em BRL)</div>
            </article>
            <article class="kpi-card">
                <div class="kpi-label">Pedidos entregues</div>
                <div class="kpi-value">{esc(format_int_pt(kpis.delivered_orders))}</div>
                <div class="kpi-sub">Pedidos distintos com status delivered</div>
            </article>
            <article class="kpi-card">
                <div class="kpi-label">Clientes únicos</div>
                <div class="kpi-value">{esc(format_int_pt(kpis.unique_customers))}</div>
                <div class="kpi-sub">Identificados via customer_unique_id</div>
            </article>
            <article class="kpi-card">
                <div class="kpi-label">Ticket médio por pedido</div>
                <div class="kpi-value">{esc(format_brl(kpis.avg_ticket))}</div>
                <div class="kpi-sub">Receita de produtos ÷ pedidos entregues</div>
            </article>
        </div>
        """
    )


def render_seasonality_section(monthly_df: pd.DataFrame, period_label: str) -> None:
    """Render monthly seasonality selector, 2D trend chart, accessible summary, and table."""
    _render_html(
        f"""
        <div id="sazonalidade" class="unidata-section-head">
            <h2 class="unidata-section-title">Sazonalidade mensal</h2>
            <p class="unidata-section-subtitle">
                Padrão histórico observado por mês calendário ({esc(period_label)}). Meses sem entregas não são preenchidos com zero.
            </p>
        </div>
        """
    )

    if monthly_df.empty:
        _render_html(
            """
            <div class="unidata-alert-card">
                <p class="unidata-alert-title">Série mensal indisponível</p>
                <p class="unidata-alert-body">Não há meses com pedidos entregues válidos no recorte atual.</p>
            </div>
            """
        )
        return

    metric_choice = st.radio(
        "Métrica da série mensal",
        options=list(MONTHLY_METRIC_OPTIONS.keys()),
        horizontal=True,
        key="monthly_metric_choice",
    )

    fig = build_monthly_trend_chart(monthly_df, metric_choice)
    st.plotly_chart(
        fig,
        width="stretch",
        theme=None,
        config=PLOTLY_CONFIG,
        alt=f"Gráfico de linha 2D mostrando {metric_choice} ao longo dos meses entregues.",
    )

    col_name, _, _, kind = MONTHLY_METRIC_OPTIONS[metric_choice]
    by_desc = monthly_df.sort_values(
        by=[col_name, "year_month"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)
    by_asc = monthly_df.sort_values(
        by=[col_name, "year_month"], ascending=[True, True], kind="mergesort"
    ).reset_index(drop=True)
    peak_row = by_desc.iloc[0]
    trough_row = by_asc.iloc[0]
    peak_val = (
        format_brl(float(peak_row[col_name]))
        if kind == "brl"
        else format_int_pt(int(peak_row[col_name]))
    )
    trough_val = (
        format_brl(float(trough_row[col_name]))
        if kind == "brl"
        else format_int_pt(int(trough_row[col_name]))
    )

    _render_html(
        f"""
        <div class="unidata-summary-box unidata-tabular">
            <strong>Resumo acessível da tendência:</strong>
            padrão histórico observado em <strong>{esc(format_int_pt(len(monthly_df)))}</strong> mês(es) com entregas no recorte
            ({esc(period_label)}). Maior marca em <strong>{esc(format_month_pt(str(peak_row['year_month'])))}</strong>
            ({esc(peak_val)}) e menor marca em <strong>{esc(format_month_pt(str(trough_row['year_month'])))}</strong>
            ({esc(trough_val)}). O comportamento histórico não constitui previsão de demanda.
        </div>
        """
    )

    table_rows = []
    for _, row in monthly_df.iterrows():
        yoy_raw = row.get("yoy_revenue_pct")
        yoy_txt = (
            format_pct_pt(float(yoy_raw))
            if yoy_raw is not None and pd.notna(yoy_raw) and math.isfinite(float(yoy_raw))
            else "—"
        )
        table_rows.append(
            {
                "Mês": f"{format_month_pt(str(row['year_month']))} ({row['year_month']})",
                "Receita de produtos (R$)": format_brl(float(row["product_revenue"])),
                "Pedidos entregues": format_int_pt(int(row["delivered_orders"])),
                "Ticket médio por pedido (R$)": format_brl(float(row["avg_ticket"])),
                "Variação YoY (%)": yoy_txt,
            }
        )

    st.table(
        pd.DataFrame(table_rows),
        border="horizontal",
        width="stretch",
        hide_index=True,
        alt="Tabela mensal de receita de produtos, pedidos entregues, ticket médio e variação YoY.",
    )


def render_customers_section(
    seg_result: SegmentationResult,
    rfm_scope_label: str,
) -> None:
    """Render RFM customer segmentation section or isolated partial K-means failure state."""
    ref_txt = (
        format_date_pt(seg_result.reference_date)
        if seg_result.reference_date is not None
        else "—"
    )
    cfg = RFMConfig()

    _render_html(
        f"""
        <div id="clientes" class="unidata-section-head">
            <h2 class="unidata-section-title">Clientes e segmentação RFM</h2>
            <p class="unidata-section-subtitle">
                Escopo RFM: <strong>{esc(rfm_scope_label)}</strong> · Data de referência: <strong>{esc(ref_txt)}</strong> ·
                Clientes únicos avaliados: <strong class="unidata-tabular">{esc(format_int_pt(seg_result.customer_count))}</strong> ·
                Modelo: K-means (k={cfg.n_clusters}, log1p em Frequência/Valor, StandardScaler, random_state={cfg.random_state}, n_init={cfg.n_init}).
            </p>
        </div>
        """
    )

    if not seg_result.ok or seg_result.cluster_summary is None or seg_result.cluster_summary.empty:
        err_msg = (
            seg_result.error_message
            or "Não foi possível formar os 4 segmentos RFM para o recorte atual."
        )
        _render_html(
            f"""
            <div class="unidata-alert-card unidata-alert-card--warning" role="status">
                <h3 class="unidata-alert-title">Segmentação RFM indisponível para este recorte</h3>
                <p class="unidata-alert-body">{esc(err_msg)}</p>
                <p class="unidata-rec-caveat">
                    Os demais indicadores do painel (KPIs executivos, sazonalidade, categorias e metodologia) permanecem disponíveis.
                </p>
            </div>
            """
        )
        return

    fig = build_segment_distribution_chart(seg_result.cluster_summary)
    st.plotly_chart(
        fig,
        width="stretch",
        theme=None,
        config=PLOTLY_CONFIG,
        alt="Gráfico de barras horizontais mostrando a participação percentual de clientes únicos em cada segmento RFM.",
    )

    table_rows = []
    for _, row in seg_result.cluster_summary.iterrows():
        table_rows.append(
            {
                "Segmento": str(row["cluster_label"]),
                "Clientes únicos": format_int_pt(int(row["customer_count"])),
                "Participação (%)": format_pct_pt(float(row["customer_pct"])),
                "Recência mediana (dias)": _format_scalar_pt(float(row["median_recency"])),
                "Frequência mediana (pedidos)": _format_scalar_pt(float(row["median_frequency"])),
                "Gasto mediano (R$)": format_brl(float(row["median_monetary"])),
                "Ticket médio (R$)": format_brl(float(row["avg_ticket"])),
            }
        )

    st.table(
        pd.DataFrame(table_rows),
        border="horizontal",
        width="stretch",
        hide_index=True,
        alt="Tabela comparativa dos segmentos RFM com clientes únicos, participação e medianas de recência, frequência e gasto.",
    )


def render_categories_section(
    categories_df: pd.DataFrame,
    period_label: str,
) -> None:
    """Render product category horizontal ranking chart and full untruncated DOM table."""
    _render_html(
        f"""
        <div id="categorias" class="unidata-section-head">
            <h2 class="unidata-section-title">Categorias de produtos</h2>
            <p class="unidata-section-subtitle">
                Ranking por receita de produtos (R$) no período ({esc(period_label)}).
                Fallback de nome: tradução (quando carregada) → categoria original → "Não informado".
            </p>
        </div>
        """
    )

    if categories_df.empty:
        _render_html(
            """
            <div class="unidata-alert-card">
                <p class="unidata-alert-title">Sem categorias no recorte atual</p>
                <p class="unidata-alert-body">Nenhum item entregue válido foi encontrado para agrupar por categoria.</p>
            </div>
            """
        )
        return

    fig = build_category_ranking_chart(categories_df, top_n=10)
    st.plotly_chart(
        fig,
        width="stretch",
        theme=None,
        config=PLOTLY_CONFIG,
        alt="Gráfico de barras horizontais com as principais categorias por receita de produtos em reais.",
    )

    display_df = categories_df if len(categories_df) <= 50 else categories_df.head(25)
    table_rows = [
        {
            "Categoria": str(row["category"]),
            "Receita de produtos (R$)": format_brl(float(row["product_revenue"])),
            "Participação (%)": format_pct_pt(float(row["revenue_share_pct"])),
            "Itens": format_int_pt(int(row["items_count"])),
            "Pedidos entregues": format_int_pt(int(row["delivered_orders"])),
        }
        for _, row in display_df.iterrows()
    ]

    st.table(
        pd.DataFrame(table_rows),
        border="horizontal",
        width="stretch",
        hide_index=True,
        alt="Tabela completa de categorias por receita de produtos, participação percentual, itens e pedidos entregues.",
    )


def render_recommendations_section(
    recs: list[Recommendation],
    seg_ok: bool,
    month_count: int,
) -> None:
    """Render deterministic explainable recommendation cards or neutral insufficient-evidence card."""
    _render_html(
        """
        <div id="recomendacoes" class="unidata-section-head">
            <h2 class="unidata-section-title">Recomendações explicáveis</h2>
            <p class="unidata-section-subtitle">
                Ações sugeridas com cautela a partir de evidências numéricas observadas e ressalva não causal.
            </p>
        </div>
        """
    )

    if not recs:
        _render_html(
            """
            <div class="unidata-alert-card" role="status">
                <h3 class="unidata-alert-title">Recomendação insuficiente</h3>
                <p class="unidata-alert-body">
                    Não há evidência quantitativa suficiente no recorte atual para emitir recomendações
                    determinísticas sem especulação (exige variação mensal, segmentos RFM válidos ou receita positiva por categoria).
                </p>
            </div>
            """
        )
        return

    cards_html = []
    for rec in recs:
        cards_html.append(
            f"""
            <article class="unidata-rec-card">
                <div class="unidata-rec-meta">
                    <span class="unidata-rec-cat">{esc(rec.category)}</span>
                    <span class="unidata-rec-period">{esc(rec.period)}</span>
                </div>
                <h3 class="unidata-rec-title">{esc(rec.title)}</h3>
                <p class="unidata-rec-obs">{esc(rec.observation)}</p>
                <div class="unidata-rec-evidence"><strong>Evidência:</strong> {esc(rec.evidence)}</div>
                <p class="unidata-rec-caveat"><strong>Ressalva:</strong> {esc(rec.caveat)}</p>
            </article>
            """
        )

    _render_html(f"<div class='unidata-rec-grid'>{''.join(cards_html)}</div>")

    omitted_notes: list[str] = []
    if not seg_ok:
        omitted_notes.append("Clientes (segmentação RFM indisponível no recorte)")
    if month_count < 2:
        omitted_notes.append("Sazonalidade (são necessários ao menos 2 meses distintos)")
    if omitted_notes:
        _render_html(
            f"""
            <p class="unidata-nominal-note">
                Pilares sem recomendação emitida neste recorte por insuficiência de evidência: {esc('; '.join(omitted_notes))}.
            </p>
            """
        )


def render_methodology_section(
    diagnostics: DataDiagnostics | None,
    seg_result: SegmentationResult | None,
    data_dir: Path,
) -> None:
    """Render persistent Methodology, Provenance, CC BY-NC-SA 4.0, and Data Diagnostics section."""
    del seg_result
    cfg = RFMConfig()

    st.markdown("<div id='sobre-os-dados'></div>", unsafe_allow_html=True)
    with st.expander("Sobre os dados, Metodologia e Diagnóstico de Qualidade", expanded=False):
        st.markdown(
            f"""
            **Proveniência e Licença**
            - **Base de dados:** {DATASET_NAME} ([Kaggle]({KAGGLE_DATASET_URL})).
            - **Licença:** [{DATASET_LICENSE}]({DATASET_LICENSE_URL}) — **uso exclusivamente não comercial** (projeto acadêmico).
            - **Nota metodológica:** {PROVENANCE_NOTE_PT}

            **Regras Analíticas e Modelagem**
            - **Universo:** exclusivamente pedidos com `order_status == 'delivered'` e timestamp de compra válido.
            - **Receita de produtos:** soma de `price` em `olist_order_items_dataset.csv` (exclui frete e nunca soma linhas de `order_payments`).
            - **Clientes únicos:** contagem e agregação RFM por `customer_unique_id` (deduplicando `customer_id`).
            - **Ticket médio por pedido:** `Receita de produtos ÷ Pedidos entregues`.
            - **Sazonalidade:** agrupamento cronológico por mês calendário (`YYYY-MM`), sem imputação de zeros em lacunas.
            - **Segmentação RFM e K-means:** cálculo de Recência (em dias até a última compra entregue do escopo), Frequência (`nunique(order_id)`) e Valor Monetário (`sum(price)`), com transformação `log1p` em Frequência e Valor, padronização via `StandardScaler` e agrupamento `KMeans` com `k={cfg.n_clusters}`, `random_state={cfg.random_state}` e `n_init={cfg.n_init}`.

            **Limitações**
            - Os resultados descrevem um padrão histórico observado no marketplace Olist; não estabelecem causalidade e não realizam previsão de demanda futura.
            - Valores em BRL são nominais (sem deflação) e restritos aos registros locais carregados de `{data_dir.name or str(data_dir)}`.
            """
        )

        if diagnostics is not None:
            if diagnostics.translation_loaded:
                trans_status = (
                    "Tradução de categorias: **carregada** "
                    "(`product_category_name_translation.csv`)."
                )
            else:
                trans_status = (
                    "Tradução de categorias: **ausente** "
                    "(`product_category_name_translation.csv` não encontrado; exibindo nomes originais em português ou `Não informado`)."
                )
            st.markdown(f"**Status da tradução opcional:** {trans_status}")

            diag_rows = [
                {
                    "Indicador de diagnóstico": "Pedidos lidos na base",
                    "Contagem": format_int_pt(diagnostics.orders_total_read),
                },
                {
                    "Indicador de diagnóstico": "Pedidos entregues válidos (escopo exibido)",
                    "Contagem": format_int_pt(diagnostics.orders_delivered),
                },
                {
                    "Indicador de diagnóstico": "Pedidos excluídos por status",
                    "Contagem": format_int_pt(diagnostics.orders_excluded_status),
                },
                {
                    "Indicador de diagnóstico": "Pedidos com timestamp inválido",
                    "Contagem": format_int_pt(diagnostics.orders_invalid_timestamp),
                },
                {
                    "Indicador de diagnóstico": "Pedidos sem customer_unique_id",
                    "Contagem": format_int_pt(diagnostics.orders_missing_customer),
                },
                {
                    "Indicador de diagnóstico": "Itens lidos na base",
                    "Contagem": format_int_pt(diagnostics.items_total_read),
                },
                {
                    "Indicador de diagnóstico": "Itens em pedidos entregues",
                    "Contagem": format_int_pt(diagnostics.items_in_delivered_orders),
                },
                {
                    "Indicador de diagnóstico": "Itens descartados por preço ou chave inválida",
                    "Contagem": format_int_pt(diagnostics.items_dropped_invalid_price_or_key),
                },
                {
                    "Indicador de diagnóstico": "Clientes únicos entregues (escopo exibido)",
                    "Contagem": format_int_pt(diagnostics.unique_customers_delivered),
                },
                {
                    "Indicador de diagnóstico": "Itens sem categoria informada",
                    "Contagem": format_int_pt(diagnostics.items_missing_category),
                },
            ]
            st.table(
                pd.DataFrame(diag_rows),
                border="horizontal",
                width="stretch",
                hide_index=True,
                alt="Tabela de diagnóstico de qualidade dos dados com contagens lidas, entregues e excluídas.",
            )

            if diagnostics.warnings:
                st.markdown("**Avisos de qualidade registrados durante o pipeline:**")
                for warn_msg in diagnostics.warnings:
                    st.markdown(f"- {warn_msg}")
