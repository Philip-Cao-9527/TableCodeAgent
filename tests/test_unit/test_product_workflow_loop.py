from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tablecodeagent.workflow import run_product_workflow


DEMO_TASK = Path("benchmarks/tasks/demo_table_001")


def test_product_workflow_prepares_context_and_code_brief() -> None:
    result = run_product_workflow(task_dir=str(DEMO_TASK))

    assert result["status"] == "needs_code_generation"
    assert result["next_action"] == "generate_candidate_code"
    assert "data" in result["tables"]
    assert result["context_package"]["tables"]["data"]["columns"]
    assert result["tool_strategy"]
    assert "output_contract" in result["code_generation_brief"]


def test_product_workflow_repair_loop_passes_after_second_candidate(tmp_path: Path) -> None:
    bad_code = "from pathlib import Path\nPath('answer.json').write_text('{bad json', encoding='utf-8')\n"
    fixed_code = textwrap.dedent(
        """
        from __future__ import annotations

        import json
        from pathlib import Path

        def main() -> None:
            Path("answer.json").write_text(json.dumps({"answer": 32.5}) + "\\n", encoding="utf-8")

        if __name__ == "__main__":
            main()
        """
    )

    result = run_product_workflow(
        task_dir=str(DEMO_TASK),
        workspace_dir=str(tmp_path / "product_demo"),
        candidate_code_versions=[bad_code, fixed_code],
    )

    assert result["status"] == "passed"
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["failure_type"] in {"code_execution_failed", "answer_schema_mismatch"}
    assert result["attempts"][1]["passed"] is True
    assert result["repair_history"][0]["repair_instruction"]
    assert result["analysis_memory"][-1]["scope"] == "report-scoped"


def test_product_workflow_reports_unfixed_repair_failure(tmp_path: Path) -> None:
    wrong_code = textwrap.dedent(
        """
        from __future__ import annotations

        import json
        from pathlib import Path

        Path("answer.json").write_text(json.dumps({"answer": 1}) + "\\n", encoding="utf-8")
        """
    )

    result = run_product_workflow(
        task_dir=str(DEMO_TASK),
        workspace_dir=str(tmp_path / "product_unfixed"),
        candidate_code_versions=[wrong_code, wrong_code],
    )

    assert result["status"] == "repair_needed"
    assert result["next_action"] == "revise_candidate_code"
    assert result["failure_type"] == "validation_failed"
    assert len(result["repair_history"]) == 2
    assert result["validation"]["passed"] is False


def test_product_workflow_empty_or_missing_table_context_is_observable(tmp_path: Path) -> None:
    task_dir = tmp_path / "empty_task"
    task_dir.mkdir()
    (task_dir / "task.json").write_text(json.dumps({"id": "empty", "question": "no tables"}), encoding="utf-8")

    with pytest.raises(ValueError, match="requires at least one table"):
        run_product_workflow(task_dir=str(task_dir))
