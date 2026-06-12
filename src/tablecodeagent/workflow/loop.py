from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tablecodeagent.benchmark.answer_models import validate_answer_json_with_model
from tablecodeagent.context.table_context import build_table_context_package
from tablecodeagent.workflow.state import ProductWorkflowState
from tablecodeagent.runtime.sandbox import run_python_in_sandbox, run_tests_in_sandbox
from tablecodeagent.validation.answer import validate_answer


TABLE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}


def run_product_workflow(
    *,
    task_dir: str,
    workspace_dir: str | None = None,
    candidate_code: str | None = None,
    candidate_code_versions: list[str] | None = None,
) -> dict[str, Any]:
    task_path = Path(task_dir).resolve()
    task = _read_json(task_path / "task.json")
    tables = _discover_tables(task_path, task)
    state = _build_initial_state(task_path, task, tables)

    candidates = _normalize_candidates(candidate_code, candidate_code_versions)
    if not candidates:
        state.status = "needs_code_generation"
        state.next_action = "generate_candidate_code"
        state.trace.append({
            "event": "context_prepared",
            "table_count": len(tables),
            "next_action": state.next_action,
        })
        return state.to_dict()

    workspace = _prepare_workspace(task_path, workspace_dir)
    state.workspace_path = str(workspace)
    state.next_action = "run_candidate_code"
    state.trace.append({
        "event": "workspace_prepared",
        "workspace_path": str(workspace),
        "candidate_count": len(candidates),
    })

    for index, code in enumerate(candidates, start=1):
        attempt = _run_candidate(workspace, task, index, code)
        state.attempts.append(attempt)
        state.schema_check = attempt.get("schema_check")
        state.validation = attempt.get("validation")
        if attempt["passed"]:
            state.status = "passed"
            state.next_action = None
            state.analysis_memory.append(_build_memory_entry(task, attempt, "passed"))
            state.trace.append({"event": "candidate_passed", "attempt": index})
            return state.to_dict()

        feedback = _build_repair_feedback(index, attempt)
        state.repair_history.append(feedback)
        state.analysis_memory.append(_build_memory_entry(task, attempt, "repair_needed"))
        state.trace.append({"event": "candidate_failed", "attempt": index, "failure_type": attempt["failure_type"]})

    state.status = "repair_needed"
    state.next_action = "revise_candidate_code"
    state.failure_type = state.attempts[-1]["failure_type"] if state.attempts else "no_candidate_code"
    return state.to_dict()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_tables(task_dir: Path, task: dict[str, Any]) -> dict[str, str]:
    tables: dict[str, str] = {}
    if isinstance(task.get("tables"), dict):
        for name, value in task["tables"].items():
            tables[str(name)] = str((task_dir / str(value)).resolve())
    elif isinstance(task.get("data_files"), dict):
        for name, value in task["data_files"].items():
            tables[str(name)] = str((task_dir / str(value)).resolve())
    elif isinstance(task.get("data_files"), list):
        for value in task["data_files"]:
            path = task_dir / str(value)
            tables[path.stem] = str(path.resolve())
    elif task.get("data_file"):
        path = task_dir / str(task["data_file"])
        tables[path.stem] = str(path.resolve())
    else:
        for path in sorted(task_dir.iterdir()):
            if path.suffix.lower() in TABLE_EXTENSIONS:
                tables[path.stem] = str(path.resolve())

    missing = [name for name, path in tables.items() if not Path(path).exists()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"product workflow table discovery found missing table files: {joined}")
    if not tables:
        raise ValueError("product workflow requires at least one table file")
    return tables


def _build_initial_state(task_dir: Path, task: dict[str, Any], tables: dict[str, str]) -> ProductWorkflowState:
    context_package = build_table_context_package(
        tables,
        join_clues=_extract_join_clues(task),
        field_semantics=task.get("output_contract") or {},
    )
    return ProductWorkflowState(
        task_id=str(task.get("id") or task_dir.name),
        task_dir=str(task_dir),
        workspace_path=None,
        status="initialized",
        next_action=None,
        task_summary={
            "id": task.get("id"),
            "task_type": task.get("task_type"),
            "question": task.get("question"),
            "output_contract": task.get("output_contract") or {},
        },
        tables=tables,
        context_package=context_package,
        tool_strategy=_select_tool_strategy(task, context_package),
        code_generation_brief=_build_code_generation_brief(task, context_package),
        analysis_memory=[],
    )


