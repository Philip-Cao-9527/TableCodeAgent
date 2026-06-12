# TableCodeAgent 项目级规则

本文件是 MiniClaude 的项目级长期总规则入口。MiniClaude 运行时会向上查找 `CLAUDE.md`，并加载当前工作目录下 `.claude/rules/*.md`。

## 核心边界

- TableCodeAgent 是面向复杂表格任务的轻量级 Coding Agent 项目，不是普通一次性数据分析脚本。
- 必须区分三层工作流：`product workflow` 是面向用户任务的主 Agent Loop；`helper-assisted workflow` 是内部确定性 oracle、fixture 和回归资产；`no-helper capability evaluation` 是真实 benchmark，只评估模型基于公开 task、数据和 schema 自主生成代码的能力。
- deterministic oracle 不是产品主流程，不能把 `tests/test_workflows/` 的结果写成真实 LLM Agent 能力。
- no-helper benchmark 不得公开 `expected.json`、`tests/test_workflows`、`tablecodeagent.workflow`、`tablecodeagent.product_agent`、`build_*_report()`、`run_*()`、`implementation_hints`、`allowed_project_helpers` 或 `solve_py_suggestion`。

## 验证优先级

- 本地验证优先于真实 API：unit tests、integration tests、simulated Agent outputs、sandbox、schema、pytest 和 validator 稳定后，才允许运行真实 API benchmark。
- 真实 API 不是发现普通本地质量问题的第一道防线。如果真实 API 暴露了本地测试可提前覆盖的问题，先补本地回归，再决定是否复测。
- API key、`.env`、`configs/api/local/` 和 secret 不得写入代码、文档或 trace 输出。
- `SKIP`、env 缺失、API 失败、工具未调用、schema 不匹配、pytest 失败、validator 失败或未生成 `answer.json` 必须按真实状态记录，不能伪装通过。

## 产品态 Agent Loop

- 产品态主 Loop 位于 `src/tablecodeagent/workflow/`，通过 MiniClaude 的 `run_table_product_workflow` tool 接入 Agent Loop。
- 产品态 Loop 应覆盖任务解析、表格发现、字段画像、上下文压缩、工具策略、候选代码执行、sandbox、schema/pytest/validator 反馈、repair loop、trace 归因和 report-scoped analysis memory。
- context engineering 必须控制上下文边界：system instructions、rules、skills、memory、tool outputs、trace summaries 和 repair feedback 都要有明确用途，不得无限堆叠。
- analysis memory 当前为 report-scoped，除非另有实现和验证，不得写成跨线程或长期企业记忆。

## 项目 skill 与规则职责

- `CLAUDE.md`：MiniClaude 项目级长期总规则入口。
- `.claude/rules/*.md`：按主题拆分的补充规则。
- `.codex/AGENTS.md`：Codex 协作、仓库开发治理和本地验证要求。
- `.claude/skills/*/SKILL.md`：具体场景 skill 说明、触发策略、输入输出与验证要求。
- 项目 skill 正式根目录是 `.claude/skills/`；不得新增或恢复 `.tca/skills/` 双轨目录。
