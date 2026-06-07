# TableCodeAgent 任务 Prompt 底稿

本文件是 skill 内部底稿。生成最终回答时，把不相关段落删除，把占位符替换成用户本轮任务信息；不要把本文件当“参数化模板”原样输出给用户。

## 通用执行 Prompt

```text
你要在当前仓库 `/root/workspace/TableCodeAgent` 完成一次“{{任务标题}}”任务。严格执行以下要求，不得跳过。

当前模式：{{执行模式说明}}

【硬性前置要求（必须先做）】

1. 不做任何修改前，必须先阅读并在进度里明确已读：

   - `.codex/AGENTS.md`
   - `README.md`
   - `docs/reproduce/tablecodeagent_architecture.md`
   - `docs/reproduce/why_table_code_agent.md`
   - `docs/reproduce/` 下与本轮任务直接相关的 fix report / 复现记录 / 实验记录
   - 本轮涉及的真实调用链代码：{{相关入口、模块、脚本、benchmark task}}

2. 全程使用简体中文。代码、命令、报错原文、文件路径、API 字段名、模型名、库名除外。
3. 先理解入口、调用链、工具注册、数据路径和验证方式，再做修改或给计划；不要依赖过期文件清单替代理解代码。
4. 严格最小必要改动，禁止无关重构，禁止回滚用户已有改动。
5. 不把未验证写成已验证，不把 `SKIP` 写成通过，不把推测写成事实；无法确认时明确写“待确认”或“未验证”。

【项目定位与边界】

1. TableCodeAgent 是面向复杂表格任务的轻量级 Coding Agent 项目，目标是把表格数据处理、算法建模前置分析、业务决策推理、表格 benchmark 等任务组织成可复现、可验证、可审计、可迁移的程序化工作流。
2. 不要把项目缩窄成普通数据分析 Agent，也不要包装成 SFT、RL、RAG、Memory 增强或 SOTA 项目。
3. 当前工程主线是复用 `mini_claude` baseline，逐步加入表格工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。
4. 新增能力优先放在 `src/tablecodeagent/` 领域模块，再通过轻量 adapter 接入 `mini_claude` Agent Runtime。
5. 不要把核心计算、评测、trace、数据清洗、建模前处理或 benchmark 逻辑堆进 `src/mini_claude/tools.py`。

【版本、文档与报告策略】

1. 用户没有明确要求升版时，沿用当前仓库版本，不主动 bump 版本。
2. 只有功能修复、行为变更、Agent 工具注册或工具行为调整、benchmark/trace/validation/runner 变化、工具协议或评测口径变化，才需要按 `.codex/AGENTS.md` 评估版本号和修复报告。
3. 纯文档修改、README 更新、说明文字修正、skill/指令文件调整、格式整理、注释修正，不触发修复报告，也不触发版本号变更；最终总结必须说明原因。
4. 如果本轮改动影响架构、目录说明、验证命令或 benchmark/trace 口径，必须同步检查 `README.md` 与 `docs/reproduce/tablecodeagent_architecture.md`。
5. 不提交真实 API key、`configs/api/local/`、`.env`、`__pycache__`、`.pyc` 或无关生成文件。

【本次要完成的 TODO，必须全部落地】

A. {{TODO_A_标题}}

问题现象 / 任务背景：

1. {{背景_A_1}}
2. {{背景_A_2}}
3. {{背景_A_3}}

定位要求：

1. {{定位_A_1}}
2. {{定位_A_2}}
3. {{定位_A_3}}

实现或修复要求：

1. {{要求_A_1}}
2. {{要求_A_2}}
3. {{要求_A_3}}

B. {{TODO_B_标题，可删除}}

目标：

1. {{目标_B_1}}
2. {{目标_B_2}}

约束：

1. {{约束_B_1}}
2. {{约束_B_2}}

【实现约束】

1. 单个模块只承载一个清晰职责；大函数必须拆成可命名、可单测、可复用的小函数。
2. 不复制粘贴大段近似逻辑；出现重复分支时，优先抽取明确 helper 或数据驱动结构。
3. 错误处理必须可观测，不吞异常伪装成功；校验失败不能包装成“无数据”或“已通过”。
4. 不新增无依据的固定超时、轮次上限、重试上限、prompt/工具输出/CSV/trace 截断。
5. 如果确实需要新增限制，必须说明依据、触发时用户或日志能看到什么、是否误伤合法长表格/长输出/长 trace、对 benchmark 指标和失败类型统计有什么影响。
6. Agent 工具相关改动不能只改 schema 不接执行路径，也不能只接执行路径但模型不可见。
7. benchmark 或 LLM 验证必须区分非 API 模式和真实 LLM 模式；非 API 通过不能写成真实 LLM Agent 行为已验证。
8. {{本轮专项实现约束}}

【测试与验证要求，必须执行】

根据本轮改动选择最小但完整的验证闭环，不接受“只看代码”：

1. 表格工具改动至少运行：

   ```bash
   cd /root/workspace/TableCodeAgent
   bash scripts/run_table_tools_smoke.sh
   ```

2. Agent 工具注册、tool schema、`execute_tool()` 分发改动至少运行：

   ```bash
   cd /root/workspace/TableCodeAgent
   bash scripts/run_agent_table_tools_smoke.sh
   ```

3. benchmark、runner、trace、validation 改动至少运行：

   ```bash
   cd /root/workspace/TableCodeAgent
   bash scripts/run_benchmark_smoke.sh
   ```

4. 真实 LLM 端到端验证只在 API env 可用且任务需要时运行：

   ```bash
   cd /root/workspace/TableCodeAgent
   bash scripts/run_real_api_code_agent_benchmark.sh configs/api/local/deepseek.env benchmarks/tasks/growth_campaign_audit_001
   ```

5. 如果本轮涉及 Excel、多表、multi-header、merged cell 或新 benchmark task，必须覆盖对应任务目录，并在结果中说明验证的是 `direct`、`agent_tool_dispatch` 还是 `optional_llm_agent`。
6. 如果当前环境无法运行某项测试，必须说明失败命令、失败原因、已完成的替代验证，以及该结论是否仍未验证。
7. 验证输出必须给出证据路径，例如 `benchmarks/results/<mode>/<run_id>/results.jsonl`、`benchmarks/results/<mode>/<run_id>/traces/...json` 或具体命令输出摘要。

【交付物要求】

最终输出按以下顺序：

1. 文件改动清单：逐文件说明关键改动点。
2. 根因或设计依据：说明来自哪些代码、文档、测试或日志证据。
3. 实现方案：说明为什么是最小必要改动，以及为什么不会破坏现有调用链。
4. 验证命令：列出实际运行的命令。
5. 证据路径：列出结果文件、trace、日志或关键输出。
6. 版本与文档同步：说明是否触发版本号、修复报告、README 或架构文档更新；不触发时说明原因。
7. 风险与未验证项：明确剩余风险、跳过项、`SKIP` 或当前环境限制。

【注意】

- 不要为了完成任务而扩大范围做无关重构。
- 不要把 baseline 教程文档 `docs/baseline/` 当成 TableCodeAgent 最新架构记录来改。
- 不要把历史 benchmark 结果写成当前复测结果；当前复测必须有本轮命令或证据。
- 遇到 API、网络、权限、模型行为不可控等限制时如实说明，不要假装已通过。
```

