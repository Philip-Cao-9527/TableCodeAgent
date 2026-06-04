from __future__ import annotations

import json
from typing import Any, Callable

from tablecodeagent.table_tools.core import load_table, profile_table, query_multi_table, query_table
from tablecodeagent.validation.answer import validate_answer


TABLE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "load_table",
        "description": "Load table metadata and a bounded preview from CSV or XLSX. Does not return all rows by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "csv_path": {"type": "string", "description": "Path to the CSV or XLSX file."},
                "preview_rows": {
                    "type": "integer",
                    "description": "Number of preview rows to return. Defaults to 5.",
                },
                "sheet_name": {"type": "string", "description": "Optional XLSX sheet name."},
                "header_rows": {
                    "type": "integer",
                    "description": "Number of header rows to normalize. Defaults to 1.",
                },
                "fill_merged_cells": {
                    "type": "boolean",
                    "description": "For XLSX, fill merged cells from the top-left value before reading.",
                },
            },
            "required": ["csv_path"],
        },
    },
    {
        "name": "profile_table",
        "description": "Profile a CSV or XLSX table: row/column counts, missing values, inferred column types, numeric stats, duplicates, and quality flags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "csv_path": {"type": "string", "description": "Path to the CSV or XLSX file."},
                "sheet_name": {"type": "string", "description": "Optional XLSX sheet name."},
                "header_rows": {
                    "type": "integer",
                    "description": "Number of header rows to normalize. Defaults to 1.",
                },
                "fill_merged_cells": {
                    "type": "boolean",
                    "description": "For XLSX, fill merged cells from the top-left value before reading.",
                },
            },
            "required": ["csv_path"],
        },
    },
    {
        "name": "query_table",
        "description": "Run a structured aggregate query over a CSV or XLSX table with equality, comparison, or contains filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "csv_path": {"type": "string", "description": "Path to the CSV or XLSX file."},
                "metric": {
                    "type": "string",
                    "enum": ["count", "sum", "mean", "min", "max"],
                    "description": "Aggregate metric to compute.",
                },
                "column": {
                    "type": "string",
                    "description": "Target column for sum/mean/min/max. Optional for count.",
                },
                "filters": {
                    "anyOf": [
                        {"type": "object"},
                        {"type": "array", "items": {"type": "object"}},
                    ],
                    "description": "Either an object of equality filters, or a list of {column, op, value}. Supported ops: eq, ne, gt, gte, lt, lte, contains.",
                },
                "sheet_name": {"type": "string", "description": "Optional XLSX sheet name."},
                "header_rows": {
                    "type": "integer",
                    "description": "Number of header rows to normalize. Defaults to 1.",
                },
                "fill_merged_cells": {
                    "type": "boolean",
                    "description": "For XLSX, fill merged cells from the top-left value before reading.",
                },
            },
            "required": ["csv_path", "metric"],
        },
    },
    {
        "name": "query_multi_table",
        "description": "Run a minimal two-table inner join aggregate query over CSV/XLSX tables. Columns in filters and metric should be table-prefixed, such as orders.revenue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Exactly two table specs: {name, path, optional sheet_name/header_rows/fill_merged_cells}.",
                },
                "join": {
                    "type": "object",
                    "description": "Join spec: {left_key, right_key}. Keys are unprefixed source columns.",
                },
                "metric": {
                    "type": "string",
                    "enum": ["count", "sum", "mean", "min", "max"],
                    "description": "Aggregate metric to compute after join/filter.",
                },
                "column": {
                    "type": "string",
                    "description": "Prefixed target column for sum/mean/min/max, for example orders.revenue.",
                },
                "filters": {
                    "anyOf": [
                        {"type": "object"},
                        {"type": "array", "items": {"type": "object"}},
                    ],
                    "description": "Filters over prefixed joined columns.",
                },
            },
            "required": ["tables", "join", "metric"],
        },
    },
    {
        "name": "validate_answer",
        "description": "Validate an actual answer against an expected answer with optional numeric tolerance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "actual": {
                    "anyOf": [
                        {"type": "number"},
                        {"type": "string"},
                        {"type": "object"},
                        {"type": "array"},
                        {"type": "boolean"},
                    ],
                    "description": "Actual answer or query_table result.",
                },
                "expected": {
                    "anyOf": [
                        {"type": "number"},
                        {"type": "string"},
                        {"type": "object"},
                        {"type": "array"},
                        {"type": "boolean"},
                    ],
                    "description": "Expected answer.",
                },
                "tolerance": {
                    "type": "number",
                    "description": "Numeric tolerance. Defaults to 1e-6.",
                },
            },
            "required": ["actual", "expected"],
        },
    },
]

TABLE_TOOL_NAMES = {tool["name"] for tool in TABLE_TOOL_DEFINITIONS}


def _load_table(inp: dict[str, Any]) -> dict[str, Any]:
    return load_table(
        inp["csv_path"],
        int(inp.get("preview_rows", 5)),
        sheet_name=inp.get("sheet_name"),
        header_rows=int(inp.get("header_rows", 1)),
        fill_merged_cells=bool(inp.get("fill_merged_cells", False)),
    )


def _profile_table(inp: dict[str, Any]) -> dict[str, Any]:
    return profile_table(
        inp["csv_path"],
        sheet_name=inp.get("sheet_name"),
        header_rows=int(inp.get("header_rows", 1)),
        fill_merged_cells=bool(inp.get("fill_merged_cells", False)),
    )


def _query_table(inp: dict[str, Any]) -> dict[str, Any]:
    return query_table(
        inp["csv_path"],
        metric=inp["metric"],
        column=inp.get("column"),
        filters=inp.get("filters"),
        sheet_name=inp.get("sheet_name"),
        header_rows=int(inp.get("header_rows", 1)),
        fill_merged_cells=bool(inp.get("fill_merged_cells", False)),
    )


def _query_multi_table(inp: dict[str, Any]) -> dict[str, Any]:
    return query_multi_table(
        inp["tables"],
        join=inp["join"],
        metric=inp["metric"],
        column=inp.get("column"),
        filters=inp.get("filters"),
    )


def _validate_answer(inp: dict[str, Any]) -> dict[str, Any]:
    return validate_answer(
        inp["actual"],
        inp["expected"],
        inp.get("tolerance", 1e-6),
    )


_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "load_table": _load_table,
    "profile_table": _profile_table,
    "query_table": _query_table,
    "query_multi_table": _query_multi_table,
    "validate_answer": _validate_answer,
}


def execute_table_tool(name: str, inp: dict[str, Any]) -> str:
    handler = _HANDLERS.get(name)
    if handler is None:
        payload = {"ok": False, "error": f"Unknown table tool: {name}"}
    else:
        try:
            payload = {"ok": True, "result": handler(inp)}
        except Exception as error:
            payload = {
                "ok": False,
                "error": str(error),
                "error_type": type(error).__name__,
            }
    return json.dumps(payload, ensure_ascii=False, indent=2)
