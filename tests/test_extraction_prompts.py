"""Tests for extraction prompt templates."""

import pytest

from prompts.extraction import (
    EXTRACTION_SCHEMAS,
    get_extraction_prompt,
    get_extraction_system_prompt,
)

SPECIFIC_CATEGORIES = [
    "Contrato",
    "Laudo Médico",
    "Extrato Bancário",
    "Ficha Cadastral",
    "Nota Fiscal",
]


class TestExtractionSystemPrompt:
    def test_returns_non_empty_string(self):
        assert len(get_extraction_system_prompt()) > 0

    def test_mentions_json_and_confidence(self):
        prompt = get_extraction_system_prompt()
        assert "JSON" in prompt
        assert "0.0" in prompt and "1.0" in prompt


class TestSpecificCategoryPrompts:
    @pytest.mark.parametrize("category", SPECIFIC_CATEGORIES)
    def test_contains_category_name(self, category: str):
        assert category in get_extraction_prompt(category)

    @pytest.mark.parametrize("category", SPECIFIC_CATEGORIES)
    def test_contains_all_expected_fields(self, category: str):
        prompt = get_extraction_prompt(category)
        for field in EXTRACTION_SCHEMAS[category]:
            assert field in prompt

    @pytest.mark.parametrize("category", SPECIFIC_CATEGORIES)
    def test_instructs_null_and_zero_confidence_for_missing(self, category: str):
        prompt = get_extraction_prompt(category)
        assert "null" in prompt
        assert "0.0" in prompt

    @pytest.mark.parametrize("category", SPECIFIC_CATEGORIES)
    def test_instructs_json_output_format(self, category: str):
        prompt = get_extraction_prompt(category)
        assert "JSON" in prompt
        assert "fields" in prompt


class TestGenericCategoryPrompt:
    def test_mentions_max_10_fields(self):
        assert "10" in get_extraction_prompt("Documento Genérico")

    def test_instructs_json_output(self):
        prompt = get_extraction_prompt("Documento Genérico")
        assert "JSON" in prompt and "fields" in prompt

    def test_mentions_null_and_confidence(self):
        prompt = get_extraction_prompt("Documento Genérico")
        assert "null" in prompt and "confidence" in prompt


class TestInvalidCategory:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Categoria desconhecida"):
            get_extraction_prompt("Categoria Inexistente")


class TestExtractionSchemas:
    def test_has_six_categories(self):
        assert len(EXTRACTION_SCHEMAS) == 6

    def test_generic_has_empty_fields(self):
        assert EXTRACTION_SCHEMAS["Documento Genérico"] == []

    @pytest.mark.parametrize("category,expected_fields", [
        ("Contrato", ["Partes", "Valor", "Prazo", "Assinaturas"]),
        ("Laudo Médico", ["Paciente", "CRM", "CID", "Medicamentos"]),
        ("Extrato Bancário", ["Banco", "Conta", "Datas", "Valores"]),
        ("Ficha Cadastral", ["Nome Completo", "CPF", "Data de Nascimento", "Endereço", "Telefone"]),
        ("Nota Fiscal", ["Emitente", "CNPJ", "Número da Nota", "Itens", "Valor Total", "Data de Emissão"]),
    ])
    def test_schema_fields_match(self, category: str, expected_fields: list[str]):
        assert EXTRACTION_SCHEMAS[category] == expected_fields
