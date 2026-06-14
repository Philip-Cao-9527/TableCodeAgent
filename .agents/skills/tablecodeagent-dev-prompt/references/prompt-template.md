# TableCodeAgent 开发任务 prompt 底稿

本文件是 `.agents/skills/tablecodeagent-dev-prompt` 的内部参考模板。生成最终 prompt 时，删除不相关段落，把占位符替换成本轮真实任务信息；不要把本文件当“参数化模板”原样输出给用户。无法确认的信息应写成“必须先核对”，不要编造事实。

## 通用执行 prompt

````text
你要在当前仓库 `{{仓库路径或当前仓库}}` 完成一次“{{任务标题}}”任务。严格执行以下要求，不得跳过。

【硬性前置要求（必须先做）】

1. 不做任何修改前，必须先阅读并在进度里明确已读：
   - `.codex/AGENTS.md`
   - `README.md`
   - `docs/reproduce/tablecodeagent_architecture.md`
   - `docs/reproduce/why_table_code_agent.md`
   - `docs/reproduce/` 下与本轮任务直接相关的 fix report / 复现记录 / 实验记录
   - 本轮涉及的真实调用链代码、task、脚本、配置、文档或 skill 文件：`{{本轮相关文件}}`
2. 开始前先运行 `rg --files` 或等价命令核对真实仓库结构、真实调用链文件和真实测试入口；如果用户给出的路径不存在，必须如实说明。
3. 全程使用简体中文；代码、命令、报错原文、文件路径、API 字段名、模型名、库名、域名和专有名词保留英文原文。
4. 先理解真实入口、调用链、工具注册、数据路径、依赖顺序和验证方式，再做修改。
5. 不要回滚用户已有改动；遇到不相关 dirty 文件，记录并避开。
6. 不要把未验证写成已验证，不要把 `SKIP` 写成通过，不要把推测写成事实；无法确认时明确写“未验证”或“待确认”。

【项目定位与边界】

1. TableCodeAgent 是面向复杂表格任务的轻量级 Coding Agent 项目，目标是把表格数据处理、算法建模前置分析、业务决策推理、表格 benchmark 等任务组织成可复现、可验证、可审计、可迁移的程序化工作流。
2. 不要把项目缩窄成普通数据分析 Agent，也不要包装成 SFT、RL、RAG、Memory 增强或 SOTA 项目。
3. 当前工程主线是复用 `mini_claude` baseline，逐步加入表格工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。
4. 本轮任务范围：{{本轮任务范围}}。
5. 本轮明确不做：{{本轮不做什么}}。
6. 如果需要参考外部最新知识、官方 API、论文、benchmark、Agent 框架、LLM API 或工程实践，可以调用 `$web-search`；用户明确要求不联网时不要调用。

【版本、文档与报告策略】

1. 沿用当前仓库版本，不主动 bump；只有核心代码、可执行能力、工具协议、benchmark / trace / validation / runner 等实质变化才按 `.codex/AGENTS.md` 评估版本号。
2. 纯文档修改、README 更新、说明文字修正、skill / 指令文件调整、格式整理、注释修正，不触发修复报告，也不触发版本号变更；最终总结必须说明原因。
3. 如果本轮改动影响架构、目录说明、验证命令、Agent 工具协议、benchmark / trace / validation / runner 口径，必须同步检查 `README.md` 与 `docs/reproduce/tablecodeagent_architecture.md`。
4. 只在 `README.md` 已经维护相关清单、且本轮改动导致说明失实时，才同步 README；否则不要为了显得完整改 README。
5. 禁止修改或提交 `configs/api/local/`、`.env`、真实 API key、`__pycache__`、`.pyc` 或无关生成文件。
6. 如果用户明确要求生成报告，必须按 `.codex/AGENTS.md` 的报告规则生成，并使用可跳转 Markdown 相对路径交叉引用。

【本次要完成的 TODO，必须全部落地】

A. {{事项 A 标题}}

1. 背景：{{背景 A}}
2. 定位要求：{{定位 A}}
3. 修改要求：{{修改 A}}
4. 验收标准：{{验收 A}}

