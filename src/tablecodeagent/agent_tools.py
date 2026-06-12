from __future__ import annotations

import json
from typing import Any, Callable

from tablecodeagent.workflow import run_product_workflow
from tablecodeagent.table_tools.core import load_table, profile_table, query_multi_table, query_table
from tablecodeagent.table_tools.quality import (
    calculate_smd,
    check_group_balance,
    check_join_cardinality,
    check_missing_values,
    check_subsidy_outliers,
    check_time_window_alignment,
    check_treatment_control_distribution,
    check_unique_key,
)
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
    {
        "name": "check_missing_values",
        "description": "Check missing values for a table and return per-column counts and rates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_path": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["table_path"],
        },
    },
    {
        "name": "check_unique_key",
        "description": "Check whether key columns uniquely identify rows and return duplicate key examples.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_path": {"type": "string"},
                "key_columns": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["table_path", "key_columns"],
        },
    },
    {
        "name": "check_join_cardinality",
        "description": "Check join cardinality and row expansion between two tables.",
        "input_schema": {
            "type": "object",
            "properties": {
                "left_table_path": {"type": "string"},
                "right_table_path": {"type": "string"},
                "left_keys": {"type": "array", "items": {"type": "string"}},
                "right_keys": {"type": "array", "items": {"type": "string"}},
                "how": {"type": "string", "description": "Join type. Defaults to left."},
            },
            "required": ["left_table_path", "right_table_path", "left_keys"],
        },
    },
    {
        "name": "check_treatment_control_distribution",
        "description": "Check treatment/control counts and imbalance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_path": {"type": "string"},
                "group_column": {"type": "string"},
                "treatment_value": {"type": "string"},
                "control_value": {"type": "string"},
                "min_group_ratio": {"type": "number"},
            },
            "required": ["table_path"],
        },
    },
    {
        "name": "calculate_smd",
        "description": "Calculate SMD or categorical balance gaps for covariates between treatment/control groups.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_path": {"type": "string"},
                "group_column": {"type": "string"},
                "covariates": {"type": "array", "items": {"type": "string"}},
                "treatment_value": {"type": "string"},
                "control_value": {"type": "string"},
                "threshold": {"type": "number"},
            },
            "required": ["table_path", "group_column", "covariates"],
        },
    },
    {
        "name": "check_group_balance",
        "description": "Alias of calculate_smd for group balance checks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_path": {"type": "string"},
                "group_column": {"type": "string"},
                "covariates": {"type": "array", "items": {"type": "string"}},
                "treatment_value": {"type": "string"},
                "control_value": {"type": "string"},
                "threshold": {"type": "number"},
            },
            "required": ["table_path", "group_column", "covariates"],
        },
    },
    {
        "name": "check_subsidy_outliers",
        "description": "Check subsidy amount outliers with an IQR rule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_path": {"type": "string"},
                "column": {"type": "string"},
                "iqr_multiplier": {"type": "number"},
            },
            "required": ["table_path"],
        },
    },
    {
        "name": "check_time_window_alignment",
        "description": "Check whether order_time falls within each user's campaign_window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "orders_table_path": {"type": "string"},
                "exposure_table_path": {"type": "string"},
                "user_key": {"type": "string"},
                "order_time_column": {"type": "string"},
                "campaign_window_column": {"type": "string"},
            },
            "required": ["orders_table_path", "exposure_table_path"],
        },
    },
    {
        "name": "run_table_product_workflow",
        "description": (
            "Run the product-facing TableCodeAgent workflow for a table task. "
            "First call without candidate code returns task parsing, table discovery, compressed context, "
            "tool strategy, and a code-generation brief. Later calls with candidate_code_versions execute "
            "solve.py candidates in the sandbox and return schema/pytest/validation feedback for repair."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_dir": {"type": "string", "description": "Path to a task directory containing task.json and table files."},
                "workspace_dir": {
                    "type": "string",
                    "description": "Optional output workspace for the product workflow run.",
                },
                "candidate_code": {
                    "type": "string",
                    "description": "Optional single solve.py candidate to execute.",
                },
                "candidate_code_versions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional ordered solve.py candidates. The workflow records repair feedback for failed candidates.",
                },
            },
            "required": ["task_dir"],
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


def _check_missing_values(inp: dict[str, Any]) -> dict[str, Any]:
    return check_missing_values(inp["table_path"], inp.get("columns"))


def _check_unique_key(inp: dict[str, Any]) -> dict[str, Any]:
    return check_unique_key(inp["table_path"], inp["key_columns"])


def _check_join_cardinality(inp: dict[str, Any]) -> dict[str, Any]:
    return check_join_cardinality(
        inp["left_table_path"],
        inp["right_table_path"],
        left_keys=inp["left_keys"],
        right_keys=inp.get("right_keys"),
        how=inp.get("how", "left"),
    )


def _check_treatment_control_distribution(inp: dict[str, Any]) -> dict[str, Any]:
    return check_treatment_control_distribution(
        inp["table_path"],
        group_column=inp.get("group_column", "treatment_group"),
        treatment_value=inp.get("treatment_value", "treatment"),
        control_value=inp.get("control_value", "control"),
        min_group_ratio=float(inp.get("min_group_ratio", 0.5)),
    )


def _calculate_smd(inp: dict[str, Any]) -> dict[str, Any]:
    return calculate_smd(
        inp["table_path"],
        group_column=inp["group_column"],
        covariates=inp["covariates"],
        treatment_value=inp.get("treatment_value", "treatment"),
        control_value=inp.get("control_value", "control"),
        threshold=float(inp.get("threshold", 0.1)),
    )


def _check_group_balance(inp: dict[str, Any]) -> dict[str, Any]:
    return check_group_balance(
        inp["table_path"],
        group_column=inp["group_column"],
        covariates=inp["covariates"],
        treatment_value=inp.get("treatment_value", "treatment"),
        control_value=inp.get("control_value", "control"),
        threshold=float(inp.get("threshold", 0.1)),
    )


def _check_subsidy_outliers(inp: dict[str, Any]) -> dict[str, Any]:
    return check_subsidy_outliers(
        inp["table_path"],
        column=inp.get("column", "subsidy_amount"),
        iqr_multiplier=float(inp.get("iqr_multiplier", 1.5)),
    )


def _check_time_window_alignment(inp: dict[str, Any]) -> dict[str, Any]:
    return check_time_window_alignment(
        inp["orders_table_path"],
        inp["exposure_table_path"],
        user_key=inp.get("user_key", "user_id"),
        order_time_column=inp.get("order_time_column", "order_time"),
        campaign_window_column=inp.get("campaign_window_column", "campaign_window"),
    )


def _run_table_product_workflow(inp: dict[str, Any]) -> dict[str, Any]:
    return run_product_workflow(
        task_dir=inp["task_dir"],
        workspace_dir=inp.get("workspace_dir"),
        candidate_code=inp.get("candidate_code"),
        candidate_code_versions=inp.get("candidate_code_versions"),
    )


_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "load_table": _load_table,
    "profile_table": _profile_table,
    "query_table": _query_table,
    "query_multi_table": _query_multi_table,
    "validate_answer": _validate_answer,
    "check_missing_values": _check_missing_values,
    "check_unique_key": _check_unique_key,
    "check_join_cardinality": _check_join_cardinality,
    "check_treatment_control_distribution": _check_treatment_control_distribution,
    "calculate_smd": _calculate_smd,
    "check_group_balance": _check_group_balance,
    "check_subsidy_outliers": _check_subsidy_outliers,
    "check_time_window_alignment": _check_time_window_alignment,
    "run_table_product_workflow": _run_table_product_workflow,
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