def _extract_join_clues(task: dict[str, Any]) -> list[dict[str, Any]]:
    clues: list[dict[str, Any]] = []
    for section_name in ("finance_config", "query", "output_contract"):
        section = task.get(section_name)
        if isinstance(section, dict):
            keys = [key for key in section if "join" in key.lower() or "key" in key.lower()]
            if keys:
                clues.append({"source": section_name, "keys": keys})
    return clues


def _select_tool_strategy(task: dict[str, Any], context_package: dict[str, Any]) -> list[dict[str, Any]]:
    table_names = sorted(context_package["tables"].keys())
    strategy = [
        {
            "phase": "profile",
            "tool": "profile_table",
            "why": "先确认字段、缺失、重复和类型漂移，避免直接生成脆弱代码。",
            "tables": table_names,
        },
        {
            "phase": "query_or_join",
            "tool": "query_table/query_multi_table",
            "why": "对可结构化的聚合和连接先用表格工具形成证据，再让代码实现完整业务口径。",
            "tables": table_names,
        },
        {
            "phase": "execute_and_validate",
            "tool": "run_table_product_workflow",
            "why": "执行候选 solve.py，收集 schema、pytest、validator 与 sandbox 反馈进入 repair loop。",
            "validation_mode": (task.get("output_contract") or {}).get("validation_mode"),
        },
    ]
    return strategy


def _build_code_generation_brief(task: dict[str, Any], context_package: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal": "生成一个只读 task workspace 数据、写出 answer.json 的候选 solve.py。",
        "question": task.get("question"),
        "tables": {
            name: {
                "columns": package.get("columns"),
                "row_count": package.get("row_count"),
                "quality_flags": package.get("quality_flags"),
            }
            for name, package in context_package["tables"].items()
        },
        "output_contract": task.get("output_contract") or {},
        "constraints": [
            "不要读取 expected.json。",
            "先处理缺失值、重复键、枚举值大小写、字段类型和边界业务口径。",
            "写出 JSON 原生 null，不要把 pandas NaN/NaT 写成字符串。",
            "失败时根据 repair_history 精确修复，不要丢弃已有业务口径。",
        ],
    }


def _normalize_candidates(
    candidate_code: str | None,
    candidate_code_versions: list[str] | None,
) -> list[str]:
    candidates: list[str] = []
    if candidate_code_versions:
        candidates.extend(code for code in candidate_code_versions if code and code.strip())
    if candidate_code and candidate_code.strip():
        candidates.append(candidate_code)
    return candidates


def _prepare_workspace(task_dir: Path, workspace_dir: str | None) -> Path:
    if workspace_dir:
        base = Path(workspace_dir).resolve()
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        base = Path(".tablecodeagent") / "product_runs" / f"{stamp}__{task_dir.name}"
        base = base.resolve()
    if base.exists():
        base = base / f"{task_dir.name}.product_workflow"
    base.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task_dir, base)
    return base


