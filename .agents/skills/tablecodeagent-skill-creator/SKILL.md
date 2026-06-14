---
name: tablecodeagent-skill-creator
description: 基于 TableCodeAgent 项目真实上下文创建或更新 `.agents/skills/` 下的项目本地 skill。用于用户要求沉淀可复用项目流程、prompt 生成流程、Plan Mode 流程或审查流程时使用；不用于一次性任务 prompt，不修改 TableCodeAgent 核心运行能力，也不创建系统或全局 skill。
---

# TableCodeAgent 本地 Skill Creator

## 技能定位

创建或更新 TableCodeAgent 仓库内 `.agents/skills/` 下的项目本地 skill。它只维护 Codex/Agent 指令资产，不修改 `src/mini_claude/`、`src/tablecodeagent/`、benchmark runner、trace、validation 或真实 API 链路。

不要把 TableCodeAgent 的完整项目规则粗暴塞进每个 skill。新 skill 只沉淀某个高频、边界清晰、输入输出稳定的流程；一次性开发、修复、评审或说明任务应生成一次性 prompt，而不是创建长期 skill。

## 什么时候创建新 skill

适合创建新 skill：

- 某类任务会反复出现，并且每次都有相似的必读材料、边界判断、输出格式和验证方式。
- 用户明确要求把流程沉淀到 `.agents/skills/`。
- 任务需要独立模板、审查框架、Plan Mode 收口、项目化 prompt 生成或固定质量门禁。
- 任务比 `.codex/AGENTS.md` 更具体，但又不属于一次具体代码实现。

不适合创建新 skill：

- 只是一次性执行 prompt，应使用 `$tablecodeagent-dev-prompt`。
- 只是要求 Plan Mode prompt，应使用 `$tablecodeagent-plan-mode-prompt`。
- 只是要求 code review prompt，应使用 `$tablecodeagent-code-review-prompt`。
- 只是几条长期仓库规则，应维护 `.codex/AGENTS.md`。
- 需求还不稳定，关键输入、输出和边界仍在变化。
- 想创建一个大而全的万能 skill。

## 与现有指令资产的边界

- `.codex/AGENTS.md`：仓库级 Codex 协作、语言、编码、测试、版本、报告和 Git 底线规则。
- `$tablecodeagent-dev-prompt`：普通开发、修复、benchmark、trace、validation、runner、文档同步和 skill/指令文件维护的执行 prompt 生成。
- `$tablecodeagent-plan-mode-prompt`：只生成要求执行者使用 Plan Mode 的中文任务 prompt。
- `$tablecodeagent-code-review-prompt`：只生成代码评审任务 prompt。
- 本 skill：创建或更新项目本地 skill 本身，不负责生成普通执行 prompt、Plan Mode prompt 或 review prompt 的具体任务内容。

项目本地 `.agents/skills/<skill-name>` 不等于当前会话或其他会话一定自动发现。若用户要求全局 `$skill-name` 可调用，需要另行同步到当前 Codex 实际发现的全局 skill 目录；本 skill 不默认做全局同步。

跨 skill 调用或路由必须写成 `$skill-name`，例如 `$tablecodeagent-dev-prompt`。只有在说明源码位置、必读文件或验证证据时，才写 `.agents/skills/<skill-name>/...` 文件路径。

## 必读文件

触发后先读取：

1. `.codex/AGENTS.md`
2. `README.md`
3. `docs/reproduce/tablecodeagent_architecture.md`
4. `docs/reproduce/why_table_code_agent.md`
5. `.agents/skills/tablecodeagent-dev-prompt/SKILL.md`
6. 本轮目标 skill 已有文件；如果是新增，则读取同类已有 skill 的 `SKILL.md`、`agents/openai.yaml` 和被引用的 `references/*.md`
7. 需要写模板时读取 `references/skill-template.md`

开始写文件前先运行 `rg --files .agents .codex docs` 或等价命令核对真实路径。

## 使用流程

1. 判断用户需求是否值得沉淀为 skill；不值得时，改为生成一次性 prompt 并说明原因。
2. 确认 skill 名称：使用小写字母、数字和连字符；不要使用 `skill-creator` 或 `skills-creator` 裸名；优先使用 `tablecodeagent-` 前缀避免和系统 skill 冲突。
3. 明确唯一职责、触发场景、不适用场景、必读文件、引用模板、输出格式和验证方式。
4. 只创建必要文件：
   - `SKILL.md` 必须有。
   - `agents/openai.yaml` 在本仓库现有 skill 风格需要 UI 元数据时创建。
   - `references/*.md` 只在需要可复用模板、长检查清单或示例底稿时创建。
   - 不创建空目录、空模板、未来占位文件、README、CHANGELOG 或辅助说明文档。
5. 写入内容时只迁移结构思想和写法，不复制其他项目私有路径、版本号、浏览器扩展约束、旧测试命令或发布规则。
6. 如果本轮只是 skill/指令文件调整，最终说明按 `.codex/AGENTS.md` 不触发修复报告和版本号变更。

## 输出要求

创建或更新 skill 时，产物必须满足：

- `SKILL.md` frontmatter 至少包含 `name` 和 `description`。
- `description` 写清触发场景和边界，不写空泛口号。
- `SKILL.md` 必须说明何时读取 `references/`，并且引用路径真实存在。
- `agents/openai.yaml` 只写必要 `interface.display_name`、`interface.short_description`、`interface.default_prompt`。
- `agents/openai.yaml` 的 `default_prompt` 如果要求使用某个 skill，必须写成 `$skill-name`。
- 中文内容自然、可执行，不保留英文脚手架说明、空标题、空占位符或一次性任务残留。

## 验证要求

完成后至少执行：

1. `rg --files .agents/skills`，确认新增或修改文件存在。
2. 使用 `python -X utf8` 或等价方式读取本轮新增 / 修改的 `.md` 和 `.yaml` 文件，确认 UTF-8 可读。
3. 检查每个新增 / 修改的 `SKILL.md` frontmatter 存在 `name` 和 `description`，且名称符合小写字母、数字和连字符。
4. 检查每个 `agents/openai.yaml` 可读，并包含 `interface.display_name`、`interface.short_description`、`interface.default_prompt`。
5. 检查 `SKILL.md` 中提到的 `references/*.md` 文件真实存在，没有引用不存在路径。
6. 检查没有旧项目私有残留。
7. 运行 `git diff -- .agents/skills`，确认改动范围只在预期 skill 文件内。

默认不运行 TableCodeAgent smoke tests、benchmark 或真实 API，因为本 skill 只维护指令资产。
