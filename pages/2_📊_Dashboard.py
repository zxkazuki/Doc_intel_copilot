"""Página Dashboard — KPIs, insights por categoria, alertas e documentos recentes."""

import streamlit as st
import pandas as pd

from modules.dashboard import get_dashboard_data, DashboardData, VALID_CATEGORIES
from modules.history import get_document_history, get_document_detail, HistoryFilters


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


SEVERITY_EMOJI: dict[str, str] = {
    "Critical": "🔴",
    "High": "🟠",
    "Medium": "🟡",
    "Low": "🟢",
}

SEVERITY_COLOR: dict[str, str] = {
    "Critical": "red",
    "High": "orange",
    "Medium": "yellow",
    "Low": "green",
}


def _is_empty(data: DashboardData) -> bool:
    """Verifica se não há dados no dashboard."""
    return (
        data.kpis.total_processed == 0
        and data.kpis.pending_documents == 0
        and data.kpis.pending_reviews == 0
        and data.kpis.critical_alerts == 0
        and not data.recent_documents
    )


def _render_kpis(data: DashboardData) -> None:
    """Renderiza linha de KPIs."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Processado", data.kpis.total_processed)
    col2.metric("Documentos Pendentes", data.kpis.pending_documents)
    col3.metric("Revisões Pendentes", data.kpis.pending_reviews)
    col4.metric("Alertas Críticos", data.kpis.critical_alerts)


def _render_insights_by_category(data: DashboardData) -> None:
    """Renderiza insights agrupados por categoria em tabs (max 5 cada)."""
    st.subheader("📋 Insights por Categoria")
    tabs = st.tabs(VALID_CATEGORIES)

    for tab, category in zip(tabs, VALID_CATEGORIES):
        with tab:
            insights = data.insights_by_category.get(category, [])
            if not insights:
                st.info(f"Nenhum insight na categoria {category}.")
                continue
            for insight in insights:
                severity = insight.get("severity", "Low")
                title = insight.get("title", "Sem título")
                description = insight.get("description", "")
                color = SEVERITY_COLOR.get(severity, "gray")
                st.markdown(f":{color}[{severity}] **{title}**")
                if description:
                    st.caption(description)
                st.divider()


def _render_document_insights_selector() -> None:
    """Renderiza seletor de documento e exibe os insights do documento escolhido."""
    st.subheader("🔍 Insights por Documento")

    documents = get_document_history(HistoryFilters(page_size=100)).items
    if not documents:
        st.info("Nenhum documento disponível.")
        return

    labels = {
        doc.get("document_id"): f"{doc.get('file_name', '—')} ({doc.get('category', '—')})"
        for doc in documents
    }

    selected_id = st.selectbox(
        "Selecione um documento",
        options=list(labels),
        format_func=lambda doc_id: labels.get(doc_id, doc_id),
    )

    if not selected_id:
        return

    detail = get_document_detail(selected_id)
    insights = detail.get("insights", []) if detail else []
    if not insights:
        st.info("Nenhum insight para este documento.")
        return

    for insight in insights:
        severity = insight.get("severity", "Low")
        emoji = SEVERITY_EMOJI.get(severity, "⚪")
        title = insight.get("title", "Sem título")
        description = insight.get("description", "")
        st.markdown(f"{emoji} **{title}** — _{severity}_")
        if description:
            st.caption(description)


def _render_alerts(data: DashboardData) -> None:
    """Renderiza lista de alertas (max 20, Critical primeiro)."""
    st.subheader("🚨 Alertas")
    if not data.alerts:
        st.info("Nenhum alerta ativo.")
        return

    for alert in data.alerts:
        severity = alert.get("severity", "Low")
        emoji = SEVERITY_EMOJI.get(severity, "⚪")
        title = alert.get("title", "Sem título")
        description = alert.get("description", "")
        st.markdown(f"{emoji} **{title}** — _{severity}_")
        if description:
            st.caption(description)


def _render_recent_documents(data: DashboardData) -> None:
    """Renderiza tabela com os 10 últimos documentos processados."""
    st.subheader("📄 Documentos Recentes")
    if not data.recent_documents:
        st.info("Nenhum documento processado recentemente.")
        return

    rows = [
        {
            "Arquivo": doc.get("file_name", "—"),
            "Categoria": doc.get("category", "—"),
            "Status": doc.get("status", "—"),
            "Processado em": doc.get("processed_at", "—"),
        }
        for doc in data.recent_documents
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def main() -> None:
    """Entry point da página Dashboard."""
    st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
    st.title("📊 Dashboard Operacional")

    data = get_dashboard_data()

    if _is_empty(data):
        st.info(
            "Nenhum documento processado ainda. "
            "Envie seu primeiro documento na página de Upload."
        )
        return

    _render_kpis(data)
    st.divider()
    _render_insights_by_category(data)
    st.divider()
    _render_document_insights_selector()
    st.divider()
    _render_alerts(data)
    st.divider()
    _render_recent_documents(data)


main()
