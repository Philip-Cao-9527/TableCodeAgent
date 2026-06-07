---
name: tablecodeagent-dev-prompt
description: 为 TableCodeAgent 仓库生成可直接交给 Codex/Agent 执行的中文项目化开发 prompt。用户要求使用 $tablecodeagent-dev-prompt，或要求为 TableCodeAgent 的代码实现、修复治理、Plan Mode、评审、benchmark、trace、validation、runner、表格工具、Agent 工具注册、文档同步任务生成执行 prompt 时使用。只产出任务 prompt，不直接开始执行该 prompt 中的开发任务。
---

# TableCodeAgent 开发 Prompt 生成技能

生成可直接执行的项目化任务 prompt，不直接开始改代码。

这个 skill 的唯一主产物是“一份能复制给 Codex/Agent 立刻执行的中文 prompt”。不要把输出做成变量清单、结构规范、通用模板说明或 prompt 设计教程；除非用户明确要求维护 skill 本身，否则不要输出“可复用参数化模板”。

## 先做什么

1. 先确认本轮需求是“生成 prompt”，不是直接执行修复、开发或评审。
2. 读取 `references/prompt-template.md` 作为底稿，只把适合本次任务的段落填入最终 prompt；不保留空占位符。
3. 从用户输入中提取以下信息：
   - 仓库路径，默认 `/root/workspace/TableCodeAgent`
   - 任务类型：Plan Mode、执行修复、功能开发、代码评审、benchmark/trace/validation、文档同步、skill/指令文件维护
   - 问题背景或目标现象
   - 必做 TODO
   - 相关模块与真实调用链线索
   - 用户给出的强制约束
   - 必测范围与可接受的未验证边界
   - 交付格式
4. 如果用户没有补全全部信息，按 TableCodeAgent 默认约束补足，但不要编造事实；当前版本、已实现能力、最近验证结果必须要求执行者从仓库文件刷新确认。

## 默认补全规则

