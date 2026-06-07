from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

from tablecodeagent.runtime.dependency import ensure_runtime_dependencies
from tablecodeagent.runtime.sandbox import run_python_in_sandbox, run_tests_in_sandbox


def test_sandbox_runs_fixed_solve_py_and_pytest(tmp_path: Path) -> None:
    dependency = ensure_runtime_dependencies(include_test=True, auto_install=True)
    assert dependency["ok"] is True

    source_task = Path("benchmarks/tasks/growth_campaign_audit_001")
    workspace = tmp_path / "growth_campaign_audit_001.fixed_solve_py"
    shutil.copytree(source_task, workspace)
    solve_path = workspace / "solve.py"
    solve_path.write_text(textwrap.dedent(
        """
        from __future__ import annotations

        import json
        from pathlib import Path

        from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report


        def main() -> None:
            task_dir = Path(__file__).resolve().parent
            report = build_growth_campaign_audit_report(task_dir)
            (task_dir / "answer.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\\n",
                encoding="utf-8",
            )


        if __name__ == "__main__":
            main()
        """
    ).strip() + "\n", encoding="utf-8")

    sandbox_env = {"PYTHONPATH": str(Path("src").resolve())}
    run_result = run_python_in_sandbox(
        "solve.py",
        workspace_dir=workspace,
        timeout_seconds=30,
        env=sandbox_env,
    )
    test_result = run_tests_in_sandbox(
        workspace_dir=workspace,
        test_path="tests/test_solution.py",
        timeout_seconds=30,
        env=sandbox_env,
    )

    answer = json.loads((workspace / "answer.json").read_text(encoding="utf-8"))
    assert run_result["exit_code"] == 0, run_result
    assert test_result["exit_code"] == 0, test_result
    assert answer["join_cardinality"]["row_expansion_detected"] is True


def test_sandbox_uses_utf8_for_unicode_stdout(tmp_path: Path) -> None:
    workspace = tmp_path / "unicode_solve"
    workspace.mkdir()
    solve_path = workspace / "solve.py"
    solve_path.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            print("✅ answer saved")
            """
        ).strip() + "\n",
        encoding="utf-8",
    )

    run_result = run_python_in_sandbox(
        "solve.py",
        workspace_dir=workspace,
        timeout_seconds=30,
    )

    assert run_result["exit_code"] == 0, run_result
    assert "✅ answer saved" in run_result["stdout"]
