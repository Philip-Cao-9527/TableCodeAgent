---
name: tablecodeagent-plan-mode-prompt
description: 为 TableCodeAgent 仓库生成要求 Codex 使用 Plan Mode 的中文任务 prompt。用于用户希望先只读探索、先提炼 2 到 4 个关键决策点、先给选择空间并等待拍板后再实现的任务；只生成 Plan Mode prompt，不直接执行计划、不修改代码、不替用户拍板。
---

# TableCodeAgent Plan Mode Prompt

## 技能定位

生成一份可复制给 Codex/Agent 的中文 Plan Mode prompt。这个 skill 不直接执行计划、不直接修改文件、不生成报告、不替用户做技术拍板。

它适合高风险、多阶段、目录归属或职责拆分未定、prompt 输出边界未定、验证深度未定、版本/报告策略需要用户选择的任务。普通执行 prompt 使用 `$tablecodeagent-dev-prompt`，代码评审 prompt 使用 `$tablecodeagent-code-review-prompt`。

跨 skill 调用或路由必须写成 `$skill-name`。只有在说明源码位置、必读文件或验证证据时，才写 `.agents/skills/<skill-name>/...` 文件路径。

## 必读文件

生成 prompt 前先读取：

1. `.codex/AGENTS.md`
2. `README.md`
3. `docs/reproduce/tablecodeagent_architecture.md`
4. `docs/reproduce/why_table_code_agent.md`
5. 本轮相关 skill、prompt、调用链或文档
6. `references/plan-template.md`

开始前先运行 `rg --files .agents .codex docs` 或等价命令核对真实路径。

## Plan Mode prompt 必须要求执行者

- 先进入 Plan Mode，不跳过计划阶段直接实现。
- 只做只读探索、阅读、搜索、静态分析和必要的非破坏性核对。
- 禁止编辑文件、禁止 `apply_patch`、禁止新增报告、禁止删除文件、禁止修改版本号、禁止运行会改变仓库状态的命令。
- 先阅读 `.codex/AGENTS.md`、`README.md`、架构文档、项目动机文档和本轮相关 skill / prompt / 调用链。
- 提炼 2 到 4 个真正需要用户拍板的关键决策点。
- 决策点聚焦目录归属、职责拆分、prompt 输出边界、验证深度、版本/报告策略等大方向。
- 不把函数名、变量名、琐碎文件名、能由仓库事实确认的问题或用户已写死的边界包装成用户决策。
- 用户选择后再收敛成可执行计划。

## 使用流程

1. 确认用户要的是 Plan Mode prompt，而不是直接实现或普通执行 prompt。
2. 读取必读文件和 `references/plan-template.md`。
3. 从用户输入中提取仓库路径、任务目标、硬性边界、相关文件、需要决策的大方向、后续验证深度和交付物要求。
4. 生成一个完整、连续、可复制的 Plan Mode prompt。

## 输出要求

- 最终 prompt 必须整体放入一个 Markdown 文本块。
- 如果 prompt 内部包含三反引号，外层使用四反引号或更长围栏。
- 输出代码块前最多写一句中文引导；输出代码块后不要追加正文。
- 不保留空占位符、旧项目路径、旧项目命令或模板说明。

## 自检

输出前检查：

1. 是否明确这是生成 Plan Mode prompt，不是直接执行计划。
2. 是否写入 TableCodeAgent 项目定位和只读边界。
3. 是否要求先读真实仓库和相关 skill / prompt / 调用链。
4. 是否把关键决策控制在 2 到 4 个。
5. 是否没有替用户拍板。
6. 是否没有把琐碎实现细节包装成决策点。
