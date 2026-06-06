from __future__ import annotations

import importlib
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import metadata
from typing import Any


@dataclass(frozen=True)
class DependencySpec:
    package: str
    import_name: str
    required_for: str


REQUIRED_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("pandas", "pandas", "pandas_backend"),
    DependencySpec("numpy", "numpy", "array_backend"),
    DependencySpec("openpyxl", "openpyxl", "xlsx_backend"),
)

TEST_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("pytest", "pytest", "sandbox_test_runner"),
)

LLM_DEPENDENCIES: tuple[DependencySpec, ...] = (
    DependencySpec("openai", "openai", "optional_llm_agent"),
    DependencySpec("anthropic", "anthropic", "optional_llm_agent"),
    DependencySpec("rich", "rich", "optional_llm_agent_ui"),
)

FORMAT_DEPENDENCIES: dict[str, DependencySpec] = {
    "feather": DependencySpec("pyarrow", "pyarrow", "feather_backend"),
}

DEFAULT_MAX_INSTALL_ATTEMPTS = 3


def _version_for(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def check_dependency(spec: DependencySpec) -> dict[str, Any]:
    try:
        importlib.import_module(spec.import_name)
        installed = True
    except ImportError:
        installed = False
    return {
        "package": spec.package,
        "import_name": spec.import_name,
        "required_for": spec.required_for,
        "installed": installed,
        "version": _version_for(spec.package) if installed else None,
    }


def required_specs_for_formats(
    formats: list[str] | tuple[str, ...] | None = None,
    *,
    include_test: bool = False,
    include_llm: bool = False,
) -> list[DependencySpec]:
    specs = list(REQUIRED_DEPENDENCIES)
    for fmt in formats or ():
        spec = FORMAT_DEPENDENCIES.get(fmt.lower().lstrip("."))
        if spec and spec not in specs:
            specs.append(spec)
    if include_test:
        for spec in TEST_DEPENDENCIES:
            if spec not in specs:
                specs.append(spec)
    if include_llm:
        for spec in LLM_DEPENDENCIES:
            if spec not in specs:
                specs.append(spec)
    return specs


def check_runtime_dependencies(
    *,
    formats: list[str] | tuple[str, ...] | None = None,
    include_test: bool = False,
    include_llm: bool = False,
) -> dict[str, Any]:
    checks = [
        check_dependency(spec)
        for spec in required_specs_for_formats(
            formats,
            include_test=include_test,
            include_llm=include_llm,
        )
    ]
    missing = [item for item in checks if not item["installed"]]
    return {
        "ok": not missing,
        "checks": checks,
        "missing": missing,
        "failure_type": "dependency_missing" if missing else None,
    }


def _install_command(package: str, attempt: int) -> list[str]:
    base = [sys.executable, "-m", "pip", "install", package]
    if attempt == 2:
        return base + ["--prefer-binary"]
    if attempt >= 3:
        return base + [
            "--prefer-binary",
            "--no-cache-dir",
            "--index-url",
            "https://pypi.org/simple",
        ]
    return base


def install_dependency(
    spec: DependencySpec,
    *,
    max_attempts: int = DEFAULT_MAX_INSTALL_ATTEMPTS,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    started = time.monotonic()
    max_attempts = max(1, max_attempts)

    for attempt in range(1, max_attempts + 1):
        command = _install_command(spec.package, attempt)
        step_started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            attempts.append({
                "attempt": attempt,
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "duration_seconds": round(time.monotonic() - step_started, 3),
            })
            if result.returncode == 0 and check_dependency(spec)["installed"]:
                return {
                    "package": spec.package,
                    "installed": True,
                    "attempts": attempts,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "failure_type": None,
                }
        except subprocess.TimeoutExpired as error:
            attempts.append({
                "attempt": attempt,
                "command": command,
                "exit_code": None,
                "stdout": (error.stdout or "")[-4000:] if isinstance(error.stdout, str) else "",
                "stderr": (error.stderr or "")[-4000:] if isinstance(error.stderr, str) else "",
                "timeout": True,
                "duration_seconds": round(time.monotonic() - step_started, 3),
            })

    return {
        "package": spec.package,
        "installed": False,
        "attempts": attempts,
        "duration_seconds": round(time.monotonic() - started, 3),
        "failure_type": "dependency_install_failed",
    }


def ensure_runtime_dependencies(
    *,
    formats: list[str] | tuple[str, ...] | None = None,
    include_test: bool = False,
    include_llm: bool = False,
    auto_install: bool = False,
    max_attempts: int = DEFAULT_MAX_INSTALL_ATTEMPTS,
) -> dict[str, Any]:
    before = check_runtime_dependencies(formats=formats, include_test=include_test, include_llm=include_llm)
    install_logs: list[dict[str, Any]] = []
    if before["ok"] or not auto_install:
        return {
            **before,
            "auto_install": auto_install,
            "install_logs": install_logs,
        }

    specs_by_package = {
        spec.package: spec
        for spec in required_specs_for_formats(
            formats,
            include_test=include_test,
            include_llm=include_llm,
        )
    }
    for missing in before["missing"]:
        spec = specs_by_package[missing["package"]]
        install_logs.append(install_dependency(spec, max_attempts=max_attempts))

    after = check_runtime_dependencies(formats=formats, include_test=include_test, include_llm=include_llm)
    failure_type = None
    if not after["ok"]:
        failed_packages = {log["package"] for log in install_logs if not log["installed"]}
        failure_type = "dependency_install_failed" if failed_packages else "dependency_missing"
    return {
        **after,
        "auto_install": auto_install,
        "install_logs": install_logs,
        "failure_type": failure_type,
    }
