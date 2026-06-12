from __future__ import annotations

from pathlib import Path

from tests.test_workflows.growth_campaign_audit import run_growth_campaign_audit


def test_growth_full_workflow_matches_expected_check() -> None:
    report = run_growth_campaign_audit(Path("benchmarks/tasks/growth_campaign_audit_001"))

    assert report["validation"]["passed"] is True
    assert report["join_cardinality"]["row_expansion_detected"] is True
    assert "不能静默 drop duplicates" in "\n".join(report["warnings"])