- 仓库路径：默认写 `/root/workspace/TableCodeAgent`。
- 语言：全程简体中文；代码、命令、报错、文件路径、API 字段名、模型名、库名保留英文原文。
- 修改策略：默认最小必要改动，先读入口、调用链、工具注册、数据路径和验证方式，再改代码；但“最小”必须以工业业务口径、工程分层、可验证闭环和评测可信度为前提，不能为了少改几行而保留错误 benchmark 口径、弱 JSON 契约、helper 暴露或失败归因缺口。
- 版本策略：用户未明确要求升版时，写“沿用当前仓库版本，不主动 bump；只有核心代码、可执行能力、工具协议、benchmark/trace/validation/runner 等实质变化才评估版本与修复报告”。
- 必读文件：默认至少包含 `.codex/AGENTS.md`、`README.md`、`docs/reproduce/tablecodeagent_architecture.md`、`docs/reproduce/why_table_code_agent.md`。
- 历史记录：若任务涉及回归、benchmark、trace、LLM 验证或工具行为，要求读取 `docs/reproduce/` 下与本轮直接相关的 fix report，不要堆无关报告。
- 核心代码：根据任务写入最小真实调用链，不要用过期文件清单替代阅读代码。
- 路径核对：生成 prompt 前必须用当前仓库真实文件刷新路径；不要沿用历史报告里的旧入口，例如已移除脚本、旧日期文档名或旧源码目录。
- API 与密钥：禁止修改或提交 `configs/api/local/`、`.env`、真实 API key；需要 LLM 验证时只允许读取用户指定 env 文件，若用户未指定真实 API env，则默认使用 `configs/api/local/deepseek.env`；env 缺失则记录 `SKIP`，不能伪装成功。
- 文档与报告：纯文档、skill、指令文件、格式、注释类调整不触发修复报告或版本号变更；核心行为变化才按 `.codex/AGENTS.md` 规则处理。
- 外部实践：涉及 Agent benchmark、structured output、JSON Schema / Pydantic、tool schema、风控/营销/定价等工业业务流程、或当前仓库规则与业务实践可能冲突时，prompt 中应允许执行者调用 `.agents/skills/academic-web-search` 检索官方文档、论文、benchmark 或工程实践；检索结论必须转化为本仓库可验证的实现、测试和 trace 证据。
- Prompt 包裹：最终回答中的完整 prompt 必须放在 Markdown 文本块里，方便用户一次性复制。禁止只用 `<prompt>...</prompt>`、引用块、普通段落或列表承载完整 prompt。
- 围栏长度：如果 prompt 内部包含 ``` 代码围栏，外层必须使用 ````text 或更长反引号围栏；外层围栏长度必须严格大于内部最长连续反引号长度，避免提前闭合。
- 单块输出：最终 prompt 必须作为一个连续文本块输出，不要拆成多个代码块，不要在代码块中途插入解释、截图说明或 Markdown 正文。

## Prompt 固定结构

除非用户要求极短版，最终 prompt 按下面顺序组织：

1. 任务开场，明确仓库、模式、目标和“不允许跳过”的执行口吻。
2. `【硬性前置要求（必须先做）】`
3. `【项目定位与边界】`
4. `【版本、文档与报告策略】`
5. `【本次要完成的 TODO，必须全部落地】`
6. `【实现约束】`
7. `【测试与验证要求，必须执行】`
8. `【交付物要求】`
9. `【注意】`

如果是 Plan Mode，把“测试与验证要求”改成“计划必须覆盖的验证设计”，并明确禁止改文件、禁止生成报告、禁止 apply patch。

如果是评审模式，把输出结构改成 findings first：按严重级别列问题，带文件路径、证据、影响和最小修复建议；默认不改代码。

## TableCodeAgent 项目化约束

生成 prompt 时必须保留这些护栏：

- TableCodeAgent 是面向复杂表格任务的轻量级 Coding Agent 项目，不是普通数据分析 Agent，也不要包装成 SFT、RL、RAG、Memory 增强或 SOTA 项目。
- 当前工程主线是复用 `mini_claude` baseline，逐步加入表格工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。
- 生成代码 prompt 时必须要求执行者面向工程和业务实践设计：先确认任务真实业务目标、评测想证明的能力、输入输出契约、失败可观测性和验收口径，再选择最小可落地实现。
- 新增能力优先放在 `src/tablecodeagent/` 领域模块，再通过轻量 adapter 接入 `mini_claude` Agent Runtime。
- 不把核心计算、数据清洗、trace、benchmark、validation、runner 逻辑堆进 `src/mini_claude/tools.py`。
- 单个模块只承载一个清晰职责；大函数要拆成可命名、可单测的小函数。
- 错误处理必须可观测，不吞异常伪装成功；校验失败不能包装成“无数据”或“已通过”。
- Agent 输出 JSON、`answer.json`、tool input/output schema 和 task `output_contract` 必须是机器可校验契约，不能只靠“请输出 JSON”或顶层 key 列表。prompt 应要求覆盖 validator / pytest 实际读取的关键嵌套字段、类型、枚举和语义校验边界；复杂场景优先写入 JSON Schema、Pydantic model 或同等方案。
- 真实 LLM Agent benchmark 必须采用 no-helper 口径。prompt 必须禁止把 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`、完整 workflow import 路径或 `build_*_report()` 这类解题入口公开给模型；如果需要验证项目内 helper，只能作为 unit / integration / smoke / regression 测试，不能命名为 benchmark，不能计入模型能力结论。
- 真实 API 测试 prompt 如未收到明确 env 路径，默认写 `configs/api/local/deepseek.env`，并要求执行者只核对变量名存在性，不输出 key/token/secret 值。
- 不新增无依据的固定超时、轮次上限、重试上限、prompt/工具输出/CSV/trace 截断。
- 不把未实现能力、未验证能力、`SKIP` 场景写成已完成或已通过。
- 不提交 `__pycache__`、`.pyc`、`.env`、`configs/api/local/` 或无关生成文件。

## 任务类型加料规则

### 表格工具 / 数据读取 / 查询

- 要求先阅读 `src/tablecodeagent/table_tools/`、`src/tablecodeagent/agent_tools.py`、相关 benchmark task 与 smoke 脚本。
- TODO 必须覆盖数据口径、输入格式、失败方式、错误可观测性和最小测试样例。
- 测试至少要求跑表格工具 smoke；涉及 Excel、多表、multi-header、merged cell 时加入对应任务验证。
- 禁止为了通过 demo 伪造 schema、伪造统计、伪造答案或跳过异常。

### Agent 工具注册 / tool schema / Runtime 分发

- 要求先阅读 `src/mini_claude/tools.py`、`src/mini_claude/agent.py`、`src/tablecodeagent/agent_tools.py` 和相关脚本。
- 必须验证模型可见 tool schema，以及 `mini_claude.tools.execute_tool()` 本地分发能返回可读结果。
- 不允许只改 schema 不接执行路径，也不允许只接执行路径但模型不可见。

### benchmark / runner / trace / validation

