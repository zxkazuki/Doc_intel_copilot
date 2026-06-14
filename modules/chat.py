"""Agente de chat por IA para conversar sobre documentos e laudos."""

from infrastructure.bedrock_client import invoke_claude_text
from modules.history import get_document_detail

CHAT_SYSTEM_TEMPLATE = """Você é um assistente especializado em análise documental do Document Intelligence Copilot. Você ajuda revisores a entender documentos processados, seus dados extraídos, inconsistências detectadas (insights), histórico de revisões e laudos.

Responda de forma clara, objetiva e em português. Baseie-se EXCLUSIVAMENTE no contexto do documento fornecido abaixo. Se a pergunta for sobre algo que não está no contexto, diga que não há essa informação no documento.

## CONTEXTO DO DOCUMENTO

{context}
"""


def _stringify(value: object) -> str:
    """Converte um valor em texto seguro, tratando None de forma amigável."""
    if value is None:
        return "—"
    text = str(value).strip()
    return text if text else "—"


def _format_metadata(document: dict) -> str:
    """Formata os metadados principais do documento."""
    return (
        "### Metadados\n"
        f"- Arquivo: {_stringify(document.get('file_name'))}\n"
        f"- Categoria: {_stringify(document.get('category'))}\n"
        f"- Status: {_stringify(document.get('status'))}"
    )


def _format_fields(extraction: dict | None) -> str:
    """Formata os campos extraídos como 'nome: valor (confiança)'."""
    fields = (extraction or {}).get("fields", []) or []
    if not fields:
        return "### Dados Extraídos\n- Nenhum campo extraído."

    lines = ["### Dados Extraídos"]
    for field in fields:
        name = _stringify(field.get("name"))
        value = _stringify(field.get("value"))
        confidence = _stringify(field.get("confidence"))
        lines.append(f"- {name}: {value} (confiança: {confidence})")
    return "\n".join(lines)


def _format_insights(insights: list[dict] | None) -> str:
    """Formata os insights como 'título — severidade — categoria: descrição'."""
    insights = insights or []
    if not insights:
        return "### Insights\n- Nenhum insight gerado."

    lines = ["### Insights"]
    for insight in insights:
        title = _stringify(insight.get("title"))
        severity = _stringify(insight.get("severity"))
        category = _stringify(insight.get("category"))
        description = _stringify(insight.get("description"))
        lines.append(f"- {title} — {severity} — {category}: {description}")
    return "\n".join(lines)


def _format_reviews(reviews: list[dict] | None) -> str:
    """Formata o histórico de revisões humanas."""
    reviews = reviews or []
    if not reviews:
        return "### Histórico de Revisões\n- Nenhuma revisão registrada."

    ordered = sorted(reviews, key=lambda r: _stringify(r.get("timestamp")))
    lines = ["### Histórico de Revisões"]
    for review in ordered:
        action = _stringify(review.get("action"))
        reviewer = _stringify(review.get("reviewer_id"))
        timestamp = _stringify(review.get("timestamp"))
        entry = f"- [{timestamp}] {action} por {reviewer}"

        field_name = review.get("field_name")
        if field_name:
            original = _stringify(review.get("original_value"))
            new_value = _stringify(review.get("new_value"))
            entry += f" — campo '{_stringify(field_name)}': '{original}' → '{new_value}'"
        lines.append(entry)
    return "\n".join(lines)


def _format_laudo(laudo_text: str) -> str:
    """Formata o laudo opcional, retornando vazio quando não há conteúdo."""
    text = (laudo_text or "").strip()
    return f"### Laudo\n{text}" if text else ""


def build_document_context(document_id: str, laudo_text: str = "") -> str:
    """Monta o contexto textual do documento (campos, insights, revisões, laudo)."""
    detail = get_document_detail(document_id)
    if not detail:
        return ""

    sections = [
        _format_metadata(detail.get("document", {}) or {}),
        _format_fields(detail.get("extraction")),
        _format_insights(detail.get("insights")),
        _format_reviews(detail.get("reviews")),
    ]

    laudo_section = _format_laudo(laudo_text)
    if laudo_section:
        sections.append(laudo_section)

    return "\n\n".join(sections)


def chat_with_agent(
    document_id: str,
    history: list[dict],
    laudo_text: str = "",
) -> str:
    """Conversa com o agente sobre o documento.

    Args:
        document_id: documento em contexto.
        history: lista de mensagens [{"role": "user"|"assistant", "content": str}].
        laudo_text: laudo opcional para enriquecer o contexto.

    Returns:
        Resposta do agente como texto. Retorna mensagem de erro amigável em caso de falha.
    """
    if not history:
        return "Envie uma pergunta para iniciar a conversa."

    context = build_document_context(document_id, laudo_text)
    if not context:
        return "Não foi possível carregar o contexto do documento."

    system = CHAT_SYSTEM_TEMPLATE.format(context=context)

    try:
        response = invoke_claude_text(
            system=system, messages=history, prompt="", max_tokens=2048
        )
    except Exception as e:
        return f"Erro ao consultar o agente: {e}"

    return response or "Não consegui gerar uma resposta. Tente reformular a pergunta."
