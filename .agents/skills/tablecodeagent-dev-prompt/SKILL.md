---
name: tablecodeagent-dev-prompt
description: 为 TableCodeAgent 仓库生成可直接交给 Codex/Agent 执行的中文项目化开发 prompt。用户要求使用 $tablecodeagent-dev-prompt，或要求为 TableCodeAgent 的普通代码实现、修复治理、benchmark、trace、validation、runner、表格工具、Agent 工具注册、文档同步、skill/指令文件维护任务生成执行 prompt 时使用；Plan Mode prompt 改用 $tablecodeagent-plan-mode-prompt，代码评审 prompt 改用 $tablecodeagent-code-review-prompt。本 skill 只产出任务 prompt，不直接开始执行开发任务。
---

# TableCodeAgent 开发 Prompt

## 技能定位

生成一次具体 TableCodeAgent 开发、修复、治理或文档同步任务的执行 prompt。它的唯一主产物是一份能复制给 Codex/Agent 立刻执行的中文项目化开发 prompt，不是变量表、教程、结构规范、通用模板说明，也不是直接开始执行 prompt 中的开发任务。

Plan Mode prompt 交给 `$tablecodeagent-plan-mode-prompt`。代码评审 prompt 交给 `$tablecodeagent-code-review-prompt`。如果一次开发 prompt 的执行依赖外部最新知识、官方 API、论文、benchmark、Agent 框架、LLM API 或工程实践，最终 prompt 可以要求后续执行者调用 `$web-search`，并把外部结论转成当前仓库可验证的工程约束、测试和证据。

## 技能交叉引用规则

如果生成的 prompt 需要明确要求后续执行者调用其他 skill，必须使用 `$skill-name` 形式，例如 `$web-search`。不要只写反引号包裹的 skill 名称，也不要把 skill 路由写成普通文件路径。

只有在说明源码位置、必读文件或验证证据时，才写 `.agents/skills/<skill-name>/...` 文件路径。

## 使用流程

1. 先确认用户要的是“生成开发执行 prompt”，不是直接执行修复、直接进入 Plan Mode 或直接做代码评审。
2. 读取当前仓库规则和任务相关材料，默认至少包括 `.codex/AGENTS.md`、`README.md`、`docs/reproduce/tablecodeagent_architecture.md`、`docs/reproduce/why_table_code_agent.md`，以及本轮涉及的真实调用链、task、脚本、文档或 skill 文件。
3. 读取 `references/prompt-template.md` 作为底稿，只保留本轮适用段落，不保留空占位符、旧路径或模板说明。
4. 从用户输入和仓库材料中提取：
   - 仓库路径，默认要求执行者以“当前仓库”为准并现场核对。
   - 任务类型：普通代码实现、修复治理、benchmark / trace / validation / runner、表格工具、Agent 工具注册、文档同步、skill / 指令文件维护。
   - 问题背景、目标现象、强制边界、禁止修改范围和必做 TODO。
   - 必读文件、真实入口、真实调用链、真实测试入口和证据路径要求。
   - 版本、README、架构文档、修复报告和真实 API / `SKIP` 边界。
5. 按本轮任务删减和填充底稿，生成一个完整、连续、可复制、可执行的中文 prompt。
6. 输出前将生成的 prompt 保存为临时草稿或放入可检查文件，并运行本 skill 的专项校验脚本：

```powershell
python -X utf8 .agents/skills/tablecodeagent-dev-prompt/scripts/validate_tablecodeagent_dev_prompt.py <prompt_path>
```

7. 如果脚本失败，必须根据缺失项补齐 prompt 并复跑，直到通过；如果仍有无法验证边界，必须在最终回答中明确写出剩余不可验证项。该脚本只检查关键结构和质量约束是否保留，不判断具体任务内容是否已经完全覆盖用户意图。
8. 输出最终 prompt。代码块前最多一句中文引导，代码块后不要追加正文。

## 默认补全规则

