# fix-report-v0.0.2-skill-authoring-agents-docs-20260606

## 1. 本轮问题 / 目标与范围

本轮只处理项目内 skill authoring 规范、仓库级 AGENTS fix-report 规则和 benchmark 结果文档补强，不修改 runtime、runner、tests 或 benchmark 结果产物本身。

本轮主要是规范、文档和证据链补齐，不代表 TableCodeAgent 核心 Agent 能力升级，不修改 `/root/.codex/skills/.system/skill-creator/SKILL.md`。

## 2. 改动文件清单

- [.tca/skills/.system/skill-creator/SKILL.md](../../.tca/skills/.system/skill-creator/SKILL.md)：补齐项目内 skill 的推荐目录结构、frontmatter、`agents/agent.yaml`、验证与边界规范。
- [.tca/skills/growth-campaign-audit/SKILL.md](../../.tca/skills/growth-campaign-audit/SKILL.md)：把不自然的中英混排规则改成中文主句表达，并保留必要英文术语。
- [.codex/AGENTS.md](../../.codex/AGENTS.md)：细化 fix-report 规则，明确关键证据必须使用文件级可跳转链接。
- [fix-report-v0.0.2-benchmark-restructure-20260606.md](./fix-report-v0.0.2-benchmark-restructure-20260606.md)：补齐 benchmark 关键文件链接，并重写失败原因证据链。
- [fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md](./fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md)：记录本轮 `.gitignore` 解释、skill 规范补强和 AGENTS 规则补充。

## 3. 项目内 `skill-creator` 规范补强

本轮把项目内 skill authoring 规范补到了可复用粒度，但仍保持在仓库内约束范围：

- 增加了项目内 skill 推荐目录树，明确 `skill-name/`、`SKILL.md`、`agents/agent.yaml`、`scripts/`、`references/`、`assets/` 的 required / optional 边界。
- 明确 `SKILL.md` 必须有合法 YAML frontmatter，且至少包含 `name`、`description`。
- 明确 `agents/agent.yaml` 改为项目内 skill 的必填文件，并要求与 `SKILL.md` 同步维护。
- 增加编写 / 审核清单，覆盖适用范围、不适用范围、目录结构、frontmatter、中文友好、输入输出、证据与验证、失败处理与 `SKIP`、仓库级 AGENTS 关系、全局 `/root/.codex/skills/...` 边界。
- 明确 `references/` 是按需读取，不应把大段资料重复塞进 `SKILL.md`。
- 补充了中文友好强约束：不要写“整句英文规则 + 中文补充”式混排，必要英文术语要嵌进中文句子中。

依据：

- [项目内 skill 规范文件](../../.tca/skills/.system/skill-creator/SKILL.md)
- [全局参考模板，只读未改](../../../../.codex/skills/.system/skill-creator/SKILL.md)
- [现有项目 skill 示例](../../.tca/skills/growth-campaign-audit/SKILL.md)
- [现有 `agents/agent.yaml` 示例](../../.tca/skills/growth-campaign-audit/agents/agent.yaml)

## 4. `.gitignore` 中为什么忽略 `benchmarks/results/`

依据仓库现状可以确认：

- [.gitignore](../../.gitignore) 明确包含 `benchmarks/results/`。
- 真实结果目录 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl)、[summary.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json)、[trace](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.real_api_code_agent.json)、[solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)、[answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)、[task.json 副本](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/task.json) 都位于该目录下。

因此忽略该目录的原因应写清为：

- 这些内容是 benchmark 运行产物，不是稳定源码。
- 目录按时间戳、模型名、任务名变化，数量会持续增长，不适合直接纳入版本控制。
- 其中包含 trace、workspace、任务文件副本、模型生成的 `solve.py`、执行产物 `answer.json`、外部校验用 `expected.json` 等审计材料，适合作为本地证据保留，不适合作为默认提交内容。
- 被 `.gitignore` 忽略不等于不重要；相反，fix-report 应通过具体文件级链接保留可审计证据，例如 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl)、[summary.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json)、[trace](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.real_api_code_agent.json)、[solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)。