B. {{事项 B 标题，可删除}}

1. 背景：{{背景 B}}
2. 定位要求：{{定位 B}}
3. 修改要求：{{修改 B}}
4. 验收标准：{{验收 B}}

C. {{事项 C 标题，可删除}}

1. 背景：{{背景 C}}
2. 修改要求：{{修改 C}}
3. 验收标准：{{验收 C}}

【实现约束】

1. 默认最小必要改动，但不是盲目保守；如果局部补丁无法闭环，先说明根因、必要性、影响范围、回归方案和可回滚边界，再做必要调整。
2. 代码生成或文档修改必须基于真实仓库结构、真实调用链和真实测试入口。
3. 新增能力优先放在 `src/tablecodeagent/` 领域模块，再通过轻量 adapter 接入 `mini_claude` Agent Runtime；不要把核心计算、评测、trace、数据清洗、建模前处理或 benchmark 逻辑堆进 `src/mini_claude/tools.py`。
4. 单个模块只承载一个清晰职责；大函数必须拆成可命名、可单测、可复用的小函数。
5. 不复制粘贴大段近似逻辑；出现重复分支时，优先抽取明确 helper 或数据驱动结构。
6. 不新增没有依据的保护逻辑，包括固定超时、长度截断、条数上限、重试上限、静默降级、隐藏兜底、中断条件、容量边界、输入输出限制或异常捕获默认值。
7. 如确实需要新增保护逻辑，必须说明依据、触发时可见行为、误伤风险、验证方式和后续调整方式。
8. 错误处理必须显式暴露问题、便于排查；禁止 broad try/catch 后吞异常，禁止失败后伪造成功或返回空结果冒充正常。
9. Agent 输出 JSON、`answer.json`、tool input / output schema 和 task `output_contract` 必须机器可校验，不能只靠自然语言提示或顶层 key 列表；复杂场景优先使用 JSON Schema、Pydantic model 或同等方案。
10. 真实 LLM Agent benchmark 必须采用 no-helper 口径。禁止把 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`、完整 workflow import 路径或 `build_*_report()` 这类解题入口公开给模型；如果需要验证项目内 helper，只能作为 unit / integration / smoke / regression 测试，不能命名为 benchmark，不能计入模型能力结论。
11. benchmark 或 LLM 验证必须区分非 API 模式和真实 LLM 模式；非 API 通过不能写成真实 LLM Agent 行为已验证。
12. 不要把未实现能力、未验证能力、`SKIP` 场景或推测写成已完成、已通过或事实。
13. 本轮专项实现约束：{{本轮专项实现约束}}

【测试与验证要求，必须执行】

根据本轮改动选择最小但完整的验证闭环，不接受“只看代码”。只列实际运行的命令，不要把历史测试结果写成本轮验证结果。

1. 通用代码与文档校验：{{通用校验命令}}
2. 表格工具改动至少运行：

   ```bash
   bash scripts/run_table_tools_smoke.sh
   ```

3. Agent 工具注册、tool schema、`execute_tool()` 分发改动至少运行：

   ```bash
   bash scripts/run_agent_table_tools_smoke.sh
   ```

4. benchmark、runner、trace、validation 改动至少运行：

   ```bash
   bash scripts/run_benchmark_smoke.sh
   ```

5. 真实 LLM 端到端验证只在 API env 可用且任务需要时运行；如未指定 env，默认使用 `configs/api/local/deepseek.env`，但不得打印 key/token/secret：

   ```bash
   bash scripts/run_real_api_code_agent_benchmark.sh configs/api/local/deepseek.env {{任务目录}}
   ```

6. 如果本轮是 skill / 指令文件维护，默认不运行 TableCodeAgent smoke tests；验证重点是 UTF-8 可读、frontmatter 关键字段、YAML 关键字段、`references/` 引用路径、脚本语法和校验脚本结果。至少运行或等价核对：

   ```powershell
   python -m py_compile .agents/skills/tablecodeagent-dev-prompt/scripts/validate_tablecodeagent_dev_prompt.py
   python -X utf8 .agents/skills/tablecodeagent-dev-prompt/scripts/validate_tablecodeagent_dev_prompt.py .agents/skills/tablecodeagent-dev-prompt/references/prompt-template.md
   ```

7. 如果当前环境无法运行某项测试，必须说明失败命令、失败原因、已完成的替代验证，以及该结论是否仍未验证。
8. 验证输出必须给出证据路径，例如具体文件、命令输出摘要、`benchmarks/results/<mode>/<run_id>/results.jsonl`、trace 文件或生成报告路径。

【交付物要求】

最终输出按以下顺序组织：

1. 文件改动清单：逐文件说明关键改动点。
2. 根因或设计依据：说明来自哪些代码、文档、测试、日志或参考材料。
3. 实现方案：说明为什么是最小必要改动，以及为什么不会破坏现有调用链。
4. 验证命令：列出实际运行的命令。
5. 验证结果：说明通过、失败或 `SKIP`，不要把未运行写成通过。
6. 证据路径：列出结果文件、trace、日志、关键改动文件或命令输出摘要。
7. 版本、文档与报告策略：说明是否触发版本号、README、架构文档或修复报告；不触发时说明原因。
8. 风险与未验证项：明确剩余风险、跳过项、`SKIP` 或当前环境限制。

【注意】

1. 不要为了完成任务而扩大范围做无关重构。
2. 不要把 baseline 教程文档 `docs/baseline/` 当成 TableCodeAgent 最新架构记录来改。
3. 不要把历史 benchmark 结果写成当前复测结果；当前复测必须有本轮命令或证据。
4. 遇到 API、网络、权限、模型行为不可控等限制时如实说明，不要假装已通过。
5. 最终 prompt 必须由单个 Markdown 文本块承载；如果内部包含三反引号，外层使用四反引号或更长围栏。
````

## 计划模式 prompt 路由

Plan Mode prompt 不在本底稿继续维护。用户要求只读探索、先提炼关键决策点、先给用户选择空间或明确使用 Plan Mode 时，调用 `$tablecodeagent-plan-mode-prompt`；其项目本地源码位置是 `.agents/skills/tablecodeagent-plan-mode-prompt/`。

## 评审 prompt 路由

代码评审 prompt 不在本底稿继续维护。用户要求 code review、findings first、审查报告或默认不修复的评审任务时，调用 `$tablecodeagent-code-review-prompt`；其项目本地源码位置是 `.agents/skills/tablecodeagent-code-review-prompt/`。

## skill / 指令文件维护 prompt 片段

当任务是维护 `.agents/skills`、`.codex/AGENTS.md` 或 prompt 生成 skill 时，把通用 prompt 中的本轮范围和测试要求收敛为：

```text
本轮是维护 Codex/Agent 指令资产，不是修改 TableCodeAgent 核心运行能力。