- 仓库路径：优先使用用户给出的路径；没有明确路径时写“当前仓库”，并要求执行者先核对真实工作目录。
- 语言：全程简体中文；代码、命令、报错原文、文件路径、API 字段名、模型名、库名、域名和专有名词保留英文原文。
- 修改策略：默认最小必要改动，先读入口、调用链、工具注册、数据路径和验证方式，再改代码；但“最小”必须服从业务口径、工程分层、可验证闭环和评测可信度，不能为了少改几行保留错误 benchmark 口径、弱 JSON 契约、helper 暴露或失败归因缺口。
- 路径核对：要求执行者用 `rg --files` 或等价命令刷新当前仓库真实路径，不沿用历史报告里的旧入口、旧脚本或旧目录。
- 版本策略：用户未明确要求升版时，沿用当前仓库版本，不主动 bump；只有核心代码、可执行能力、工具协议、benchmark / trace / validation / runner 等实质变化才评估版本号与修复报告。
- 文档与报告：纯文档、skill、指令文件、格式、注释类调整不触发修复报告或版本号变更；核心行为变化才按 `.codex/AGENTS.md` 规则处理。
- API 与密钥：禁止修改或提交 `configs/api/local/`、`.env`、真实 API key；需要真实 API 验证时只允许读取用户指定 env 文件，若用户未指定 env，则默认使用 `configs/api/local/deepseek.env`；env 缺失、网络失败、依赖缺失或模型行为不可控时记录 `SKIP` 或“未验证”，不能伪装成功。
- 外部实践：涉及 Agent benchmark、structured output、JSON Schema / Pydantic、tool schema、风控 / 营销 / 定价等工业业务流程，或当前仓库规则与外部规范可能冲突时，prompt 中可以要求执行者调用 `$web-search`；用户明确要求不联网时不要写入联网要求。
- TODO 分块：TODO 多时按 `A / B / C / D` 分块；单任务只保留一个任务块，不堆空标题。
- 不编造事实：当前版本、已实现能力、最近验证结果、文件存在性和 API 状态必须要求执行者从仓库或本轮命令刷新确认。

## Prompt 固定结构

除非用户明确要求极短版，最终 prompt 按下面顺序组织：

1. 任务开场：明确仓库、目标和“不允许跳过”的执行口吻。
2. `【硬性前置要求（必须先做）】`
3. `【项目定位与边界】`
4. `【版本、文档与报告策略】`
5. `【本次要完成的 TODO，必须全部落地】`
6. `【实现约束】`
7. `【测试与验证要求，必须执行】`
8. `【交付物要求】`
9. `【注意】`

不适用的空段落要删除或合并，不要保留空标题、无用变量或模板说明。

## 输出包裹规则

- 最终 prompt 必须整体放入单个 Markdown 文本块，方便用户一次性复制。
- 如果 prompt 内部包含三反引号，外层使用四反引号或更长围栏，例如 ````text。
- 不要用 XML / HTML 标签、引用块、普通列表或多个代码块替代单个文本块。
- 输出代码块前最多写一句中文引导，例如“下面是可直接执行的 prompt。”
- 输出代码块后不要追加正文，避免影响复制。

## TableCodeAgent 专项护栏

生成 prompt 时必须保留这些项目约束：

- TableCodeAgent 是面向复杂表格任务的轻量级 Coding Agent 项目，不是普通数据分析 Agent，也不要包装成 SFT、RL、RAG、Memory 增强或 SOTA 项目。
- 当前工程主线是复用 `mini_claude` baseline，逐步加入表格工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。
- 新增能力优先放在 `src/tablecodeagent/` 领域模块，再通过轻量 adapter 接入 `mini_claude` Agent Runtime；不要把核心计算、数据清洗、trace、benchmark、validation、runner 逻辑堆进 `src/mini_claude/tools.py`。
- 单个模块只承载一个清晰职责；大函数要拆成可命名、可单测、可复用的小函数。
- 错误处理必须可观测，不吞异常伪装成功；校验失败不能包装成“无数据”或“已通过”。
- Agent 输出 JSON、`answer.json`、tool input / output schema 和 task `output_contract` 必须是机器可校验契约，不能只靠“请输出 JSON”或顶层 key 列表；复杂场景优先使用 JSON Schema、Pydantic model 或同等方案。
- 真实 LLM Agent benchmark 必须采用 no-helper 口径。prompt 必须禁止把 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`、完整 workflow import 路径或 `build_*_report()` 这类解题入口公开给模型；如果需要验证项目内 helper，只能作为 unit / integration / smoke / regression 测试，不能命名为 benchmark，不能计入模型能力结论。
- benchmark、trace、runner、validation 改动必须区分非 API 模式和真实 LLM 模式；非 API 通过不能写成真实 LLM Agent 行为已验证。
- 不新增无依据的固定超时、轮次上限、重试上限、prompt / 工具输出 / CSV / trace 截断、静默降级或隐藏兜底。
- 不把未实现能力、未验证能力、`SKIP` 场景或推测写成已完成、已通过或事实。
- 不提交 `configs/api/local/`、`.env`、真实 API key、`__pycache__`、`.pyc` 或无关生成文件。

## 任务类型专项规则

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
- 要求真实 benchmark 采用 no-helper 口径，只允许给模型 task、数据文件、允许的通用库、公开输出契约和必要环境约束。
- 要求检查并移除会泄露解题入口的 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`；如果历史 task 仍保留这些字段，prompt 必须要求执行者先迁移为 no-helper task，再运行真实 benchmark。
- 要求 `output_contract` 与 pytest / validator 真实读取路径对齐，至少覆盖顶层 key、关键嵌套路径、字段类型和结构错误分类。不得把 `schema_check.passed=true` 等同于最终通过。
- 真实 LLM 验证必须记录 `api_called`、`skipped`、`llm_tool_call_observed`、`tool_call_count`、`validation.passed`、`failure_type` 等关键字段。
- 如果 env 缺失、网络失败、模型未调用工具或权限不足，必须如实写 `SKIP` 或未验证原因。