## Plan Mode Prompt 收口

把通用执行 prompt 中的模式说明替换为：

```text
当前是 Plan Mode：只允许做非修改性探索、阅读、搜索、静态分析、运行只读/验证类命令。不要编辑文件，不要 apply patch，不要新增报告，不要删除文件，不要修改版本号。
```

把测试段替换为：

```text
【计划必须覆盖的验证设计】

最终计划必须说明后续执行时应运行哪些命令、预期证据路径是什么、哪些验证依赖 API/env/网络、哪些验证可以用非 API smoke test 完成。不要在 Plan Mode 中伪装已经完成验证。
```

最终输出要求替换为：

```text
最终必须只输出一个 `<proposed_plan>`，不要直接实现。计划必须覆盖：当前状态、推进顺序、关键设计、文件级改动计划、测试与验证、版本与报告策略、风险与边界，以及“本轮未修改代码”的明确声明。
```

## 评审 Prompt 收口

把模式说明替换为：

```text
当前是代码评审模式：以发现 bug、回归风险、行为不一致、缺失测试和文档误导为主。默认不修改文件；如果需要给建议，优先给最小可行改法和验证要求。
```

最终输出要求替换为：

```text
最终输出必须 findings first，按严重级别排序。每条 finding 必须包含文件路径、证据、影响、最小修复建议和验证建议。如果没有发现明确问题，直接写“未发现明确问题”，并列出剩余风险或测试缺口。
```

## skill / 指令文件维护 Prompt 片段

当任务是维护 `.codex/skills`、`.agents/skills`、`AGENTS.md` 或 prompt 生成 skill 时，加入：

```text
【skill / 指令文件专项要求】

1. 本轮是维护 Codex/Agent 指令资产，不是修改 TableCodeAgent 核心运行能力。
2. 必须检查 skill 的存放目录、frontmatter、references 文件和可调用性边界；只有当前仓库真实存在 `agents/openai.yaml` 时才要求检查该文件。
3. 如果目标是让 `$skill-name` 在新对话可调用，优先同步到当前 Codex 实际发现的全局 skill 目录 `/root/.codex/skills/<skill-name>`；项目内副本可保留，但不能把它误判为当前会话已加载。
4. 不要求运行 TableCodeAgent smoke tests；验证重点是文件存在、YAML/frontmatter 可解析、路径同步完成。
5. 最终说明本轮是 skill/指令文件调整，按 `.codex/AGENTS.md` 不触发项目修复报告或版本号变更。
```

## 常见专项验证映射

- 只改 skill、AGENTS、prompt：检查文件存在、frontmatter/YAML 可解析、全局 skill 目录已同步；不跑 TableCodeAgent smoke。
- 只改 README 或架构文档：检查文档中版本、目录、验证命令与当前代码一致；不默认升版。
- 改 `src/tablecodeagent/table_tools/`：跑 `scripts/run_table_tools_smoke.sh`。
- 改 `src/tablecodeagent/agent_tools.py` 或 `src/mini_claude/tools.py`：跑 `scripts/run_agent_table_tools_smoke.sh`，必要时再跑 benchmark smoke。
- 改 `benchmarks/`、runner、trace、validation：跑 `scripts/run_benchmark_smoke.sh`，并给出 `benchmarks/results/<mode>/<run_id>/results.jsonl` 与 trace 路径。
- 改真实 LLM 端到端链路：在 env 可用时跑 `scripts/run_real_api_code_agent_benchmark.sh configs/api/local/deepseek.env benchmarks/tasks/growth_campaign_audit_001`，或等价的 `python -m tablecodeagent.benchmark.benchmark_runner --env ... --task-dir ...`；真实 benchmark 必须使用 no-helper 口径；env 不可用时必须写 `SKIP`，不能写通过。