def _run_candidate(workspace: Path, task: dict[str, Any], index: int, code: str) -> dict[str, Any]:
    solve_path = workspace / "solve.py"
    solve_path.write_text(code, encoding="utf-8")

    sandbox_env = {
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    run_result = run_python_in_sandbox("solve.py", workspace_dir=workspace, max_output_chars=40000, env=sandbox_env)
    answer_path = workspace / "answer.json"
    schema_check = _schema_check(answer_path, task)
    test_result = None
    if (workspace / "tests" / "test_solution.py").exists():
        test_result = run_tests_in_sandbox(
            workspace_dir=workspace,
            test_path="tests/test_solution.py",
            max_output_chars=40000,
            env=sandbox_env,
        )
    validation = _validate_answer(answer_path, workspace / "expected.json", task)
    passed = (
        run_result.get("exit_code") == 0
        and schema_check.get("passed") is not False
        and (test_result is None or test_result.get("exit_code") == 0)
        and validation.get("passed") is not False
    )
    failure_type = _classify_failure(run_result, schema_check, test_result, validation)
    return {
        "attempt": index,
        "passed": passed,
        "failure_type": failure_type,
        "run_python": _sandbox_summary(run_result),
        "schema_check": schema_check,
        "pytest": _sandbox_summary(test_result) if test_result is not None else None,
        "validation": validation,
        "answer_path": str(answer_path) if answer_path.exists() else None,
    }


def _schema_check(answer_path: Path, task: dict[str, Any]) -> dict[str, Any]:
    contract = task.get("output_contract") or {}
    answer_model = contract.get("answer_model") or task.get("task_type")
    if not answer_path.exists():
        return {"passed": False, "errors": [{"path": "$", "type": "missing_file", "message": "answer.json must exist"}]}
    try:
        answer = _read_json(answer_path)
    except Exception as error:
        return {"passed": False, "errors": [{"path": "$", "type": "json_parse_error", "message": str(error)}]}
    if answer_model:
        result = validate_answer_json_with_model(answer, task_type=task.get("task_type"), task_id=task.get("id"), answer_model=answer_model)
        return {
            "passed": result["passed"],
            "answer_model": answer_model,
            "errors": result.get("errors", []),
            "actual_keys": sorted(answer.keys()) if isinstance(answer, dict) else [],
        }
    required = list(contract.get("answer_json_required_keys") or contract.get("required_top_level_keys") or [])
    missing = [key for key in required if not isinstance(answer, dict) or key not in answer]
    return {
        "passed": not missing if required else None,
        "required_keys": required,
        "missing_keys": missing,
        "actual_keys": sorted(answer.keys()) if isinstance(answer, dict) else [],
        "errors": [{"path": f"$.{key}", "type": "missing", "message": "required field missing"} for key in missing],
    }


def _validate_answer(answer_path: Path, expected_path: Path, task: dict[str, Any]) -> dict[str, Any]:
    if not answer_path.exists():
        return {"passed": False, "actual": None, "expected": "answer.json exists", "diff": None}
    try:
        answer = _read_json(answer_path)
    except Exception as error:
        return {
            "passed": False,
            "actual": f"{type(error).__name__}: {error}",
            "expected": "valid JSON answer.json",
            "diff": None,
        }
    if not expected_path.exists():
        return {"passed": None, "actual": "answer.json saved", "expected": "pytest/schema or human review", "diff": None}
    expected = _read_json(expected_path)
    if "answer" in expected:
        actual_value = answer.get("answer") if isinstance(answer, dict) and "answer" in answer else answer
        return validate_answer(actual_value, expected["answer"], expected.get("tolerance", 1e-6))
    if (task.get("output_contract") or {}).get("validation_mode") == "pytest":
        return {"passed": None, "actual": "answer.json saved", "expected": "pytest is authoritative", "diff": None}
    return {"passed": None, "actual": answer, "expected": "no explicit expected.answer", "diff": None}


def _classify_failure(
    run_result: dict[str, Any],
    schema_check: dict[str, Any],
    test_result: dict[str, Any] | None,
    validation: dict[str, Any],
) -> str | None:
    if run_result.get("timeout"):
        return "sandbox_timeout"
    if run_result.get("exit_code") != 0:
        return "code_execution_failed"
    if schema_check.get("passed") is False:
        return "answer_schema_mismatch"
    if test_result is not None and test_result.get("timeout"):
        return "sandbox_timeout"
    if test_result is not None and test_result.get("exit_code") != 0:
        return "pytest_failed"
    if validation.get("passed") is False:
        return "validation_failed"
    return None


def _sandbox_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "exit_code": result.get("exit_code"),
        "timeout": result.get("timeout"),
        "failure_type": result.get("failure_type"),
        "stdout_preview": _preview(result.get("stdout")),
        "stderr_preview": _preview(result.get("stderr")),
    }


def _preview(text: str | None, max_chars: int = 800) -> str | None:
    if not text:
        return None
    stripped = text.strip()
    return stripped[:max_chars] if stripped else None


def _build_repair_feedback(index: int, attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt": index,
        "failure_type": attempt["failure_type"],
        "schema_errors": (attempt.get("schema_check") or {}).get("errors", []),
        "validation": attempt.get("validation"),
        "pytest": attempt.get("pytest"),
        "run_python": attempt.get("run_python"),
        "repair_instruction": "优先修复最早失败层；不要通过删除字段或绕过校验来伪装成功。",
    }


def _build_memory_entry(task: dict[str, Any], attempt: dict[str, Any], outcome: str) -> dict[str, Any]:
    return {
        "scope": "report-scoped",
        "task_id": task.get("id"),
        "outcome": outcome,
        "failure_type": attempt.get("failure_type"),
        "schema_error_count": len((attempt.get("schema_check") or {}).get("errors", [])),
        "validation_passed": (attempt.get("validation") or {}).get("passed"),
    }
