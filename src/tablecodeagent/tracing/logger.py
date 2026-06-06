from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


TRACE_VERSION = "v0.0.2"


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_run_dir(root: str | Path = "benchmarks/runs", run_id: str | None = None) -> Path:
    run_name = run_id or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    run_dir = Path(root) / run_name
    (run_dir / "traces").mkdir(parents=True, exist_ok=True)
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
        "llm_tool_call_observed": trace.get("llm_tool_call_observed", False),
        "tool_call_count": trace.get("tool_call_count", 0),
        "final_answer": trace.get("final_answer"),
        "expected_answer": trace.get("expected_answer"),
        "validation": validation,
        "passed": validation.get("passed") is True and trace.get("failure_type") is None,
        "actual": validation.get("actual"),
        "expected": validation.get("expected"),
        "diff": validation.get("diff"),
        "failure_type": trace.get("failure_type"),
        "elapsed_ms": trace.get("elapsed_ms", 0),
        "trace_path": trace.get("trace_path"),
    }
    metrics = trace.get("metrics") or {}
    result["metrics"] = metrics
    for key in (
        "code_execution_success_rate",
        "test_pass_rate",
        "validation_pass_rate",
        "generated_code_saved",
        "solve_py_runtime_seconds",
        "sandbox_timeout_count",
        "dependency_failure_count",
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
