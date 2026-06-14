"""Geração de laudo de revisão por IA."""

from dataclasses import dataclass

from infrastructure.bedrock_client import invoke_claude_text
from modules.history import get_document_detail


@dataclass
class LaudoResult:
    success: bool
    content: str = ""
    error_message: str | None = None


LAUDO_SYSTEM_PROMPT = """Você é um analista sênior de revisão documental. Sua tarefa é redigir um laudo técnico de revisão formal e objetivo sobre um documento processado, justificando a recomendação de APROVAÇÃO ou RECUSA.

O laudo deve conter:
1. **Identificação do Documento** — nome, categoria e status
2. **Resumo da Análise** — visão geral dos dados extraídos
3. **Inconsistências e Alertas** — análise dos insights detectados, com foco em itens de severidade Critical e High
4. **Recomendação** — APROVAÇÃO ou RECUSA, claramente justificada com base nos dados e inconsistências
5. **Observações Finais** — recomendações de ação

Escreva em português formal, tom técnico-jurídico, estruturado com títulos em markdown. Seja conciso porém completo."""


def _format_field(field: dict) -> str:
    """Format a single extracted field as a readable line."""
    name = field.get("name") or "(campo sem nome)"
    value = field.get("value") or "(não informado)"
    confidence = str(field.get("confidence") or "desconhecida")
    return f"- {name}: {value} (confiança: {confidence})"


def _format_insight(insight: dict) -> str:
    """Format a single insight as a readable block."""
    title = insight.get("title") or "(insight sem título)"
    severity = str(insight.get("severity") or "desconhecida")
    category = str(insight.get("category") or "desconhecida")
    description = insight.get("description") or "(sem descrição)"
    return f"- [{severity}] {title} (categoria: {category})\n  {description}"


def _build_laudo_prompt(detail: dict) -> str:
    """Build the user prompt with the document context for the laudo."""
    document = detail.get("document") or {}
    extraction = detail.get("extraction") or {}
    insights = detail.get("insights") or []
    fields = extraction.get("fields") or []

    file_name = document.get("file_name") or "(desconhecido)"
    category = document.get("category") or "(não classificado)"
    status = document.get("status") or "(sem status)"

    fields_section = (
        "\n".join(_format_field(f) for f in fields)
        if fields
        else "(nenhum campo extraído)"
    )
    insights_section = (
        "\n".join(_format_insight(i) for i in insights)
        if insights
        else "(nenhum insight detectado)"
    )

    return (
        "Redija o laudo de revisão para o documento a seguir.\n\n"
        "## Metadados do Documento\n"
        f"- Nome do arquivo: {file_name}\n"
        f"- Categoria: {category}\n"
        f"- Status: {status}\n\n"
        "## Campos Extraídos\n"
        f"{fields_section}\n\n"
        "## Insights Detectados\n"
        f"{insights_section}\n"
    )


def generate_laudo(document_id: str, decision: str = "") -> LaudoResult:
    """Gera um laudo de revisão por IA para o documento.

    Args:
        document_id: ID do documento.
        decision: recomendação opcional do revisor ("aprovação"/"recusa") para orientar o laudo.
    """
    detail = get_document_detail(document_id)
    if not detail:
        return LaudoResult(success=False, error_message="Documento não encontrado.")

    prompt = _build_laudo_prompt(detail)
    if decision:
        prompt += f"\n\nO revisor indicou a seguinte decisão preliminar: {decision}. Construa o laudo coerente com essa decisão, a menos que os dados contradigam fortemente."

    try:
        content = invoke_claude_text(prompt=prompt, system=LAUDO_SYSTEM_PROMPT, max_tokens=2048)
    except Exception as e:
        return LaudoResult(success=False, error_message=f"Erro ao gerar laudo: {e}")

    if not content:
        return LaudoResult(success=False, error_message="Falha ao gerar laudo (resposta vazia).")

    return LaudoResult(success=True, content=content)