- 要求明确 runner 模式、输入任务目录、输出 `results.jsonl`、trace 路径、失败类型与指标口径。
- 要求真实 benchmark 采用 no-helper 口径：只允许给模型 task、数据文件、允许的通用库、公开输出契约和必要环境约束，禁止公开项目 workflow helper、完整 import 路径、`allowed_project_helpers`、`solve_py_suggestion` 或 `build_*_report()`。
- 要求检查并移除会泄露解题入口的 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`；如果历史 task 仍保留这些字段，prompt 必须要求执行者先迁移为 no-helper task，再运行真实 benchmark。
- 要求 `output_contract` 与 pytest / validator 真实读取路径对齐；至少覆盖顶层 key、关键嵌套路径、字段类型和结构错误分类。不得把 `schema_check.passed=true` 等同于最终通过。
- 必须区分非 API 模式和真实 LLM 模式；非 API 通过不能写成真实 LLM Agent 行为已验证。
- 真实 LLM 验证必须记录 `api_called`、`skipped`、`llm_tool_call_observed`、`tool_call_count`、`validation.passed`、`failure_type` 等关键字段。
- 如果 env 缺失、网络失败、模型未调用工具或权限不足，必须如实写 `SKIP` 或未验证原因。

### 文档 / README / 架构记录

- 要求先读 `.codex/AGENTS.md` 的文档目录与修复报告规则。
- README 面向项目总览，`docs/reproduce/` 面向开发证据和可复现记录，`docs/baseline/` 保留 baseline 教程型文档。
- 不要把历史状态写成最新状态；涉及“当前支持什么”必须要求从代码、脚本和最近验证结果确认。
- 纯文档调整默认不触发修复报告和版本号变更，最终 prompt 中要要求说明原因。

### skill / 指令文件维护

- 明确这是维护 Codex/Agent 指令资产，不是修改 TableCodeAgent 核心运行能力。
- 要求检查 skill 的存放目录、frontmatter、references 文件和可调用性边界；只有当前仓库真实存在 `agents/openai.yaml` 时才要求检查该文件。
- 默认不要求跑 TableCodeAgent smoke tests；验证重点是文件存在、YAML/frontmatter 可解析、路径已同步、最终说明不触发项目修复报告。
- 如果要让 `$skill-name` 在新对话可调用，优先同步到当前 Codex 实际发现的全局 skill 目录 `/root/.codex/skills/<skill-name>`。

### Plan Mode

- 明确只允许只读探索、静态分析和计划生成。
- 禁止编辑文件、禁止 `apply_patch`、禁止生成修复报告、禁止改版本号、禁止运行会改变仓库状态的命令。
- 最终必须只输出一个可执行计划，覆盖当前状态、文件级改动方案、验证方案、版本/报告策略、风险边界。

### 代码评审

- 默认不改代码。
- 输出必须 findings first，按严重级别排序，提供文件路径、证据、影响、最小修复建议。
- 没有发现明确问题时要直说，并列出剩余风险与验证缺口。

## 风格要求

- 最终 prompt 要像执行指令，不像建议、教程或泛泛计划。
- 约束必须具体、可检查、可落地；TODO 多时按 `A / B / C / D` 分块。
- 保留用户原话中的硬性边界，再做项目化归纳。
- 不要生硬照搬其他项目的模块名、测试命令、版本号、浏览器扩展约束。
- 不要在最终 prompt 前输出长解释；最多用一句话说明“下面是可直接执行的 prompt”。
- 最终 prompt 必须用 Markdown 文本块包裹。若内部包含 ```，外层使用 ````text；不要用 `<prompt>` 标签替代文本块。
- 输出代码块前最多写一句中文引导；输出代码块后不要追加额外正文，避免影响复制。

## 输出前自检

输出 prompt 前逐条检查：

1. 是否明确本轮只是生成 prompt，不是已经执行开发任务。
2. 是否没有输出变量清单、可复用模板或结构规范。
3. 是否写入 TableCodeAgent 的项目定位，而不是泛化成普通数据分析 Agent。
4. 是否要求先读 `.codex/AGENTS.md`、`README.md` 和相关真实调用链。
5. 是否避免硬编码过期版本、过期支持状态或不存在的文件。
6. 是否明确版本、修复报告和 docs 同步策略。
7. 是否针对任务类型加入了 smoke、benchmark、trace、LLM/API 或 YAML/frontmatter 验证要求。
8. 是否明确哪些场景必须写 `未验证` 或 `SKIP`，而不是伪装成功。
9. 是否最终交付格式包含文件改动、验证命令、证据路径、风险与未验证项。
10. 最终 prompt 是否完整放在一个 Markdown 文本块中，而不是普通正文、引用块、列表或 `<prompt>` 标签。
11. 如果最终 prompt 内含 ```，外层围栏是否使用 ````text 或更长围栏，且完整 prompt 没有被提前闭合或拆块。
