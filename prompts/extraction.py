"""Prompt templates for structured field extraction by document category.

Each category has a specific set of expected fields (from EXTRACTION_SCHEMAS).
The generic category instructs the model to find up to 10 key-value pairs.
All prompts instruct Claude to return a JSON object with a "fields" array
of {name, value, confidence} entries.
"""

# Schema defining expected fields per document category
EXTRACTION_SCHEMAS: dict[str, list[str]] = {
    "Contrato": ["Partes", "Valor", "Prazo", "Assinaturas"],
    "Laudo Médico": ["Paciente", "CRM", "CID", "Medicamentos"],
    "Extrato Bancário": ["Banco", "Conta", "Datas", "Valores"],
    "Ficha Cadastral": [
        "Nome Completo",
        "CPF",
        "Data de Nascimento",
        "Endereço",
        "Telefone",
    ],
    "Nota Fiscal": [
        "Emitente",
        "CNPJ",
        "Número da Nota",
        "Itens",
        "Valor Total",
        "Data de Emissão",
    ],
    "Documento Genérico": [],
}


EXTRACTION_SYSTEM_PROMPT: str = (
    "Você é um especialista em extração de campos estruturados de documentos. "
    "Sua tarefa é analisar o conteúdo do documento fornecido e extrair os campos "
    "solicitados com precisão. Para cada campo, atribua um score de confiança entre "
    "0.0 e 1.0 indicando quão certo você está de que o valor extraído está correto.\n\n"
    "Regras de confiança:\n"
    "- 0.9–1.0: Valor claramente visível e legível no documento.\n"
    "- 0.7–0.89: Valor presente mas parcialmente legível ou inferido do contexto.\n"
    "- 0.5–0.69: Valor incerto, pode haver ambiguidade.\n"
    "- 0.0: Campo não encontrado no documento — use value=null.\n\n"
    "Retorne SOMENTE um objeto JSON válido, sem texto adicional."
)


def _build_specific_category_prompt(category: str, fields: list[str]) -> str:
    """Build a user prompt for a specific (non-generic) document category."""
    fields_list = "\n".join(f"- {field}" for field in fields)
    return (
        f"O documento a seguir foi classificado como **{category}**.\n\n"
        f"Extraia EXATAMENTE os seguintes campos:\n{fields_list}\n\n"
        "Para cada campo, retorne:\n"
        '- "name": o nome exato do campo conforme listado acima\n'
        '- "value": o valor extraído do documento (string) ou null se não encontrado\n'
        '- "confidence": score de confiança entre 0.0 e 1.0\n\n'
        "Se um campo não for encontrado no documento, defina value como null e "
        "confidence como 0.0.\n\n"
        "Retorne o resultado no seguinte formato JSON:\n"
        "```json\n"
        '{\n  "fields": [\n'
        '    {"name": "NomeCampo", "value": "valor extraído", "confidence": 0.95},\n'
        '    {"name": "OutroCampo", "value": null, "confidence": 0.0}\n'
        "  ]\n}\n"
        "```\n\n"
        "IMPORTANTE: Retorne SOMENTE o JSON, sem explicações ou texto adicional."
    )


_GENERIC_CATEGORY_PROMPT: str = (
    "O documento a seguir foi classificado como **Documento Genérico**.\n\n"
    "Analise o conteúdo e identifique até 10 pares chave-valor relevantes "
    "presentes no documento. Priorize informações mais importantes como "
    "nomes, datas, valores monetários, identificadores e dados de contato.\n\n"
    "Para cada par encontrado, retorne:\n"
    '- "name": nome descritivo do campo identificado\n'
    '- "value": o valor extraído do documento (string) ou null se ilegível\n'
    '- "confidence": score de confiança entre 0.0 e 1.0\n\n'
    "Regras:\n"
    "- Extraia NO MÁXIMO 10 campos.\n"
    "- Se um valor for ilegível, defina value como null e confidence como 0.0.\n"
    "- Priorize campos com maior relevância e legibilidade.\n\n"
    "Retorne o resultado no seguinte formato JSON:\n"
    "```json\n"
    '{\n  "fields": [\n'
    '    {"name": "Campo Identificado", "value": "valor encontrado", "confidence": 0.92},\n'
    '    {"name": "Outro Campo", "value": null, "confidence": 0.0}\n'
    "  ]\n}\n"
    "```\n\n"
    "IMPORTANTE: Retorne SOMENTE o JSON, sem explicações ou texto adicional."
)


def get_extraction_prompt(category: str) -> str:
    """Return the user prompt for field extraction based on document category.

    Args:
        category: The document category (must be a key in EXTRACTION_SCHEMAS).

    Returns:
        The formatted user prompt string for the given category.

    Raises:
        ValueError: If category is not recognized.
    """
    if category not in EXTRACTION_SCHEMAS:
        raise ValueError(
            f"Categoria desconhecida: '{category}'. "
            f"Categorias válidas: {list(EXTRACTION_SCHEMAS.keys())}"
        )

    if category == "Documento Genérico":
        return _GENERIC_CATEGORY_PROMPT

    return _build_specific_category_prompt(category, EXTRACTION_SCHEMAS[category])


def get_extraction_system_prompt() -> str:
    """Return the system prompt for field extraction."""
    return EXTRACTION_SYSTEM_PROMPT
