"""Detalhes do Documento — visualização completa de extração, insights, alertas e revisões."""

import streamlit as st
import pandas as pd

from modules.history import get_document_history, get_document_detail, HistoryFilters
from infrastructure.s3_client import generate_presigned_url


def _to_float(value) -> float:
    """Safely convert a value (str/Decimal/float/None) to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


SEVERITY_EMOJI = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}

STATUS_BADGES = {
    "uploaded": "🔵 Enviado",
    "classifying": "🔵 Classificando",
    "classified": "🔵 Classificado",
    "extracting": "🔵 Extraindo",
    "extracted": "🔵 Extraído",
    "generating_insights": "🔵 Gerando Insights",
    "pending_review": "🟡 Aguardando Revisão",
    "approved": "🟢 Aprovado",
    "rejected": "🔴 Rejeitado",
    "classification_error": "❌ Erro na Classificação",
    "extraction_error": "❌ Erro na Extração",
    "insights_error": "❌ Erro nos Insights",
}

ACTION_LABELS = {"approve": "✅ Aprovação", "reject": "❌ Rejeição", "correction": "✏️ Correção"}


def _render_header(document: dict) -> None:
    """Renderiza cabeçalho com nome do arquivo, categoria e status."""
    file_name = document.get("file_name", "Documento")
    category = document.get("category", "—")
    status = document.get("status", "—")
    status_label = STATUS_BADGES.get(status, status)

    st.title(f"🔍 {file_name}")
    col1, col2 = st.columns(2)
    col1.markdown(f"**Categoria:** `{category}`")
    col2.markdown(f"**Status:** {status_label}")


def _render_document_viewer(document: dict) -> None:
    """Renderiza o documento original (PDF via iframe, imagens via st.image)."""
    st.subheader("📄 Documento Original")

    s3_key = document.get("s3_key")
    if not s3_key:
        st.warning("Chave S3 do documento não disponível.")
        return

    presigned_url = generate_presigned_url(s3_key)
    if not presigned_url:
        st.error("Não foi possível gerar URL de acesso ao documento.")
        return

    file_format = document.get("file_format", "").lower()
    match file_format:
        case "pdf":
            st.markdown(
                f'<iframe src="{presigned_url}" width="100%" height="600" '
                f'frameborder="0"></iframe>',
                unsafe_allow_html=True,
            )
        case "png" | "jpg" | "jpeg":
            st.image(presigned_url, use_container_width=True)
        case _:
            st.info(f"Formato '{file_format}' sem visualização disponível.")


def _render_extraction_table(extraction: dict | None) -> None:
    """Renderiza tabela de campos extraídos (Campo, Valor, Confiança)."""
    st.subheader("📋 Extração Estruturada")

    if not extraction:
        st.info("Nenhuma extração disponível para este documento.")
        return

    fields = extraction.get("fields", [])
    if not fields:
        st.info("Nenhum campo extraído.")
        return

    rows = [
        {
            "Campo": f.get("name", "—"),
            "Valor": f.get("value") or "—",
            "Confiança": f"{_to_float(f.get('confidence', 0)):.0%}",
        }
        for f in fields
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_insights(insights: list[dict]) -> None:
    """Renderiza seção de insights com emoji de severidade."""
    st.subheader("💡 Insights")

    if not insights:
        st.info("Nenhum insight gerado para este documento.")
        return

    for insight in insights:
        severity = insight.get("severity", "Low")
        emoji = SEVERITY_EMOJI.get(severity, "⚪")
        title = insight.get("title", "Sem título")
        description = insight.get("description", "")

        st.markdown(f"{emoji} **{title}**")
        if description:
            st.caption(description)


def _render_alerts(insights: list[dict]) -> None:
    """Renderiza alertas Critical/High com destaque visual."""
    st.subheader("🚨 Alertas")

    alerts = [i for i in insights if i.get("severity") in ("Critical", "High")]
    if not alerts:
        st.info("Nenhum alerta de alta severidade para este documento.")
        return

    # Critical first, then High
    alerts.sort(key=lambda a: 0 if a.get("severity") == "Critical" else 1)

    for alert in alerts:
        severity = alert.get("severity", "High")
        title = alert.get("title", "Sem título")
        description = alert.get("description", "")

        if severity == "Critical":
            st.error(f"🔴 **{title}**\n\n{description}")
        else:
            st.warning(f"🟠 **{title}**\n\n{description}")


def _render_review_history(reviews: list[dict]) -> None:
    """Renderiza timeline de revisões em ordem cronológica."""
    st.subheader("📝 Histórico de Revisões")

    if not reviews:
        st.info("Nenhuma revisão realizada para este documento.")
        return

    sorted_reviews = sorted(reviews, key=lambda r: r.get("timestamp", ""))

    for review in sorted_reviews:
        action = review.get("action", "—")
        reviewer = review.get("reviewer_id", "Desconhecido")
        timestamp = review.get("timestamp", "—")
        action_label = ACTION_LABELS.get(action, action)

        st.markdown(f"**{action_label}** — {reviewer} em `{timestamp}`")

        if action == "correction" and (field_name := review.get("field_name")):
            original = review.get("original_value") or "—"
            new = review.get("new_value") or "—"
            st.markdown(f"  Campo: **{field_name}** · `{original}` → `{new}`")

        st.divider()


def _render_navigation(status: str, document_id: str) -> None:
    """Renderiza botões de navegação e ação de revisão."""
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← Voltar ao Histórico"):
            st.switch_page("pages/3_📋_Historico.py")

    with col2:
        if st.button("← Dashboard"):
            st.switch_page("pages/2_📊_Dashboard.py")

    with col3:
        if status == "pending_review":
            if st.button("Ir para Revisão", type="primary"):
                st.query_params["document_id"] = document_id
                st.switch_page("pages/5_✅_Revisao.py")


def main() -> None:
    """Entry point da página de Detalhes."""
    st.set_page_config(page_title="Detalhes", page_icon="🔍", layout="wide")

    document_id = st.query_params.get("document_id")

    if not document_id:
        documents = get_document_history(HistoryFilters(page_size=100)).items
        if not documents:
            st.info("Nenhum documento processado ainda.")
            return

        options = {
            doc["document_id"]: f"{doc.get('file_name', 'Documento')} "
            f"({doc.get('category', '—')})"
            for doc in documents
        }
        document_id = st.selectbox(
            "Selecione um documento",
            options=list(options.keys()),
            format_func=lambda doc_id: options[doc_id],
        )

    data = get_document_detail(document_id)
    if data is None:
        st.error("Documento não encontrado.")
        if st.button("← Voltar ao Histórico"):
            st.switch_page("pages/3_📋_Historico.py")
        return

    document = data.get("document", {})
    extraction = data.get("extraction")
    insights = data.get("insights", [])
    reviews = data.get("reviews", [])
    status = document.get("status", "")

    _render_header(document)
    st.divider()
    _render_navigation(status, document_id)
    st.divider()
    _render_document_viewer(document)
    st.divider()
    _render_extraction_table(extraction)
    st.divider()
    _render_insights(insights)
    st.divider()
    _render_alerts(insights)
    st.divider()
    _render_review_history(reviews)


main()
