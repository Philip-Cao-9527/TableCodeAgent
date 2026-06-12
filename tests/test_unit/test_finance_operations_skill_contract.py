from __future__ import annotations

from pathlib import Path

from mini_claude.frontmatter import parse_frontmatter


def test_finance_operations_project_skill_is_parseable_and_has_agent_metadata() -> None:
    skill_path = Path(".claude/skills/finance-operations/SKILL.md")
    agent_path = Path(".claude/skills/finance-operations/agents/agent.yaml")

    parsed = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
    agent_text = agent_path.read_text(encoding="utf-8")

    assert parsed.meta["name"] == "finance-operations"
    assert "应收账款" in parsed.meta["description"]
    assert "输入输出约定" in parsed.body
    assert "证据与验证要求" in parsed.body
    assert "display_name: 财务运营应收回款分析" in agent_text
    assert "requires_real_api: false" in agent_text


def test_finance_operations_skill_does_not_leak_benchmark_answers_or_helpers() -> None:
    skill_text = Path(".claude/skills/finance-operations/SKILL.md").read_text(encoding="utf-8")
    agent_text = Path(".claude/skills/finance-operations/agents/agent.yaml").read_text(encoding="utf-8")
    combined = skill_text + "\n" + agent_text

    forbidden = [
        "3150",
        "1700",
        "INV-100",
        "PAY-00",
        "build_finance",
        "run_finance_operations",
        "tablecodeagent.workflows.finance_operations",
        "tests.test_workflows.finance_operations",
        "allowed_project_helpers",
        "solve_py_suggestion",
    ]

    for marker in forbidden:
        assert marker not in combined