验证重点：

1. 文件存在性。
2. UTF-8 可读性。
3. `SKILL.md` frontmatter 至少包含 `name:` 与 `description:`。
4. `agents/openai.yaml` 关键字段存在：`interface:`、`display_name:`、`short_description:`、`default_prompt:`。
5. `references/` 引用路径真实存在。
6. Python 脚本语法检查。
7. prompt 质量校验脚本结果。
8. 无旧项目私有路径、版本号、测试命令、报告规则或发布约束残留。

默认不运行 TableCodeAgent smoke、benchmark 或真实 API 测试；最终总结必须说明原因是“仅维护 skill/指令资产，不改核心运行能力”。

项目本地 `.agents/skills/<skill-name>` 不等于当前会话或其他会话一定自动发现；本轮不做全局 skill 同步，除非用户另行明确要求。
```

## 校验脚本使用提醒

生成或改写 prompt 后，保存为临时草稿或放入可检查文件，并运行：

```powershell
python -X utf8 .agents/skills/tablecodeagent-dev-prompt/scripts/validate_tablecodeagent_dev_prompt.py <prompt_path>
```

脚本失败时，按缺失项补齐 prompt 并复跑，直到通过或明确剩余不可验证边界。该脚本只检查关键结构和质量约束是否保留，不负责判断具体任务内容是否完全覆盖用户意图。
