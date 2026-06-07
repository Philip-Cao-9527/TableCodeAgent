from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any


TRACE_VERSION = "v0.0.4"
DEFAULT_RESULT_ROOT = Path("benchmarks/results")


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_path_token(value: str | None, *, max_length: int = 80) -> str:
    text = (value or "unknown").strip() or "unknown"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    safe = safe or "unknown"
    if len(safe) <= max_length:
        return safe
    import hashlib
    digest = hashlib.sha1(safe.encode("utf-8")).hexdigest()[:8]
    return f"{safe[:max_length - 9]}-{digest}"


def make_result_dir(
    *,
    mode: str,
    model_name: str | None,
    task_label: str,
    root: str | Path = DEFAULT_RESULT_ROOT,
    timestamp: str | None = None,
) -> Path:
    run_time = timestamp or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    run_id = (
        f"{run_time}__model-{safe_path_token(model_name)}"
        f"__tasks-{safe_path_token(task_label, max_length=120)}"
    )
    run_dir = Path(root) / safe_path_token(mode) / run_id
    (run_dir / "traces").mkdir(parents=True, exist_ok=True)
    (run_dir / "workspaces").mkdir(parents=True, exist_ok=True)
    return run_dir


def base_record(
    *,
    task_id: str,
    mode: str,
    provider: str,
    model_name: str | None,
    api_called: bool,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "trace_version": TRACE_VERSION,
        "task_id": task_id,
        "mode": mode,
        "provider": provider,
        "model_name": model_name,
        "api_called": api_called,
        "skipped": skipped,
        "llm_tool_call_observed": False,
        "tool_call_count": 0,
        "tool_calls": [],
        "final_answer": None,
        "expected_answer": None,
        "validation": None,
        "failure_type": None,
        "metrics": {},
        "elapsed_ms": 0,
        "started_at": utc_timestamp(),
        "ended_at": None,
    }


def finish_record(record: dict[str, Any], *, started_monotonic: float) -> dict[str, Any]:
    record["ended_at"] = utc_timestamp()
    record["elapsed_ms"] = int((time.monotonic() - started_monotonic) * 1000)
    return record


def result_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    validation = trace.get("validation") or {}
    result = {
        "task_id": trace.get("task_id"),
        "mode": trace.get("mode"),
        "provider": trace.get("provider"),
        "model_name": trace.get("model_name"),
        "api_called": trace.get("api_called", False),
        "skipped": trace.get("skipped", False),
        "benchmark_profile": trace.get("benchmark_profile"),
        "helper_hints_exposed": trace.get("helper_hints_exposed"),
        "llm_tool_call_observed": trace.get("llm_tool_call_observed", False),
        "tool_call_count": trace.get("tool_call_count", 0),
        "tool_error_count": (trace.get("metrics") or {}).get("tool_error_count", 0),
        "final_answer": trace.get("final_answer"),
        "expected_answer": trace.get("expected_answer"),
        "validation": validation,
        "passed": (
            trace.get("failure_type") is None
            and (
                validation.get("passed") is True
                or (trace.get("metrics") or {}).get("test_pass_rate") == 1.0
            )
        ),
        "actual": validation.get("actual"),
        "expected": validation.get("expected"),
        "diff": validation.get("diff"),
        "failure_type": trace.get("failure_type"),
        "api_error_type": trace.get("api_error_type"),
        "elapsed_ms": trace.get("elapsed_ms", 0),
        "trace_path": trace.get("trace_path"),
        "result_dir": trace.get("result_dir"),
        "workspace_path": trace.get("workspace_path"),
        "generated_code_path": trace.get("generated_code_path"),
        "answer_path": trace.get("answer_path"),
        "code_generation_source": trace.get("code_generation_source"),
        "schema_check": trace.get("schema_check"),
        "run_python": trace.get("run_python"),
        "run_python_exit_code": trace.get("run_python_exit_code"),
        "run_python_stderr_summary": trace.get("run_python_stderr_summary"),
        "run_python_stdout_summary": trace.get("run_python_stdout_summary"),
        "pytest_exit_code": trace.get("pytest_exit_code"),
        "pytest_failure_summary": trace.get("pytest_failure_summary"),
    }
    metrics = trace.get("metrics") or {}
    result["metrics"] = metrics
    for key in (
        "code_execution_success_rate",
        "test_pass_rate",
        "validation_pass_rate",
        "generated_code_saved",
        "answer_file_saved",
        "solve_py_runtime_seconds",
        "sandbox_timeout_count",
        "dependency_failure_count",
        "tool_error_count",
        "row_expansion_detected",
        "warning_recall",
        "expected_warning_coverage",
    ):
        if key in metrics:
            result[key] = metrics[key]
    return result


def write_trace(run_dir: str | Path, trace: dict[str, Any]) -> Path:
    run_path = Path(run_dir)
    trace_path = run_path / "traces" / f"{trace['task_id']}.{trace['mode']}.json"
    trace["trace_path"] = str(trace_path)
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return trace_path


def append_result(run_dir: str | Path, result: dict[str, Any]) -> Path:
    result_path = Path(run_dir) / "results.jsonl"
    with result_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result_path
