from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tablecodeagent.agent_tools import TABLE_TOOL_NAMES
from tablecodeagent.runtime.dependency import ensure_runtime_dependencies
from tablecodeagent.runtime.sandbox import run_python_in_sandbox, run_tests_in_sandbox
from tablecodeagent.tracing.logger import (
    append_result,
    base_record,
    finish_record,
    result_from_trace,
    write_trace,
)
from tablecodeagent.validation.answer import validate_answer


MODE = "real_api_code_agent"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_env_file(env_file: Path) -> dict[str, str]:
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


@contextmanager
def patched_environ(values: dict[str, str]) -> Iterator[None]:
    old_env: dict[str, str | None] = {}
    try:
        for key, value in values.items():
            old_env[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextmanager
def pushd(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _path_denied(path: str, workspace: Path) -> str | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    if _is_within(candidate, workspace):
        return None
    return f"Benchmark workspace policy denied path outside workspace: {path}"


def _command_denied(command: str, workspace: Path) -> str | None:
    stripped = command.strip()
    workspace_text = shlex.quote(str(workspace))
    allowed_prefixes = (
        "python solve.py",
        f"cd {workspace_text} && python solve.py",
        f"cd {workspace} && python solve.py",
    )
    if stripped in allowed_prefixes:
        return None
    return "Benchmark workspace policy denied shell command; use only `python solve.py` inside the workspace."


def _table_tool_path_denied(value: Any, workspace: Path) -> str | None:
    if isinstance(value, str):
        if value.endswith((".csv", ".tsv", ".xlsx", ".xls", ".json", ".feather", ".npy", ".npz")):
            return _path_denied(value, workspace)
        return None
    if isinstance(value, list):
        for item in value:
            denial = _table_tool_path_denied(item, workspace)
            if denial:
                return denial
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"csv_path", "path", "file_path"} or key.endswith("_path") or key == "tables":
                denial = _table_tool_path_denied(item, workspace)
                if denial:
                    return denial
            elif isinstance(item, (dict, list)):
                denial = _table_tool_path_denied(item, workspace)
                if denial:
                    return denial
    return None


@contextmanager
def guarded_agent_tools(workspace: Path) -> Iterator[None]:
    import mini_claude.agent as agent_module

    original_execute_tool = agent_module.execute_tool
    workspace = workspace.resolve()

    async def guarded_execute_tool(name: str, inp: dict[str, Any], read_file_state: Any = None) -> str:
        if name in {"read_file", "write_file", "edit_file"}:
            denial = _path_denied(str(inp.get("file_path", "")), workspace)
            if denial:
                return denial
        elif name in {"list_files", "grep_search"}:
            path_value = inp.get("path")
            if path_value:
                denial = _path_denied(str(path_value), workspace)
                if denial:
                    return denial
        elif name == "run_shell":
            denial = _command_denied(str(inp.get("command", "")), workspace)
            if denial:
                return denial
        elif name in TABLE_TOOL_NAMES:
            denial = _table_tool_path_denied(inp, workspace)
            if denial:
                return denial
        return await original_execute_tool(name, inp, read_file_state)

    agent_module.execute_tool = guarded_execute_tool
    try:
        yield
    finally:
        agent_module.execute_tool = original_execute_tool


def _copy_task_workspace(task_dir: Path, result_dir: Path) -> tuple[Path, Path]:
    result_dir = result_dir.resolve()
    workspace = result_dir / "workspaces" / f"{task_dir.name}.{MODE}"
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(task_dir, workspace)
    expected_source = workspace / "expected.json"
    expected_hidden = result_dir / "traces" / f"{task_dir.name}.expected.json.for_external_check"
    if expected_source.exists():
        expected_source.rename(expected_hidden)
    return workspace, expected_hidden


def _restore_expected_for_external_check(expected_hidden: Path, workspace: Path) -> Path | None:
    if not expected_hidden.exists():
        return None
    expected_path = workspace / "expected.json"
    shutil.copy2(expected_hidden, expected_path)
    return expected_path


def _summarize_tool_result(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except Exception:
        return {"ok": None, "raw_preview": raw[:500]}
    result = payload.get("result")
    summary: dict[str, Any] = {"ok": payload.get("ok")}
    if payload.get("error_type"):
        summary["error_type"] = payload.get("error_type")
    if isinstance(result, dict):
        for key in ("value", "passed", "actual", "expected", "diff", "row_count", "column_count"):
            if key in result:
                summary[key] = result[key]
    return summary


def _extract_python_code(text: str) -> str | None:
    matches = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[-1].strip() + "\n"
    return None


def _extract_answer_value(answer: Any) -> Any:
    if isinstance(answer, dict):
        for key in ("answer", "value", "final_answer", "result"):
            if key in answer:
                return answer[key]
    return answer


def _validate_answer_json(answer_path: Path, expected_path: Path | None) -> dict[str, Any]:
    if not answer_path.exists():
        return {"passed": False, "actual": None, "expected": "answer.json exists", "diff": None}
    answer = read_json(answer_path)
    if expected_path is None or not expected_path.exists():
        return {"passed": True, "actual": answer, "expected": "answer.json exists", "diff": None}
    expected = read_json(expected_path)
    if "answer" not in expected:
        validation = answer.get("validation") if isinstance(answer, dict) else None
        if isinstance(validation, dict) and "passed" in validation:
            return {
                "passed": validation.get("passed") is True,
                "actual": validation,
                "expected": "answer.json validation.passed=true",
                "diff": None,
            }
        return {"passed": True, "actual": answer, "expected": "answer.json exists", "diff": None}
    return validate_answer(_extract_answer_value(answer), expected["answer"], expected.get("tolerance", 1e-6))


def _task_prompt(task_dir: Path) -> str:
    task = read_json(task_dir / "task.json")
    files = sorted(path.name for path in task_dir.iterdir() if path.is_file() and path.name != "expected.json")
    return (
        "你正在参加 TableCodeAgent 的真实 API 代码生成 benchmark。\n"
        f"当前 benchmark workspace 绝对路径: {task_dir.resolve()}\n"
        "请根据当前 benchmark workspace 中的任务文件生成一个可执行的 solve.py，并通过工具把 solve.py 写入该 workspace。\n"
        "要求：\n"
        "1. 只能读取 task.json 和数据文件；不要读取 expected.json，也不要假设 expected.json 存在。\n"
        "2. solve.py 运行后必须在当前目录写出 answer.json。\n"
        "3. answer.json 应包含足够的结构化结果，便于外部 pytest 或 validator 校验。\n"
        "4. 优先使用 pandas 等成熟库处理表格。\n"
        "5. 不要写入 API key、.env 或 configs/api/local 路径。\n"
        "6. 如果需要解释，请在写完 solve.py 后简短说明。\n\n"
        f"任务 id: {task.get('id')}\n"
        f"任务问题: {task.get('question')}\n"
        f"可用文件: {files}\n"
        "重要：不要读取或写入 workspace 外的文件；不要在仓库根目录写 solve.py 或 answer.json。\n"
    )


async def run_real_api_code_agent(
    *,
    task_dir: Path,
    result_dir: Path,
    env_file: Path,
    model_name: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    task = read_json(task_dir / "task.json")
    trace = base_record(
        task_id=task["id"],
        mode=MODE,
        provider=env_file.stem,
        model_name=model_name,
        api_called=False,
    )
    trace["benchmark_category"] = "real_api_code_agent"
    trace["result_dir"] = str(result_dir)
    trace["code_generation_source"] = "llm_generated"
    trace["expected_answer"] = None
    trace["metrics"] = {
        "code_execution_success_rate": None,
        "test_pass_rate": None,
        "validation_pass_rate": None,
        "generated_code_saved": False,
        "solve_py_runtime_seconds": None,
        "sandbox_timeout_count": 0,
        "dependency_failure_count": 0,
    }

    if not env_file.exists():
        trace["skipped"] = True
        trace["failure_type"] = "api_env_missing"
        trace["validation"] = {"passed": False, "actual": None, "expected": "api env exists", "diff": None}
        trace["error"] = f"API env file not found: {env_file}"
        return _finish(result_dir, trace, started)

    try:
        dependency = ensure_runtime_dependencies(include_llm=True, include_test=True, auto_install=True)
        trace["dependency_check"] = dependency
        trace["metrics"]["dependency_failure_count"] = 0 if dependency.get("ok") else 1
        if not dependency.get("ok"):
            trace["failure_type"] = dependency.get("failure_type") or "dependency_missing"
            raise RuntimeError(trace["failure_type"])

        if not api_base or not model_name or not api_key:
            trace["skipped"] = True
            trace["failure_type"] = "api_config_missing"
            trace["validation"] = {"passed": False, "actual": None, "expected": "api config", "diff": None}
            trace["error"] = "API config missing MINI_CLAUDE_API_BASE, MINI_CLAUDE_MODEL, or API key."
            return _finish(result_dir, trace, started)

        workspace, expected_hidden = _copy_task_workspace(task_dir, result_dir)
        trace["workspace_path"] = str(workspace)
        solve_path = workspace / "solve.py"
        answer_path = workspace / "answer.json"
        trace["generated_code_path"] = str(solve_path)
        trace["answer_path"] = str(answer_path)

        table_tool_names = set(TABLE_TOOL_NAMES)

        def trace_callback(event: dict[str, Any]) -> None:
            if event.get("event") != "tool_result":
                return
            name = event.get("name")
            if name in table_tool_names:
                trace["llm_tool_call_observed"] = True
            trace["tool_calls"].append({
                "name": name,
                "arguments": event.get("arguments", {}),
                "result_summary": _summarize_tool_result(event.get("result", "")),
                "elapsed_ms": event.get("elapsed_ms"),
            })
            trace["tool_call_count"] = len(trace["tool_calls"])

        from mini_claude.agent import Agent

        agent = Agent(
            permission_mode="bypassPermissions",
            model=model_name,
            max_turns=10,
            api_base=api_base,
            api_key=api_key,
            is_sub_agent=True,
            trace_callback=trace_callback,
        )
        trace["api_called"] = True
        with guarded_agent_tools(workspace), pushd(workspace):
            run_result = await agent.run_once(_task_prompt(workspace))
        trace["final_answer"] = run_result.get("text", "").strip() or None
        trace["token_usage"] = run_result.get("tokens")

        if not solve_path.exists():
            code = _extract_python_code(trace["final_answer"] or "")
            if code:
                solve_path.write_text(code, encoding="utf-8")

        trace["metrics"]["generated_code_saved"] = solve_path.exists()
        if not solve_path.exists():
            trace["failure_type"] = "code_generation_failed"
            trace["validation"] = {"passed": False, "actual": None, "expected": "solve.py generated", "diff": None}
            return _finish(result_dir, trace, started)

        project_python = str((Path.cwd() / "src").resolve())
        sandbox_env = {"PYTHONPATH": project_python}
        run_result = run_python_in_sandbox(
            "solve.py",
            workspace_dir=workspace,
            max_output_chars=40000,
            env=sandbox_env,
        )
        expected_path = _restore_expected_for_external_check(expected_hidden, workspace)
        test_path = workspace / "tests" / "test_solution.py"
        test_result = None
        if test_path.exists():
            test_result = run_tests_in_sandbox(
                workspace_dir=workspace,
                test_path="tests/test_solution.py",
                max_output_chars=40000,
                env=sandbox_env,
            )
        validation = _validate_answer_json(answer_path, expected_path)

        trace["sandbox_results"] = {"run_python": run_result, "run_tests": test_result}
        trace["validation"] = validation
        trace["metrics"].update({
            "code_execution_success_rate": 1.0 if run_result["exit_code"] == 0 else 0.0,
            "test_pass_rate": None if test_result is None else (1.0 if test_result["exit_code"] == 0 else 0.0),
            "validation_pass_rate": 1.0 if validation.get("passed") is True else 0.0,
            "solve_py_runtime_seconds": run_result["duration_seconds"],
            "sandbox_timeout_count": int(bool(run_result["timeout"])) + (
                int(bool(test_result["timeout"])) if test_result else 0
            ),
        })

        if run_result["timeout"]:
            trace["failure_type"] = "sandbox_timeout"
        elif run_result["exit_code"] != 0:
            trace["failure_type"] = "code_execution_failed"
        elif test_result is not None and test_result["timeout"]:
            trace["failure_type"] = "sandbox_timeout"
        elif test_result is not None and test_result["exit_code"] != 0:
            trace["failure_type"] = "pytest_failed"
        elif validation.get("passed") is not True:
            trace["failure_type"] = "validation_failed"
    except Exception as error:
        if trace.get("failure_type") is None:
            trace["failure_type"] = "real_api_code_agent_error"
        trace["validation"] = {"passed": False, "actual": None, "expected": "real_api_code_agent completed", "diff": None}
        trace["error"] = f"{type(error).__name__}: {error}"

    return _finish(result_dir, trace, started)


def _finish(result_dir: Path, trace: dict[str, Any], started: float) -> dict[str, Any]:
    finish_record(trace, started_monotonic=started)
    write_trace(result_dir, trace)
    result = result_from_trace(trace)
    append_result(result_dir, result)
    return result


def run_real_api_code_agent_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_real_api_code_agent(**kwargs))
