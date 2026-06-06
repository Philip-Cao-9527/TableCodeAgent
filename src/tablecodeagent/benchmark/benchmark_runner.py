from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from tablecodeagent.benchmark.real_api_code_agent import (
    MODE,
    load_env_file,
    read_json,
    run_real_api_code_agent,
)
from tablecodeagent.tracing.logger import make_result_dir


DEFAULT_ENV_FILE = Path("configs/api/local/provider_chatanywhere.env")


def _resolve_api_config(env_file: Path) -> tuple[str | None, str | None, str | None]:
    if not env_file.exists():
        return None, None, None
    env = load_env_file(env_file)
    model_name = env.get("MINI_CLAUDE_MODEL")
    api_base = env.get("MINI_CLAUDE_API_BASE") or env.get("OPENAI_BASE_URL")
    api_key = env.get("OPENAI_API_KEY") or env.get("ANTHROPIC_API_KEY")
    return model_name, api_base, api_key


def _task_label(task_dirs: list[Path], task_group: str | None) -> str:
    if task_group:
        return task_group
    if len(task_dirs) == 1:
        try:
            return str(read_json(task_dirs[0] / "task.json").get("id") or task_dirs[0].name)
        except Exception:
            return task_dirs[0].name
    return f"multiple-{len(task_dirs)}"


def _write_summary(result_dir: Path, results: list[dict[str, Any]]) -> Path:
    summary = {
        "benchmark_category": "real_api_code_agent",
        "mode": MODE,
        "result_dir": str(result_dir),
        "result_count": len(results),
        "passed_count": sum(1 for result in results if result.get("passed") is True),
        "skipped_count": sum(1 for result in results if result.get("skipped") is True),
        "failed_count": sum(
            1
            for result in results
            if result.get("skipped") is not True and result.get("passed") is not True
        ),
        "results": results,
    }
    summary_path = result_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary_path


async def run_real_api_benchmark(
    *,
    task_dirs: list[Path],
    env_file: Path = DEFAULT_ENV_FILE,
    task_group: str | None = None,
    result_root: Path = Path("benchmarks/results"),
) -> tuple[Path, list[dict[str, Any]]]:
    model_name, api_base, api_key = _resolve_api_config(env_file)
    result_dir = make_result_dir(
        mode=MODE,
        model_name=model_name,
        task_label=_task_label(task_dirs, task_group),
        root=result_root,
    )
    results: list[dict[str, Any]] = []
    for task_dir in task_dirs:
        result = await run_real_api_code_agent(
            task_dir=task_dir,
            result_dir=result_dir,
            env_file=env_file,
            model_name=model_name,
            api_base=api_base,
            api_key=api_key,
        )
        results.append(result)
    _write_summary(result_dir, results)
    return result_dir, results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the real API TableCodeAgent code benchmark.")
    parser.add_argument("--env", default=str(DEFAULT_ENV_FILE), help="Path to local API env file.")
    parser.add_argument("--task-dir", action="append", required=True, help="Benchmark task directory. Can be repeated.")
    parser.add_argument("--task-group", default=None, help="Readable task group label for the result directory.")
    parser.add_argument("--result-root", default="benchmarks/results", help="Benchmark result root directory.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result_dir, results = asyncio.run(run_real_api_benchmark(
        task_dirs=[Path(value) for value in args.task_dir],
        env_file=Path(args.env),
        task_group=args.task_group,
        result_root=Path(args.result_root),
    ))
    print(f"result_dir: {result_dir}")
    print(f"results: {result_dir / 'results.jsonl'}")
    print(f"summary: {result_dir / 'summary.json'}")
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    failed = [result for result in results if result.get("skipped") is not True and result.get("passed") is not True]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
