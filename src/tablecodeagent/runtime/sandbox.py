from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_ENV_ALLOWLIST = {
    "PATH",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "LANG",
    "LC_ALL",
    "TMPDIR",
}

FORBIDDEN_PATH_PARTS = (
    ".env",
    "configs/api/local",
    ".ssh",
    ".aws",
    ".config",
)

FORBIDDEN_TEXT_MARKERS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "MINI_CLAUDE_API_BASE",
    "MINI_CLAUDE_MODEL",
    "configs/api/local",
    ".env",
)


def _sandbox_policy() -> dict[str, Any]:
    return {
        "isolation": "process-level light sandbox",
        "containerized": False,
        "shell": False,
        "env_policy": "allowlist",
        "sensitive_paths_blocked": list(FORBIDDEN_PATH_PARTS),
        "note": "This is not Docker, Firecracker, or gVisor strong isolation.",
    }


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    keep = max(0, (max_chars - 80) // 2)
    return (
        text[:keep] + f"\n\n[... truncated {len(text) - keep * 2} chars ...]\n\n" + text[-keep:],
        True,
    )


def _is_forbidden_path(path: Path) -> bool:
    normalized = str(path).replace("\\", "/")
    home = str(Path.home()).replace("\\", "/")
    if normalized.startswith(home + "/") and not normalized.startswith(str(Path.cwd()).replace("\\", "/") + "/"):
        return True
    return any(part in normalized for part in FORBIDDEN_PATH_PARTS)


def _resolve_workspace(workspace_dir: str | Path) -> Path:
    workspace = Path(workspace_dir).resolve()
    if _is_forbidden_path(workspace):
        raise PermissionError(f"Forbidden sandbox workspace: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _safe_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in DEFAULT_ENV_ALLOWLIST}
    if extra_env:
        for key, value in extra_env.items():
            if key in DEFAULT_ENV_ALLOWLIST or key.startswith("TABLECODEAGENT_"):
                env[key] = value
    return env


def _policy_denial(command: list[str], cwd: Path, reason: str, started: float) -> dict[str, Any]:
    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": None,
        "stdout": "",
        "stderr": reason,
        "timeout": False,
        "duration_seconds": round(time.monotonic() - started, 3),
        "output_truncated": False,
        "sandbox_policy": _sandbox_policy(),
        "failure_type": "sandbox_policy_denied",
    }


def _validate_script_policy(script_path: Path) -> str | None:
    if _is_forbidden_path(script_path):
        return f"Sandbox denied forbidden script path: {script_path}"
    try:
        text = script_path.read_text(encoding="utf-8", errors="replace")
    except Exception as error:
        return f"Sandbox could not read script for policy check: {error}"
    for marker in FORBIDDEN_TEXT_MARKERS:
        if marker in text:
            return f"Sandbox denied script because it references sensitive marker: {marker}"
    return None


def run_python_in_sandbox(
    script_path: str | Path,
    *,
    workspace_dir: str | Path,
    args: list[str] | None = None,
    timeout_seconds: int = 30,
    max_output_chars: int = 20000,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    workspace = _resolve_workspace(workspace_dir)
    script = Path(script_path)
    if not script.is_absolute():
        script = workspace / script
    script = script.resolve()
    command = [sys.executable, str(script), *(args or [])]

    try:
        script.relative_to(workspace)
    except ValueError:
        return _policy_denial(command, workspace, f"Sandbox denied script outside workspace: {script}", started)

    denial = _validate_script_policy(script)
    if denial:
        return _policy_denial(command, workspace, denial, started)

    try:
        result = subprocess.run(
            command,
            cwd=workspace,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=_safe_env(env),
        )
        stdout, stdout_truncated = _truncate(result.stdout or "", max_output_chars)
        stderr, stderr_truncated = _truncate(result.stderr or "", max_output_chars)
        return {
            "command": command,
            "cwd": str(workspace),
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timeout": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output_truncated": stdout_truncated or stderr_truncated,
            "sandbox_policy": _sandbox_policy(),
            "failure_type": None if result.returncode == 0 else "sandbox_process_failed",
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stdout, stdout_truncated = _truncate(stdout, max_output_chars)
        stderr, stderr_truncated = _truncate(stderr, max_output_chars)
        return {
            "command": command,
            "cwd": str(workspace),
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr,
            "timeout": True,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output_truncated": stdout_truncated or stderr_truncated,
            "sandbox_policy": _sandbox_policy(),
            "failure_type": "sandbox_timeout",
        }


def run_tests_in_sandbox(
    *,
    workspace_dir: str | Path,
    test_path: str = "tests/test_solution.py",
    timeout_seconds: int = 30,
    max_output_chars: int = 20000,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    workspace = _resolve_workspace(workspace_dir)
    target = (workspace / test_path).resolve()
    command = [sys.executable, "-m", "pytest", test_path, "-q"]

    try:
        target.relative_to(workspace)
    except ValueError:
        return _policy_denial(command, workspace, f"Sandbox denied test outside workspace: {target}", started)
    if _is_forbidden_path(target):
        return _policy_denial(command, workspace, f"Sandbox denied forbidden test path: {target}", started)

    try:
        result = subprocess.run(
            command,
            cwd=workspace,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=_safe_env(env),
        )
        stdout, stdout_truncated = _truncate(result.stdout or "", max_output_chars)
        stderr, stderr_truncated = _truncate(result.stderr or "", max_output_chars)
        return {
            "command": command,
            "cwd": str(workspace),
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timeout": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output_truncated": stdout_truncated or stderr_truncated,
            "sandbox_policy": _sandbox_policy(),
            "failure_type": None if result.returncode == 0 else "sandbox_tests_failed",
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stdout, stdout_truncated = _truncate(stdout, max_output_chars)
        stderr, stderr_truncated = _truncate(stderr, max_output_chars)
        return {
            "command": command,
            "cwd": str(workspace),
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr,
            "timeout": True,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output_truncated": stdout_truncated or stderr_truncated,
            "sandbox_policy": _sandbox_policy(),
            "failure_type": "sandbox_timeout",
        }
