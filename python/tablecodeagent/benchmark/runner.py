from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import time
from pathlib import Path
from typing import Any

from mini_claude.tools import execute_tool, get_active_tool_definitions
from tablecodeagent.agent_tools import TABLE_TOOL_NAMES
from tablecodeagent.table_tools.core import query_multi_table, query_table
from tablecodeagent.tracing.logger import (
    append_result,
    base_record,
    finish_record,
    make_run_dir,
    result_from_trace,
    write_trace,
)
from tablecodeagent.validation.answer import validate_answer


DEFAULT_TASK_DIR = Path("benchmarks/tasks/demo_table_001")
DEFAULT_ENV_FILE = Path("configs/api/local/provider_chatanywhere.env")
MODES = ("direct", "agent_tool_dispatch", "optional_llm_agent")


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
        for key in ("value", "matched_row_count", "total_row_count", "column_count", "duplicate_row_count"):
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
    trace["expected_answer"] = expected["answer"]
    try:
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
        if validation.get("passed") is not True:
            trace["failure_type"] = "validation_failed"
    except FileNotFoundError as error:
        trace["failure_type"] = "table_read_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = str(error)
    except Exception as error:
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
    trace["expected_answer"] = expected["answer"]

    try:
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
    trace["expected_answer"] = expected["answer"]

    if not env_file.exists():
        trace["skipped"] = True
        trace["failure_type"] = "llm_runtime_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": expected["answer"], "diff": None}
        trace["error"] = f"API env file not found: {env_file}"
        return _finish_and_write(run_dir, trace, started)

    try:
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
            if trace["validation"]["passed"] is not True:
                trace["failure_type"] = "validation_failed"
    except Exception as error:
        trace["api_called"] = trace.get("api_called", False) or bool(trace.get("model_name"))
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
        else:
            raise ValueError(f"Unsupported benchmark mode: {mode}")
    return output_dir, results


async def run_benchmark_for_tasks(
    *,
    modes: list[str],
    task_dirs: list[Path],
    run_dir: Path | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
) -> tuple[Path, list[dict[str, Any]]]:
    output_dir = run_dir or make_run_dir()
    results: list[dict[str, Any]] = []
    if (output_dir / "results.jsonl").exists():
        (output_dir / "results.jsonl").unlink()

    for task_dir in task_dirs:
        _, task_results = await run_benchmark(
            modes=modes,
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
        help="Mode to run. Can be repeated. Defaults to direct and agent_tool_dispatch.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    modes = args.mode or ["direct", "agent_tool_dispatch"]
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
