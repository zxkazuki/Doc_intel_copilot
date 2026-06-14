"""DynamoDB client wrapper — generic CRUD operations for all tables."""

import logging
from functools import reduce

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_table(table_name: str):
    """Returns a DynamoDB Table resource."""
    resource = boto3.resource("dynamodb", region_name=settings.aws_region)
    return resource.Table(table_name)


def put_item(table_name: str, item: dict) -> None:
    """Insere item na tabela."""
    try:
        table = get_table(table_name)
        table.put_item(Item=item)
    except ClientError as e:
        logger.error("Erro ao inserir item em %s: %s", table_name, e)
        raise


def get_item(table_name: str, key: dict) -> dict | None:
    """Busca item por chave primária. Retorna None se não existir."""
    try:
        table = get_table(table_name)
        response = table.get_item(Key=key)
        return response.get("Item")
    except ClientError as e:
        logger.error("Erro ao buscar item em %s: %s", table_name, e)
        raise


def update_item(table_name: str, key: dict, updates: dict) -> None:
    """Atualiza campos de um item existente."""
    if not updates:
        return

    try:
        table = get_table(table_name)

        expr_parts = [f"#f{i} = :v{i}" for i in range(len(updates))]
        attr_names = {f"#f{i}": field for i, field in enumerate(updates.keys())}
        attr_values = {f":v{i}": value for i, value in enumerate(updates.values())}

        table.update_item(
            Key=key,
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
    except ClientError as e:
        logger.error("Erro ao atualizar item em %s: %s", table_name, e)
        raise


def query_items(
    table_name: str,
    key_condition: dict,
    index_name: str | None = None,
    filter_expr: dict | None = None,
    limit: int | None = None,
    exclusive_start_key: dict | None = None,
    scan_forward: bool = False,
) -> list[dict]:
    """Query com condição de chave e filtros opcionais.

    Args:
        key_condition: {"pk_field": value} ou {"pk_field": value, "sk_field": {"op": val}}.
            Operadores de sort key: begins_with, between, gte, lte, eq.
        index_name: Nome do GSI, se aplicável.
        filter_expr: Filtros pós-query. {"field": value} ou {"field": {"contains": val}}.
        limit: Máximo de itens retornados.
        exclusive_start_key: Chave para paginação.
        scan_forward: True = ascendente, False (padrão) = descendente.
    """
    try:
        table = get_table(table_name)

        kwargs: dict = {
            "KeyConditionExpression": _build_key_condition(key_condition),
            "ScanIndexForward": scan_forward,
        }

        if index_name:
            kwargs["IndexName"] = index_name
        if filter_expr:
            kwargs["FilterExpression"] = _build_filter_expression(filter_expr)
        if limit:
            kwargs["Limit"] = limit
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key

        response = table.query(**kwargs)
        return response.get("Items", [])
    except ClientError as e:
        logger.error("Erro ao consultar %s: %s", table_name, e)
        raise


def scan_items(
    table_name: str,
    filter_expr: dict | None = None,
    limit: int | None = None,
    exclusive_start_key: dict | None = None,
) -> dict:
    """Scan da tabela com filtros opcionais e paginação.

    Returns:
        {"items": [...], "last_evaluated_key": key | None}
    """
    try:
        table = get_table(table_name)
        kwargs: dict = {}

        if filter_expr:
            kwargs["FilterExpression"] = _build_filter_expression(filter_expr)
        if limit:
            kwargs["Limit"] = limit
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key

        response = table.scan(**kwargs)
        return {
            "items": response.get("Items", []),
            "last_evaluated_key": response.get("LastEvaluatedKey"),
        }
    except ClientError as e:
        logger.error("Erro ao scan %s: %s", table_name, e)
        raise


# --- Internal helpers ---


def _build_key_condition(key_condition: dict):
    """Constrói KeyConditionExpression a partir de dicionário."""
    conditions = [_resolve_key_field(field, value) for field, value in key_condition.items()]
    return reduce(lambda a, b: a & b, conditions)


def _build_filter_expression(filter_expr: dict):
    """Constrói FilterExpression a partir de dicionário."""
    conditions = [_resolve_attr_field(field, value) for field, value in filter_expr.items()]
    return reduce(lambda a, b: a & b, conditions)


def _resolve_key_field(field: str, value):
    """Resolve uma condição de chave para um campo."""
    if not isinstance(value, dict):
        return Key(field).eq(value)

    match value:
        case {"begins_with": prefix}:
            return Key(field).begins_with(prefix)
        case {"between": [low, high]}:
            return Key(field).between(low, high)
        case {"gte": v}:
            return Key(field).gte(v)
        case {"lte": v}:
            return Key(field).lte(v)
        case {"eq": v}:
            return Key(field).eq(v)
        case _:
            raise ValueError(f"Operador de key condition não suportado: {value}")


def _resolve_attr_field(field: str, value):
    """Resolve uma condição de filtro para um campo."""
    if not isinstance(value, dict):
        return Attr(field).eq(value)

    match value:
        case {"contains": substring}:
            return Attr(field).contains(substring)
        case {"begins_with": prefix}:
            return Attr(field).begins_with(prefix)
        case {"between": [low, high]}:
            return Attr(field).between(low, high)
        case {"gte": v}:
            return Attr(field).gte(v)
        case {"lte": v}:
            return Attr(field).lte(v)
        case _:
            raise ValueError(f"Operador de filter expression não suportado: {value}")