## 5. 仓库级 AGENTS 规则补充

本轮只在 fix-report 规则附近补了一条更具体的约束：

- fix-report 必须附可跳转的文件路径交叉引用。
- 关键证据应优先给具体文件名，而不是只给文件夹名。
- benchmark、trace、workspace、generated code、answer、tests、docs 都应尽量给到可直接打开的文件级链接。

依据：

- [仓库级 AGENTS 规则](../../.codex/AGENTS.md)
- [本轮修正后的 benchmark fix-report](./fix-report-v0.0.2-benchmark-restructure-20260606.md)

## 6. 验证命令

结构和引用检查：

```bash
sed -n '1,260p' /root/workspace/TableCodeAgent/.tca/skills/.system/skill-creator/SKILL.md
sed -n '1,260p' /root/workspace/TableCodeAgent/.tca/skills/growth-campaign-audit/SKILL.md
sed -n '1,220p' /root/workspace/TableCodeAgent/.codex/AGENTS.md
sed -n '1,260p' /root/workspace/TableCodeAgent/docs/reproduce/fix-report-v0.0.2-benchmark-restructure-20260606.md
sed -n '1,260p' /root/workspace/TableCodeAgent/docs/reproduce/fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md
find /root/workspace/TableCodeAgent/benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent -maxdepth 1 -type f | sort
find /root/workspace/TableCodeAgent/benchmarks/tasks/growth_campaign_audit_001 -maxdepth 2 -type f | sort
grep -n 'benchmarks/results/' /root/workspace/TableCodeAgent/.gitignore
```

frontmatter、链接目标和目标文件存在性检查：

```bash
python - <<'PY'
from pathlib import Path
repo = Path("/root/workspace/TableCodeAgent")
skill = repo / ".tca/skills/.system/skill-creator/SKILL.md"
text = skill.read_text(encoding="utf-8")
assert text.startswith("---\n"), skill
frontmatter = text.split("---", 2)[1]
assert "name:" in frontmatter and "description:" in frontmatter, skill
for path in [
    repo / ".codex/AGENTS.md",
    repo / ".tca/skills/growth-campaign-audit/SKILL.md",
    repo / "docs/reproduce/fix-report-v0.0.2-benchmark-restructure-20260606.md",
    repo / "docs/reproduce/fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.real_api_code_agent.json",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.expected.json.for_external_check",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json",
    repo / "benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/expected.json",
    repo / "benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py",
]:
    assert path.exists(), path
print("skill_frontmatter_and_evidence_paths_ok")
PY
```

实际验证结果：

- 目标文件存在且可读：通过。
- `.tca/skills/.system/skill-creator/SKILL.md` frontmatter 中 `name`、`description`：通过。
- benchmark fix-report 新增关键交叉引用所指向的文件存在：通过。
- `.gitignore` 中 `benchmarks/results/` 规则与本文说明一致：通过。

## 7. 风险与备注

- 本轮未重跑真实 API benchmark；关于失败原因、生成代码位置、结果文件位置的结论只基于现有结果目录、任务测试文件和源码级路径处理逻辑修正文档。
- 本轮不修改 `/root/.codex/skills/.system/skill-creator/SKILL.md`，只参考其组织方式。
- 本轮不修改 `.gitignore` 规则本身，只补充其已有规则的仓库内解释与证据链。

## 8. 结论

本轮已完成项目内 `skill-creator` 规范补强、仓库级 AGENTS 文件级链接规则补充，以及 benchmark fix-report 关键证据链接和失败原因证据链修正。由于本轮只涉及 skill、AGENTS 和文档维护，不涉及核心运行能力变更，因此不修改版本号；未明确指定保存地址的修改记录已保存在 [fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md](./fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md)。