### 文档 / README / 架构记录

- 要求先读 `.codex/AGENTS.md` 的文档目录、修复报告和版本规则。
- README 面向项目总览，`docs/reproduce/` 面向开发证据和可复现记录，`docs/baseline/` 保留 baseline 教程型文档。
- 不要把历史状态写成最新状态；涉及“当前支持什么”必须从代码、脚本和最近验证结果确认。
- 纯文档调整默认不触发修复报告和版本号变更，最终 prompt 中要要求说明原因。

### skill / 指令文件维护

- 明确这是维护 Codex/Agent 指令资产，不是修改 TableCodeAgent 核心运行能力。
- 要求检查 skill 的存放目录、frontmatter、references 文件和可调用性边界；只有当前仓库真实存在 `agents/openai.yaml` 时才要求检查该文件。
- 默认不要求跑 TableCodeAgent smoke tests；验证重点是文件存在、UTF-8 可读、YAML / frontmatter 关键字段存在、`references/` 引用路径真实存在、脚本语法、校验脚本结果和无旧项目私有残留。
- 项目本地 `.agents/skills/<skill-name>` 不等于当前会话或其他会话一定自动发现；如果用户要求全局 `$skill-name` 可调用，必须另行同步到当前 Codex 实际发现的全局 skill 目录，本 skill 不默认执行全局同步。
- 最终总结必须说明本轮是否触发版本号、README、架构文档或修复报告；默认不触发时说明原因。

### 计划模式

- 不在本 skill 中生成 Plan Mode prompt。
- 用户要求 Plan Mode、只读探索、先提炼关键决策点、先让用户拍板时，改用 `$tablecodeagent-plan-mode-prompt`。

### 代码评审

- 不在本 skill 中生成代码评审 prompt。
- 用户要求 code review、审查 prompt、findings first 或默认不修复的审查任务时，改用 `$tablecodeagent-code-review-prompt`。

## 质量标准

- 最终 prompt 要像执行指令，不像建议、教程或泛泛计划。
- 约束必须具体、可检查、可落地。
- 交付物必须明确到文件改动、验证命令、证据路径、风险与未验证项。
- 不触发版本、README、架构文档或修复报告时，prompt 必须要求执行者在最终总结中说明原因。
- 不要机械复制其他项目的私有路径、版本号、测试命令、报告规则或发布流程。
- 不要为了显得完整堆空壳、堆模板、堆不可验证约束。

## 自检

输出 prompt 前逐条检查：

1. 是否明确本轮只是生成 prompt，不是已经执行开发任务。
2. 是否没有输出变量清单、可复用模板、结构规范或教程。
3. 是否已读取并遵守 `.codex/AGENTS.md` 和本轮真实仓库材料。
4. 是否写入 TableCodeAgent 的项目定位，而不是泛化成普通数据分析 Agent。
5. 是否要求先读 `.codex/AGENTS.md`、`README.md` 和相关真实调用链。
6. 是否避免硬编码过期版本、过期支持状态或不存在的文件。
7. 是否明确版本、文档和修复报告策略。
8. 是否针对任务类型加入 smoke、benchmark、trace、LLM/API、YAML/frontmatter、脚本语法或校验脚本验证要求。
9. 是否明确哪些场景必须写“未验证”或 `SKIP`，而不是伪装成功。
10. 是否保留 no-helper benchmark、tool schema、`output_contract`、LLM/API 与密钥安全边界。
11. 如果 prompt 中交叉引用其他 skill，是否统一使用 `$skill-name` 形式。
12. 是否已运行 `validate_tablecodeagent_dev_prompt.py`，并根据失败项循环修改到通过或说明不可验证边界。
13. 最终 prompt 是否完整放在一个 Markdown 文本块中；如果内部含 ```，外层围栏是否使用 ````text 或更长围栏。
14. 如果本轮是 Plan Mode 或代码评审 prompt，是否已路由到独立 skill，而不是在本 skill 里继续生成。
