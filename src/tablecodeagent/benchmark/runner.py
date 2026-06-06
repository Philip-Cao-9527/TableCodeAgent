from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import shutil
import textwrap
import time
from pathlib import Path
from typing import Any

from mini_claude.tools import execute_tool, get_active_tool_definitions
from tablecodeagent.agent_tools import TABLE_TOOL_NAMES
from tablecodeagent.runtime.dependency import ensure_runtime_dependencies
from tablecodeagent.runtime.sandbox import run_python_in_sandbox, run_tests_in_sandbox
from tablecodeagent.table_tools.core import load_table, query_multi_table, query_table
from tablecodeagent.table_tools.quality import (
    calculate_smd,
    check_join_cardinality,
    check_missing_values,
    check_subsidy_outliers,
    check_time_window_alignment,
    check_treatment_control_distribution,
    check_unique_key,
    expected_warning_coverage,
)
from tablecodeagent.tracing.logger import (
    append_result,
    base_record,
    finish_record,
    make_run_dir,
    result_from_trace,
    write_trace,
)
from tablecodeagent.validation.answer import validate_answer
from tablecodeagent.workflows.growth_campaign_audit import run_growth_campaign_audit


DEFAULT_TASK_DIR = Path("benchmarks/tasks/demo_table_001")
DEFAULT_ENV_FILE = Path("configs/api/local/provider_chatanywhere.env")
QUERY_MODES = ("direct", "agent_tool_dispatch", "optional_llm_agent")
GROWTH_MODES = ("growth_l0_tools", "growth_workflow", "sandbox_code_agent")
MODES = QUERY_MODES + GROWTH_MODES


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_task(task_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    task = _read_json(task_dir / "task.json")
    expected = _read_json(task_dir / "expected.json")
    return task, expected


def _extract_final_answer(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def _resolve_path(task_dir: Path, value: str) -> str:
    path = Path(value)
    return str(path if path.is_absolute() else task_dir / path)


def _resolve_table_paths(value: Any, task_dir: Path) -> Any:
    if isinstance(value, list):
        return [_resolve_table_paths(item, task_dir) for item in value]
    if isinstance(value, dict):
        resolved: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"path", "csv_path", "table_path"} and isinstance(item, str):
                resolved[key] = _resolve_path(task_dir, item)
            else:
                resolved[key] = _resolve_table_paths(item, task_dir)
        return resolved
    return value


def _query_tool_name(task: dict[str, Any]) -> str:
    return task.get("query", {}).get("tool", "query_table")


def _query_arguments(task: dict[str, Any], task_dir: Path) -> dict[str, Any]:
    query = {key: value for key, value in task["query"].items() if key != "tool"}
    if _query_tool_name(task) == "query_table" and "csv_path" not in query:
        query["csv_path"] = task["data_file"]
    return _resolve_table_paths(query, task_dir)


def _run_query_direct(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "query_table":
        return query_table(**arguments)
    if tool_name == "query_multi_table":
        return query_multi_table(**arguments)
    raise ValueError(f"Unsupported query tool: {tool_name}")


def _profile_arguments(tool_name: str, query_args: dict[str, Any]) -> list[dict[str, Any]]:
    if tool_name != "query_table":
        return []
    keys = ("csv_path", "sheet_name", "header_rows", "fill_merged_cells")
    return [{key: query_args[key] for key in keys if key in query_args}]


def _summarize_tool_result(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except Exception:
        return {"ok": None, "raw_preview": raw[:500]}

    summary: dict[str, Any] = {"ok": payload.get("ok")}
    if payload.get("error_type"):
        summary["error_type"] = payload.get("error_type")
    result = payload.get("result")
    if isinstance(result, dict):
        for key in (
            "value",
            "matched_row_count",
            "total_row_count",
            "column_count",
            "duplicate_row_count",
            "duplicate_key_count",
            "row_expansion_ratio",
            "outlier_count",
            "mismatch_count",
        ):
            if key in result:
                summary[key] = result[key]
        for key in ("passed", "actual", "expected", "diff"):
            if key in result:
                summary[key] = result[key]
    else:
        summary["result"] = result
    return summary


def _tool_event(name: str, arguments: dict[str, Any], raw: str, elapsed_ms: int) -> dict[str, Any]:
    summary = _summarize_tool_result(raw)
    return {
        "name": name,
        "arguments": arguments,
        "result_summary": summary,
        "ok": summary.get("ok"),
        "error_type": summary.get("error_type"),
        "elapsed_ms": elapsed_ms,
    }


async def _execute_traced_tool(trace: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    raw = await execute_tool(name, arguments)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    trace["tool_calls"].append(_tool_event(name, arguments, raw, elapsed_ms))
    trace["tool_call_count"] = len(trace["tool_calls"])
    payload = json.loads(raw)
    if payload.get("ok") is not True:
        trace["failure_type"] = "tool_error"
    return payload


def _finish_and_write(run_dir: Path, trace: dict[str, Any], started: float) -> dict[str, Any]:
    finish_record(trace, started_monotonic=started)
    write_trace(run_dir, trace)
    result = result_from_trace(trace)
    append_result(run_dir, result)
    return result


def _record_dependency(
    trace: dict[str, Any],
    *,
    formats: list[str] | None = None,
    include_test: bool = False,
    include_llm: bool = False,
) -> None:
    dependency = ensure_runtime_dependencies(
        formats=formats,
        include_test=include_test,
        include_llm=include_llm,
        auto_install=True,
    )
    trace["dependency_check"] = dependency
    failed = not dependency.get("ok")
    trace.setdefault("metrics", {})["dependency_failure_count"] = 1 if failed else 0
    if failed:
        trace["failure_type"] = dependency.get("failure_type") or "dependency_missing"
        raise RuntimeError(trace["failure_type"])


def _base_metrics() -> dict[str, Any]:
    return {
        "code_execution_success_rate": None,
        "test_pass_rate": None,
        "validation_pass_rate": None,
        "generated_code_saved": False,
        "solve_py_runtime_seconds": None,
        "sandbox_timeout_count": 0,
        "dependency_failure_count": 0,
        "row_expansion_detected": False,
        "warning_recall": None,
        "expected_warning_coverage": None,
    }


def _run_direct(task_dir: Path, run_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    task, expected = _load_task(task_dir)
    tool_name = _query_tool_name(task)
    query_args = _query_arguments(task, task_dir)
    trace = base_record(
        task_id=task["id"],
        mode="direct",
        provider="none",
        model_name=None,
        api_called=False,
    )
    trace["metrics"] = _base_metrics()
    trace["expected_answer"] = expected["answer"]
    try:
        _record_dependency(trace)
        actual = _run_query_direct(tool_name, query_args)
        trace["tool_calls"].append({
            "name": tool_name,
            "arguments": query_args,
            "result_summary": {
                "ok": True,
                "value": actual.get("value"),
                "matched_row_count": actual.get("matched_row_count"),
                "total_row_count": actual.get("total_row_count"),
                "joined_row_count": actual.get("joined_row_count"),
            },
            "ok": True,
            "error_type": None,
            "elapsed_ms": None,
        })
        trace["tool_call_count"] = 1
        validation = validate_answer(actual, expected["answer"], expected.get("tolerance", 1e-6))
        trace["tool_calls"].append({
            "name": "validate_answer",
            "arguments": {
                "actual": actual,
                "expected": expected["answer"],
                "tolerance": expected.get("tolerance", 1e-6),
            },
            "result_summary": {"ok": True, "passed": validation.get("passed")},
            "ok": True,
            "error_type": None,
            "elapsed_ms": None,
        })
        trace["tool_call_count"] = 2
        trace["final_answer"] = _extract_final_answer(actual)
        trace["validation"] = validation
        trace["metrics"]["validation_pass_rate"] = 1.0 if validation.get("passed") is True else 0.0
        if validation.get("passed") is not True:
            trace["failure_type"] = "validation_failed"
    except FileNotFoundError as error:
        trace["failure_type"] = "table_read_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = str(error)
    except Exception as error:
        if trace.get("failure_type") is None:
            trace["failure_type"] = "tool_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = f"{type(error).__name__}: {error}"
    return _finish_and_write(run_dir, trace, started)


async def _run_agent_tool_dispatch(task_dir: Path, run_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    task, expected = _load_task(task_dir)
    tool_name = _query_tool_name(task)
    query_args = _query_arguments(task, task_dir)
    trace = base_record(
        task_id=task["id"],
        mode="agent_tool_dispatch",
        provider="none",
        model_name=None,
        api_called=False,
    )
    trace["metrics"] = _base_metrics()
    trace["expected_answer"] = expected["answer"]

    try:
        _record_dependency(trace)
        tool_names = {tool["name"] for tool in get_active_tool_definitions()}
        missing = TABLE_TOOL_NAMES - tool_names
        if missing:
            raise RuntimeError(f"missing table tools: {sorted(missing)}")

        for profile_args in _profile_arguments(tool_name, query_args):
            profile = await _execute_traced_tool(trace, "profile_table", profile_args)
            if trace.get("failure_type"):
                raise RuntimeError(profile.get("error") or "profile_table failed")

        query = await _execute_traced_tool(trace, tool_name, query_args)
        if trace.get("failure_type"):
            raise RuntimeError(query.get("error") or f"{tool_name} failed")

        actual = query["result"]
        validation = await _execute_traced_tool(
            trace,
            "validate_answer",
            {
                "actual": actual,
                "expected": expected["answer"],
                "tolerance": expected.get("tolerance", 1e-6),
            },
        )
        trace["final_answer"] = _extract_final_answer(actual)
        trace["validation"] = validation.get("result")
        trace["metrics"]["validation_pass_rate"] = 1.0 if trace["validation"].get("passed") is True else 0.0
        if validation.get("ok") is not True:
            trace["failure_type"] = "tool_error"
        elif trace["validation"].get("passed") is not True:
            trace["failure_type"] = "validation_failed"
    except FileNotFoundError as error:
        trace["failure_type"] = "table_read_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = str(error)
    except Exception as error:
        if trace.get("failure_type") is None:
            trace["failure_type"] = "tool_error"
        trace["validation"] = trace.get("validation") or {
            "passed": False,
            "actual": None,
            "expected": expected["answer"],
            "diff": None,
        }
        trace["error"] = f"{type(error).__name__}: {error}"
    return _finish_and_write(run_dir, trace, started)


def _load_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            parts = shlex.split(value, posix=True)
            value = parts[0] if parts else ""
        except ValueError:
            value = value.strip("\"'")
        values[key] = value
    return values


async def _run_optional_llm_agent(task_dir: Path, run_dir: Path, env_file: Path) -> dict[str, Any]:
    started = time.monotonic()
    task, expected = _load_task(task_dir)
    provider = env_file.stem
    trace = base_record(
        task_id=task["id"],
        mode="optional_llm_agent",
        provider=provider,
        model_name=None,
        api_called=False,
    )
    trace["metrics"] = _base_metrics()
    trace["expected_answer"] = expected["answer"]

    if not env_file.exists():
        trace["skipped"] = True
        trace["failure_type"] = "llm_runtime_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = f"API env file not found: {env_file}"
        return _finish_and_write(run_dir, trace, started)

    try:
        _record_dependency(trace, include_llm=True)
        env_values = _load_env_file(env_file)
        old_env: dict[str, str | None] = {}
        for key, value in env_values.items():
            old_env[key] = os.environ.get(key)
            os.environ[key] = value

        model_name = os.environ.get("MINI_CLAUDE_MODEL")
        api_base = os.environ.get("MINI_CLAUDE_API_BASE") or os.environ.get("OPENAI_BASE_URL")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        trace["model_name"] = model_name

        if not api_base or not model_name or not api_key:
            trace["skipped"] = True
            trace["failure_type"] = "llm_runtime_error"
            trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
            trace["error"] = "API config missing MINI_CLAUDE_API_BASE, MINI_CLAUDE_MODEL, or API key."
            return _finish_and_write(run_dir, trace, started)

        table_tool_names = set(TABLE_TOOL_NAMES)

        def trace_callback(event: dict[str, Any]) -> None:
            if event.get("event") != "tool_result":
                return
            name = event.get("name")
            if name not in table_tool_names:
                return
            result_summary = _summarize_tool_result(event.get("result", ""))
            trace["llm_tool_call_observed"] = True
            trace["tool_calls"].append({
                "name": name,
                "arguments": event.get("arguments", {}),
                "result_summary": result_summary,
                "ok": result_summary.get("ok"),
                "error_type": result_summary.get("error_type"),
                "elapsed_ms": event.get("elapsed_ms"),
            })
            trace["tool_call_count"] = len(trace["tool_calls"])

        from mini_claude.agent import Agent

        agent = Agent(
            permission_mode="default",
            model=model_name,
            max_turns=8,
            api_base=api_base,
            api_key=api_key,
            is_sub_agent=True,
            trace_callback=trace_callback,
        )
        prompt = (
            f"请在 {task_dir} 上完成一次表格工具调用闭环："
            "先读取 task.json 和 expected.json，理解 task.json 的 query 字段；"
            "再调用合适的表格工具完成计算，最后调用 validate_answer 与 expected.json 中的答案校验。"
            "请只基于工具结果给出最终答案和校验结果，不要修改任何文件。"
        )
        trace["api_called"] = True
        run_result = await agent.run_once(prompt)
        trace["final_answer"] = run_result.get("text", "").strip() or None
        trace["token_usage"] = run_result.get("tokens")

        validation_events = [
            call for call in trace["tool_calls"]
            if call.get("name") == "validate_answer"
        ]
        if not trace["llm_tool_call_observed"]:
            trace["failure_type"] = "llm_tool_call_missing"
            trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        elif not validation_events:
            trace["failure_type"] = "validation_failed"
            trace["validation"] = {"passed": False, "actual": trace["final_answer"], "expected": expected["answer"], "diff": None}
        else:
            last_validation = validation_events[-1]["result_summary"]
            trace["validation"] = {
                "passed": last_validation.get("passed") is True,
                "actual": last_validation.get("actual"),
                "expected": last_validation.get("expected", expected["answer"]),
                "diff": last_validation.get("diff"),
            }
            trace["metrics"]["validation_pass_rate"] = 1.0 if trace["validation"]["passed"] else 0.0
            if trace["validation"]["passed"] is not True:
                trace["failure_type"] = "validation_failed"
    except Exception as error:
        trace["api_called"] = trace.get("api_called", False) or bool(trace.get("model_name"))
        if trace.get("failure_type") is None:
            trace["failure_type"] = "llm_runtime_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = f"{type(error).__name__}: {error}"
    finally:
        if "old_env" in locals():
            for key, old_value in old_env.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value

    return _finish_and_write(run_dir, trace, started)


def _table_paths(task_dir: Path, task: dict[str, Any]) -> dict[str, Path]:
    return {name: Path(_resolve_path(task_dir, value)) for name, value in task["tables"].items()}


def _run_growth_l0_tools(task_dir: Path, run_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    task, expected = _load_task(task_dir)
    trace = base_record(
        task_id=task["id"],
        mode="growth_l0_tools",
        provider="none",
        model_name=None,
        api_called=False,
    )
    trace["metrics"] = _base_metrics()
    trace["expected_answer"] = expected

    try:
        _record_dependency(trace, formats=["feather"])
        paths = _table_paths(task_dir, task)
        import numpy as np
        import pandas as pd

        fixtures_dir = run_dir / "format_fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        fixture = pd.DataFrame({"user_id": ["u1", "u2"], "value": [1, 2]})
        csv_path = fixtures_dir / "fixture.csv"
        xlsx_path = fixtures_dir / "fixture.xlsx"
        feather_path = fixtures_dir / "fixture.feather"
        npy_path = fixtures_dir / "fixture.npy"
        npz_path = fixtures_dir / "fixture.npz"
        fixture.to_csv(csv_path, index=False)
        fixture.to_excel(xlsx_path, index=False)
        fixture.to_feather(feather_path)
        np.save(npy_path, np.array([[1, 2], [3, 4]]))
        np.savez(npz_path, first=np.array([1, 2]), second=np.array([3, 4]))
        format_checks = {
            "csv": load_table(csv_path)["row_count"],
            "xlsx": load_table(xlsx_path)["row_count"],
            "feather": load_table(feather_path)["row_count"],
            "npy": load_table(npy_path)["row_count"],
            "npz": load_table(npz_path)["row_count"],
        }

        users = paths["users"]
        exposure = paths["campaign_exposure"]
        rewards = paths["rewards"]
        orders = paths["orders"]
        exposure_users = pd.read_csv(exposure).merge(pd.read_csv(users), on="user_id", how="left")

        missing = {name: check_missing_values(path) for name, path in paths.items()}
        duplicate_key = check_unique_key(rewards, task["audit_config"]["duplicate_key_columns"])
        join_cardinality = check_join_cardinality(
            exposure,
            rewards,
            left_keys=task["audit_config"]["join_keys"],
            right_keys=task["audit_config"]["join_keys"],
            how="left",
        )
        distribution = check_treatment_control_distribution(exposure)
        smd = calculate_smd(
            exposure_users,
            group_column="treatment_group",
            covariates=task["audit_config"]["covariates"],
        )
        outliers = check_subsidy_outliers(rewards)
        time_window = check_time_window_alignment(orders, exposure)
        warnings = []
        if duplicate_key["duplicate_key_count"]:
            warnings.extend(["duplicate_key", "不能静默 drop duplicates"])
        if join_cardinality["row_expansion_detected"]:
            warnings.extend(["join_row_expansion", join_cardinality["cardinality"]])
        if distribution["imbalanced"]:
            warnings.append("imbalanced_treatment_control")
        warnings.extend([f"smd_{column}" for column in smd["warning_columns"]])
        if outliers["outlier_count"]:
            warnings.append("subsidy_outlier")
        if time_window["mismatch_count"]:
            warnings.append("time_window_mismatch")
        coverage = expected_warning_coverage(warnings, expected["expected_required_warnings"])
        checks = {
            "format_checks": all(value == 2 for value in format_checks.values()),
            "duplicate_key": duplicate_key["duplicate_key_count"] == expected["expected_duplicate_key_count"],
            "join_cardinality": join_cardinality["cardinality"] == expected["expected_join_cardinality"],
            "row_expansion": join_cardinality["row_expansion_ratio"] >= expected["expected_row_expansion_ratio_min"],
            "distribution": distribution["treatment_count"] == expected["expected_treatment_count"]
            and distribution["control_count"] == expected["expected_control_count"],
            "smd": set(expected["expected_smd_warning_columns"]).issubset(set(smd["warning_columns"])),
            "outliers": outliers["outlier_count"] == expected["expected_subsidy_outlier_count"],
            "time_window": time_window["mismatch_count"] == expected["expected_time_window_mismatch_count"],
            "warnings": not coverage["missing"],
        }
        trace["tool_calls"] = [
            {"name": "pandas_backend_format_checks", "arguments": {}, "result_summary": format_checks, "ok": checks["format_checks"], "error_type": None, "elapsed_ms": None},
            {"name": "check_missing_values", "arguments": {}, "result_summary": {"total_missing": sum(item["total_missing"] for item in missing.values())}, "ok": True, "error_type": None, "elapsed_ms": None},
            {"name": "check_unique_key", "arguments": {"key_columns": task["audit_config"]["duplicate_key_columns"]}, "result_summary": duplicate_key, "ok": checks["duplicate_key"], "error_type": None, "elapsed_ms": None},
            {"name": "check_join_cardinality", "arguments": {"join_keys": task["audit_config"]["join_keys"]}, "result_summary": join_cardinality, "ok": checks["join_cardinality"], "error_type": None, "elapsed_ms": None},
            {"name": "check_treatment_control_distribution", "arguments": {}, "result_summary": distribution, "ok": checks["distribution"], "error_type": None, "elapsed_ms": None},
            {"name": "calculate_smd", "arguments": {"covariates": task["audit_config"]["covariates"]}, "result_summary": smd, "ok": checks["smd"], "error_type": None, "elapsed_ms": None},
            {"name": "check_subsidy_outliers", "arguments": {}, "result_summary": outliers, "ok": checks["outliers"], "error_type": None, "elapsed_ms": None},
            {"name": "check_time_window_alignment", "arguments": {}, "result_summary": time_window, "ok": checks["time_window"], "error_type": None, "elapsed_ms": None},
        ]
        trace["tool_call_count"] = len(trace["tool_calls"])
        trace["final_answer"] = {"checks": checks, "warnings": warnings}
        trace["validation"] = {"passed": all(checks.values()), "actual": checks, "expected": "all checks true", "diff": None}
        trace["metrics"].update({
            "validation_pass_rate": 1.0 if trace["validation"]["passed"] else 0.0,
            "row_expansion_detected": join_cardinality["row_expansion_detected"],
            "warning_recall": coverage["warning_recall"],
            "expected_warning_coverage": coverage["expected_warning_coverage"],
        })
        if trace["validation"]["passed"] is not True:
            trace["failure_type"] = "validation_failed"
    except Exception as error:
        if trace.get("failure_type") is None:
            trace["failure_type"] = "tool_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected, "diff": None}
        trace["error"] = f"{type(error).__name__}: {error}"
    return _finish_and_write(run_dir, trace, started)


def _run_growth_workflow(task_dir: Path, run_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    task, expected = _load_task(task_dir)
    trace = base_record(
        task_id=task["id"],
        mode="growth_workflow",
        provider="none",
        model_name=None,
        api_called=False,
    )
    trace["metrics"] = _base_metrics()
    trace["expected_answer"] = expected
    output_path = run_dir / "traces" / f"{task['id']}.audit_report.json"

    try:
        _record_dependency(trace)
        report = run_growth_campaign_audit(task_dir, output_path=output_path)
        validation = report["validation"]
        trace["tool_calls"] = [{
            "name": "growth_campaign_audit_workflow",
            "arguments": {"task_dir": str(task_dir), "output_path": str(output_path)},
            "result_summary": {
                "passed": validation["passed"],
                "warning_recall": validation["warning_recall"],
                "row_expansion_ratio": report["join_cardinality"]["row_expansion_ratio"],
            },
            "ok": validation["passed"],
            "error_type": None,
            "elapsed_ms": None,
        }]
        trace["tool_call_count"] = 1
        trace["final_answer"] = report
        trace["validation"] = {
            "passed": validation["passed"],
            "actual": validation["checks"],
            "expected": "growth workflow expected checks",
            "diff": None,
        }
        trace["metrics"].update({
            "validation_pass_rate": 1.0 if validation["passed"] else 0.0,
            "row_expansion_detected": report["join_cardinality"]["row_expansion_detected"],
            "warning_recall": validation["warning_recall"],
            "expected_warning_coverage": validation["expected_warning_coverage"],
        })
        if validation["passed"] is not True:
            trace["failure_type"] = "validation_failed"
    except Exception as error:
        if trace.get("failure_type") is None:
            trace["failure_type"] = "workflow_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected, "diff": None}
        trace["error"] = f"{type(error).__name__}: {error}"
    return _finish_and_write(run_dir, trace, started)


def _copy_task_workspace(task_dir: Path, run_dir: Path, mode: str) -> Path:
    workspace = run_dir / "workspaces" / f"{task_dir.name}.{mode}"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(task_dir, workspace)
    return workspace


def _write_solve_py(workspace: Path) -> Path:
    solve_path = workspace / "solve.py"
    solve_path.write_text(textwrap.dedent(
        """
        from __future__ import annotations

        import json
        from pathlib import Path

        from tablecodeagent.workflows.growth_campaign_audit import (
            build_growth_campaign_audit_report,
            validate_growth_campaign_audit_report,
        )


        def main() -> None:
            task_dir = Path(__file__).resolve().parent
            report = build_growth_campaign_audit_report(task_dir)
            expected = json.loads((task_dir / "expected.json").read_text(encoding="utf-8"))
            report["validation"] = validate_growth_campaign_audit_report(report, expected)
            (task_dir / "answer.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\\n",
                encoding="utf-8",
            )


        if __name__ == "__main__":
            main()
        """
    ).strip() + "\n", encoding="utf-8")
    return solve_path


def _run_sandbox_code_agent(task_dir: Path, run_dir: Path) -> dict[str, Any]:
    started = time.monotonic()
    task, expected = _load_task(task_dir)
    trace = base_record(
        task_id=task["id"],
        mode="sandbox_code_agent",
        provider="none",
        model_name=None,
        api_called=False,
    )
    trace["metrics"] = _base_metrics()
    trace["expected_answer"] = expected

    try:
        _record_dependency(trace, include_test=True)
        workspace = _copy_task_workspace(task_dir, run_dir, "sandbox_code_agent")
        solve_path = _write_solve_py(workspace)
        project_python = str((Path.cwd() / "src").resolve())
        sandbox_env = {"PYTHONPATH": project_python}
        run_result = run_python_in_sandbox(
            "solve.py",
            workspace_dir=workspace,
            timeout_seconds=30,
            max_output_chars=20000,
            env=sandbox_env,
        )
        test_result = run_tests_in_sandbox(
            workspace_dir=workspace,
            test_path="tests/test_solution.py",
            timeout_seconds=30,
            max_output_chars=20000,
            env=sandbox_env,
        )
        answer_path = workspace / "answer.json"
        answer = _read_json(answer_path) if answer_path.exists() else None
        validation = (answer or {}).get("validation") or {"passed": False}
        coverage = {"warning_recall": 0.0, "expected_warning_coverage": 0}
        if answer:
            coverage = expected_warning_coverage(answer.get("warnings", []), expected["expected_required_warnings"])
        passed = run_result["exit_code"] == 0 and test_result["exit_code"] == 0 and validation.get("passed") is True
        trace["generated_code_path"] = str(solve_path)
        trace["answer_path"] = str(answer_path)
        trace["sandbox_results"] = {
            "run_python": run_result,
            "run_tests": test_result,
        }
        trace["tool_calls"] = [
            {
                "name": "generate_solve_py",
                "arguments": {"workspace": str(workspace)},
                "result_summary": {"path": str(solve_path)},
                "ok": True,
                "error_type": None,
                "elapsed_ms": None,
            },
            {
                "name": "run_python_in_sandbox",
                "arguments": {"script_path": "solve.py", "workspace_dir": str(workspace)},
                "result_summary": {
                    "exit_code": run_result["exit_code"],
                    "timeout": run_result["timeout"],
                    "failure_type": run_result.get("failure_type"),
                },
                "ok": run_result["exit_code"] == 0,
                "error_type": run_result.get("failure_type"),
                "elapsed_ms": int(run_result["duration_seconds"] * 1000),
            },
            {
                "name": "run_tests_in_sandbox",
                "arguments": {"test_path": "tests/test_solution.py", "workspace_dir": str(workspace)},
                "result_summary": {
                    "exit_code": test_result["exit_code"],
                    "timeout": test_result["timeout"],
                    "failure_type": test_result.get("failure_type"),
                },
                "ok": test_result["exit_code"] == 0,
                "error_type": test_result.get("failure_type"),
                "elapsed_ms": int(test_result["duration_seconds"] * 1000),
            },
        ]
        trace["tool_call_count"] = len(trace["tool_calls"])
        trace["final_answer"] = answer
        trace["validation"] = {
            "passed": passed,
            "actual": validation,
            "expected": "answer.json passes expected.json and pytest",
            "diff": None,
        }
        trace["metrics"].update({
            "code_execution_success_rate": 1.0 if run_result["exit_code"] == 0 else 0.0,
            "test_pass_rate": 1.0 if test_result["exit_code"] == 0 else 0.0,
            "validation_pass_rate": 1.0 if validation.get("passed") is True else 0.0,
            "generated_code_saved": solve_path.exists(),
            "solve_py_runtime_seconds": run_result["duration_seconds"],
            "sandbox_timeout_count": int(bool(run_result["timeout"])) + int(bool(test_result["timeout"])),
            "row_expansion_detected": bool((answer or {}).get("join_cardinality", {}).get("row_expansion_detected")),
            "warning_recall": coverage["warning_recall"],
            "expected_warning_coverage": coverage["expected_warning_coverage"],
        })
        if passed is not True:
            if run_result["timeout"] or test_result["timeout"]:
                trace["failure_type"] = "sandbox_timeout"
            elif run_result["exit_code"] != 0:
                trace["failure_type"] = "code_execution_failed"
            elif test_result["exit_code"] != 0:
                trace["failure_type"] = "pytest_failed"
            else:
                trace["failure_type"] = "validation_failed"
    except Exception as error:
        if trace.get("failure_type") is None:
            trace["failure_type"] = "sandbox_code_agent_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected, "diff": None}
        trace["error"] = f"{type(error).__name__}: {error}"
    return _finish_and_write(run_dir, trace, started)


def _modes_for_task(task: dict[str, Any], requested_modes: list[str] | None) -> list[str]:
    default_modes = list(task.get("benchmark_modes") or ("direct", "agent_tool_dispatch"))
    if requested_modes is None:
        return default_modes
    allowed = set(default_modes)
    if "query" in task:
        allowed.update(QUERY_MODES)
    return [mode for mode in requested_modes if mode in allowed]


async def run_benchmark(
    *,
    modes: list[str],
    task_dir: Path = DEFAULT_TASK_DIR,
    run_dir: Path | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
    reset_results: bool = True,
) -> tuple[Path, list[dict[str, Any]]]:
    output_dir = run_dir or make_run_dir()
    results: list[dict[str, Any]] = []
    if reset_results and (output_dir / "results.jsonl").exists():
        (output_dir / "results.jsonl").unlink()

    for mode in modes:
        if mode == "direct":
            results.append(_run_direct(task_dir, output_dir))
        elif mode == "agent_tool_dispatch":
            results.append(await _run_agent_tool_dispatch(task_dir, output_dir))
        elif mode == "optional_llm_agent":
            results.append(await _run_optional_llm_agent(task_dir, output_dir, env_file))
        elif mode == "growth_l0_tools":
            results.append(_run_growth_l0_tools(task_dir, output_dir))
        elif mode == "growth_workflow":
            results.append(_run_growth_workflow(task_dir, output_dir))
        elif mode == "sandbox_code_agent":
            results.append(_run_sandbox_code_agent(task_dir, output_dir))
        else:
            raise ValueError(f"Unsupported benchmark mode: {mode}")
    return output_dir, results


async def run_benchmark_for_tasks(
    *,
    modes: list[str] | None,
    task_dirs: list[Path],
    run_dir: Path | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
) -> tuple[Path, list[dict[str, Any]]]:
    output_dir = run_dir or make_run_dir()
    results: list[dict[str, Any]] = []
    if (output_dir / "results.jsonl").exists():
        (output_dir / "results.jsonl").unlink()

    for task_dir in task_dirs:
        task = _read_json(task_dir / "task.json")
        task_modes = _modes_for_task(task, modes)
        if not task_modes:
            continue
        _, task_results = await run_benchmark(
            modes=task_modes,
            task_dir=task_dir,
            run_dir=output_dir,
            env_file=env_file,
            reset_results=False,
        )
        results.extend(task_results)
    return output_dir, results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TableCodeAgent benchmark smoke tests.")
    parser.add_argument("--task-dir", action="append", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--env", default=str(DEFAULT_ENV_FILE))
    parser.add_argument(
        "--mode",
        action="append",
        choices=MODES,
        help="Mode to run. Can be repeated. Defaults to each task's benchmark_modes or direct/agent_tool_dispatch.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    modes = args.mode
    run_dir = Path(args.run_dir) if args.run_dir else None
    task_dirs = [Path(value) for value in args.task_dir] if args.task_dir else sorted(
        path for path in Path("benchmarks/tasks").iterdir()
        if path.is_dir() and (path / "task.json").exists()
    )
    output_dir, results = asyncio.run(run_benchmark_for_tasks(
        modes=modes,
        task_dirs=task_dirs,
        run_dir=run_dir,
        env_file=Path(args.env),
    ))
    print(f"run_dir: {output_dir}")
    print(f"results: {output_dir / 'results.jsonl'}")
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
        if result.get("skipped") is True:
            print(f"SKIP: {result.get('failure_type') or 'benchmark mode skipped'}")
    failed = [result for result in results if result.get("skipped") is not True and result.get("passed") is not True]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
