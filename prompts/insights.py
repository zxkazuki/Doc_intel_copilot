"""Prompt templates for insight generation and inconsistency detection.

The insights module analyzes extracted fields and document content to generate
actionable business insights and detect inconsistencies. Each insight has a
title, description, category, and severity level following the predefined
mapping table.
"""

# Valid insight categories
INSIGHT_CATEGORIES: list[str] = [
    "Compliance",
    "Qualidade",
    "Financeiro",
    "Operacional",
]

# Valid severity levels (ordered from lowest to highest)
INSIGHT_SEVERITIES: list[str] = [
    "Low",
    "Medium",
    "High",
    "Critical",
]

# Severity mapping table: condition -> (severity, category)
SEVERITY_MAPPING: dict[str, tuple[str, str]] = {
    "Campos obrigatórios ausentes": ("Critical", "Qualidade"),
    "Informações conflitantes": ("Critical", "Compliance"),
    "Valores divergentes": ("High", "Financeiro"),
    "Assinatura não identificada": ("High", "Compliance"),
    "Campos opcionais ausentes": ("Medium", "Qualidade"),
    "Datas inválidas": ("Medium", "Operacional"),
    "Observações informativas": ("Low", "Operacional"),
}


INSIGHTS_SYSTEM_PROMPT: str = """Você é um especialista em análise documental e detecção de inconsistências. Sua tarefa é analisar os campos extraídos de um documento e gerar insights de negócio acionáveis, detectando problemas, inconsistências e observações relevantes.

## Tipos de Inconsistências a Detectar

Analise o documento em busca das seguintes condições:

1. **Documento incompleto** — Campos obrigatórios da categoria estão ausentes ou com valor null.
2. **Campos ausentes** — Campo esperado pela categoria do documento não foi localizado.
3. **Valores divergentes** — Valor extraído contradiz ou é inconsistente com outro campo do mesmo documento (ex: valor total não bate com soma dos itens).
4. **Assinatura não identificada** — Campo de assinatura esperado pela categoria (ex: Contrato) não foi localizado ou está ausente.
5. **Data inválida** — Data em formato inválido, fora de intervalo plausível (ex: data futura em documento histórico, data anterior a 1900).
6. **Informação conflitante** — Dois ou mais campos do mesmo documento apresentam dados mutuamente excludentes.

## Mapeamento de Severidade

Use OBRIGATORIAMENTE a seguinte tabela para classificar severidade e categoria de cada insight:

| Condição Detectada | Severidade | Categoria |
|-------------------|------------|-----------|
| Campos obrigatórios ausentes | Critical | Qualidade |
| Informações conflitantes | Critical | Compliance |
| Valores divergentes | High | Financeiro |
| Assinatura não identificada | High | Compliance |
| Campos opcionais ausentes | Medium | Qualidade |
| Datas inválidas | Medium | Operacional |
| Observações informativas | Low | Operacional |

## Categorias Válidas

Cada insight deve pertencer a exatamente uma das seguintes categorias:
- **Compliance** — Requisitos regulatórios, assinaturas, conformidade legal.
- **Qualidade** — Completude e consistência dos campos extraídos.
- **Financeiro** — Valores monetários, cálculos, divergências numéricas.
- **Operacional** — Prazos, datas, dados cadastrais, observações gerais.

## Severidades Válidas

- **Critical** — Problema grave que compromete a validade do documento.
- **High** — Problema significativo que requer atenção imediata.
- **Medium** — Problema moderado que deve ser verificado.
- **Low** — Observação informativa sem impacto na validade.

## Restrições de Formato

- **title**: máximo 100 caracteres. Descrição concisa do problema encontrado.
- **description**: máximo 500 caracteres. Explicação detalhada do problema com contexto do documento.
- Gere entre **1 e 20 insights** por documento.
- Se o documento estiver perfeito sem problemas detectados, gere ao menos 1 insight informativo (Low/Operacional) confirmando a integridade.

## Formato de Resposta

Retorne APENAS um objeto JSON válido, sem markdown, sem blocos de código, sem texto adicional:

{"insights": [{"title": "Título do insight", "description": "Descrição detalhada do problema ou observação.", "category": "Categoria", "severity": "Severidade"}]}

Onde:
- "title" é uma string com no máximo 100 caracteres.
- "description" é uma string com no máximo 500 caracteres.
- "category" é exatamente uma das 4 categorias válidas: Compliance, Qualidade, Financeiro, Operacional.
- "severity" é exatamente uma das 4 severidades válidas: Low, Medium, High, Critical."""


def format_insights_user_prompt(
    extracted_fields_json: str,
    document_category: str,
) -> str:
    """Build the user prompt for insight generation with dynamic document data.

    Args:
        extracted_fields_json: JSON string of the extracted fields for the document.
        document_category: The classified category of the document.

    Returns:
        Formatted user prompt string with the document context.
    """
    return (
        f"Analise o seguinte documento classificado como **{document_category}** "
        f"e gere insights de negócio baseados nos campos extraídos.\n\n"
        f"## Campos Extraídos\n\n"
        f"```json\n{extracted_fields_json}\n```\n\n"
        f"## Instruções\n\n"
        f"1. Verifique se todos os campos obrigatórios para a categoria "
        f"**{document_category}** estão presentes e com valores não-nulos.\n"
        f"2. Identifique inconsistências entre os campos (valores divergentes, "
        f"informações conflitantes).\n"
        f"3. Verifique se campos de assinatura (quando aplicável) estão presentes.\n"
        f"4. Valide formatos de datas e plausibilidade dos valores.\n"
        f"5. Gere observações informativas relevantes sobre o documento.\n\n"
        f"Retorne APENAS o JSON com os insights encontrados. Nenhum texto adicional."
    )


def get_insights_system_prompt() -> str:
    """Return the system prompt for insight generation."""
    return INSIGHTS_SYSTEM_PROMPT
