---
name: tablecodeagent-code-review-prompt
description: 为 TableCodeAgent 仓库生成代码评审任务 prompt。用于用户要求生成 code review、发布前风险审查、当前 diff/commit/指定文件审查 prompt 时使用；默认只生成审查任务 prompt，不直接 review，不直接修复代码。
---

# TableCodeAgent Code Review Prompt

## 技能定位

生成一份可复制给 Codex/Agent 的 TableCodeAgent 代码评审 prompt。这个 skill 默认不直接审查当前代码、不修改文件、不修复问题；产物是要求后续执行者完成审查并生成独立 Markdown review 报告的 prompt。

普通开发执行 prompt 使用 `$tablecodeagent-dev-prompt`。Plan Mode prompt 使用 `$tablecodeagent-plan-mode-prompt`。

跨 skill 调用或路由必须写成 `$skill-name`。只有在说明源码位置、必读文件或验证证据时，才写 `.agents/skills/<skill-name>/...` 文件路径。

## 必读文件

生成 prompt 前先读取：

1. `.codex/AGENTS.md`
2. `README.md`
3. `docs/reproduce/tablecodeagent_architecture.md`
4. `docs/reproduce/why_table_code_agent.md`
5. 本轮审查范围相关文件、diff、报告或任务材料
6. `references/review-template.md`

开始前先运行 `rg --files .agents .codex docs` 或等价命令核对真实路径。

如果用户明确要求联网检索，或本轮审查涉及近期可能变化的外部规范、LLM API、Agent 框架、benchmark 规则、第三方库行为、论文方法或工程实践，可以在生成的 review prompt 中要求执行者调用 `$web-search` 辅助定位问题或支撑审查结论。用户明确要求不联网时不要写入该要求。

## 审查 prompt 必须写入的要求

- findings first，按严重级别排序。
- 每条 finding 必须包含文件路径、证据、影响、最小修复建议和验证建议。
- 审查前必须先建立项目化风险地图，而不是套固定清单。
- 风险地图要覆盖复杂表格任务口径、Agent 工具暴露、no-helper benchmark、JSON / Pydantic 契约、trace / validation 证据、文档是否把历史状态写成当前状态、真实 API 与非 API 验证边界。
- 默认生成单独 Markdown review 报告；如果用户未指定路径，按项目习惯选择 `docs/reproduce/` 下合适文件名，并说明原因。
- 没有发现明确问题时，也必须说明已审查范围、剩余风险和测试缺口，不能硬凑 finding。
- 默认不直接修复代码；如果用户要求审查并修复，prompt 也必须先要求 findings first，再进入修复闭环。
- 如果启用 `$web-search`，必须要求执行者优先查官方文档、论文、作者仓库或 benchmark 主页，并把外部资料转化为本仓库可验证的审查证据；不能只用外部资料替代本地代码、diff、测试或 trace 证据。

## 使用流程

1. 确认用户要的是 code review prompt，不是直接 review 或直接修复。
2. 明确审查范围：当前分支 diff、指定 commit、PR diff、指定文件、指定报告或用户描述的改动范围。
3. 读取必读文件和 `references/review-template.md`。
4. 判断是否需要在最终 prompt 中加入 `$web-search`：用户明确要求时必须加入；审查依赖最新外部资料时可以加入；纯本地 diff 足以判断且用户未要求联网时不要强行加入。
5. 把 TableCodeAgent 专属风险地图写进最终 prompt，并按本轮范围裁剪。
6. 输出一个完整、连续、可复制的 code review prompt。

## 输出要求

- 最终 prompt 必须整体放入一个 Markdown 文本块。
- 如果 prompt 内部包含三反引号，外层使用四反引号或更长围栏。
- 输出代码块前最多写一句中文引导；输出代码块后不要追加正文。
- 不保留旧项目私有路径、旧版本号、浏览器扩展约束、旧测试命令或空占位符。

## 自检

输出前检查：

1. 是否明确这是生成 review prompt，不是直接 review。
2. 是否写清审查目标、范围、对比基准和默认不修改代码边界。
3. 是否要求项目化风险地图，而不是固定清单。
4. 是否包含 TableCodeAgent 专属审查重点。
5. 是否要求独立 Markdown review 报告。
6. 是否覆盖没有 finding 时的输出规则。
7. 如果写入 `$web-search`，是否说明了触发条件、来源优先级、外部资料与本地证据的关系，以及用户禁止联网时不调用。
