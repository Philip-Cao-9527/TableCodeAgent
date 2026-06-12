from __future__ import annotations

from pathlib import Path

from mini_claude.prompt import build_system_prompt, load_claude_md
from mini_claude.skills import build_skill_descriptions, reset_skill_cache


def test_claude_md_and_rules_are_loaded_from_project_root(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    nested = project / "workspaces" / "demo"
    rules = project / ".claude" / "rules"
    nested.mkdir(parents=True)
    rules.mkdir(parents=True)
    (project / "CLAUDE.md").write_text("MiniClaude 项目级规则入口", encoding="utf-8")
    (rules / "workflow-boundaries.md").write_text("product workflow / no-helper 边界规则", encoding="utf-8")

    monkeypatch.chdir(nested)

    loaded = load_claude_md()

    assert "MiniClaude 项目级规则入口" in loaded
    assert "product workflow / no-helper 边界规则" in loaded


def test_project_rules_and_skill_metadata_share_system_prompt(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    skill_dir = project / ".claude" / "skills" / "demo-skill"
    rules = project / ".claude" / "rules"
    skill_dir.mkdir(parents=True)
    (skill_dir / "agents").mkdir()
    rules.mkdir(parents=True)
    (project / "CLAUDE.md").write_text("本地验证优先于真实 API", encoding="utf-8")
    (rules / "context.md").write_text("上下文必须压缩后进入 Agent Loop", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: 演示 skill\n"
        "when_to_use: 验证 prompt 注入\n"
        "---\n"
        "执行 demo skill。\n",
        encoding="utf-8",
    )
    (skill_dir / "agents" / "agent.yaml").write_text(
        "display_name: 演示 Agent\n"
        "short_description: 元数据必须进入 system prompt\n"
        "requires_real_api: false\n"
        "evidence_fields:\n"
        "  - validation.passed\n"
        "boundaries:\n"
        "  - 不覆盖 CLAUDE.md\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(project)
    reset_skill_cache()
    try:
        skills = build_skill_descriptions()
        system_prompt = build_system_prompt()
    finally:
        reset_skill_cache()

    assert "/demo-skill" in skills
    assert "Agent display: 演示 Agent" in skills
    assert "Evidence fields: validation.passed" in skills
    assert "本地验证优先于真实 API" in system_prompt
    assert "上下文必须压缩后进入 Agent Loop" in system_prompt
    assert "/demo-skill" in system_prompt
    assert "元数据必须进入 system prompt" in system_prompt
