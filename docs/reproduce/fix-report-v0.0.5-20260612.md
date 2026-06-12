# v0.0.5 修复报告：skill 根目录迁移、CLAUDE.md、产品态主 Loop 与受控真实 API 复测（2026-06-12）

## 版本口径

本轮未升级版本，继续沿用 `v0.0.5`。依据：`README.md` badge 和 `src/pyproject.toml` 当前版本仍为 `0.0.5`。

## 前置阅读

已先阅读并据此修改：`.codex/AGENTS.md`、`README.md`、`docs/reproduce/tablecodeagent_architecture.md`、`docs/reproduce/why_table_code_agent.md`、`docs/reproduce/workflow-helper-no-helper-benchmark-design-20260608.md`、`docs/reproduce/fix-report-v0.0.5-20260608.md`、`docs/reproduce/fix-report-v0.0.4-20260608.md`、`src/mini_claude/prompt.py`、`src/mini_claude/skills.py`、`src/mini_claude/tools.py`、`src/mini_claude/agent.py`、`src/tablecodeagent/benchmark/benchmark_runner.py`、`src/tablecodeagent/benchmark/real_api_code_agent.py`、原 `src/tablecodeagent/workflows/*`、相关 unit / integration / simulated Agent tests。

## 外部调研结论

一手来源见 [product-agent-loop-design-20260612.md](product-agent-loop-design-20260612.md)。结论转成以下工程约束：

- 产品态主 Loop 不能等于 deterministic oracle；oracle 只能作为 fixture / regression / expected behavior 资产。
- workflow、agent、orchestrator-worker 要分层；本轮先落单 agent vertical slice，后续多表并行和 worker 拆分需要新的测试闭环。
- context engineering 不能只堆 prompt；必须压缩并保留字段、主键、join、缺失、重复、异常、时间窗和输出契约证据。
- tool schema 和返回结构必须服务 Agent repair loop；本轮 `run_table_product_workflow` 第一次返回 context/brief，后续返回 sandbox/schema/pytest/validator 反馈。
- Coding Agent 需要 agent-computer interface；本轮把表格画像、受控 workspace、sandbox、pytest/validator、trace 和 repair feedback 串成可观测接口。

## 关键改动

- `.tca/skills/` 已迁移到 `.claude/skills/`，并删除 `.tca/skills/`。不保留双轨兼容目录。
- `src/mini_claude/skills.py` 新增 `agents/agent.yaml` 元数据读取和 system prompt 注入；继续只发现 `~/.claude/skills` 与项目 `.claude/skills`。
- 新增根目录 `CLAUDE.md`，新增 `.claude/rules/workflow-boundaries.md`，并修正 `prompt.py`：向上查找 `CLAUDE.md` 的同时加载沿途 `.claude/rules/*.md`。
- 新增 `src/tablecodeagent/workflow/`，提供产品态主 Agent Loop vertical slice，并通过 `src/tablecodeagent/agent_tools.py` 的 `run_table_product_workflow` tool 接入 MiniClaude tool schema。该目录原实现名为 `product_agent`，本轮已按“product workflow”定位改为更直接的 `workflow`，避免把它误解成新的独立 Agent runtime。
- 原 `src/tablecodeagent/workflows/` 中 deterministic helper 已迁移到 `tests/test_workflows/`，只作为 helper-assisted oracle / regression 资产。
- 新增 `tests/__init__.py`，让 sandbox 子进程稳定 import `tests.test_workflows`，避免被环境中同名 `tests` 包抢占。
- `real_api_code_agent` 新增 no-helper denylist：禁止旧 `tablecodeagent.workflows`、新 `tests.test_workflows`、产品 workflow 路径 `tablecodeagent.workflow`、旧兼容禁止项 `tablecodeagent.product_agent`、`build_*_report()`、`run_*()`，并增加 AST 动态 import 检查和 `run_table_product_workflow` 工具禁用。
- README、架构文档、`.codex/AGENTS.md` 和项目 skill 文案已同步到 `.claude/skills/`、`CLAUDE.md`、三层 workflow 和产品态主 Loop 边界。

## product workflow 实现与 Agent Loop 接入

product workflow 当前实现目录是 `src/tablecodeagent/workflow/`：

- `state.py`：定义 `ProductWorkflowState`，显式记录 `task_id`、`task_dir`、`workspace_path`、`tables`、`context_package`、`tool_strategy`、`code_generation_brief`、`attempts`、`repair_history`、`schema_check`、`validation`、`trace` 和 `analysis_memory`。
- `loop.py`：实现 `run_product_workflow()`。首次调用不传候选代码时，只做任务解析、表格发现、字段画像、上下文压缩、工具策略和代码生成 brief；传入 `candidate_code` 或 `candidate_code_versions` 后，会复制 task workspace、写入 `solve.py`、运行 sandbox、执行 schema / pytest / validator，并将失败转成 repair feedback。
- `__init__.py`：暴露 `run_product_workflow()`，作为产品 workflow 的包级入口。

它接入 MiniClaude Agent Loop 的真实链路是：

```text
MiniClaude Agent
  -> src/mini_claude/tools.py 合并 TABLE_TOOL_DEFINITIONS
  -> src/tablecodeagent/agent_tools.py 注册 run_table_product_workflow tool schema
  -> mini_claude.tools.execute_tool()
  -> tablecodeagent.agent_tools.execute_table_tool()
  -> _run_table_product_workflow()
  -> tablecodeagent.workflow.run_product_workflow()
```

因此它不是“只放在 `src/` 但没有主链路接入”的死模块。Agent 能通过工具调用先拿到上下文和 brief，再把候选代码交回该 workflow 执行验证和 repair。

## 真实 API benchmark 是否调用 product workflow

本轮唯一一次真实 API benchmark 没有调用 `run_table_product_workflow`，这是刻意设计，不是漏测。原因如下：

- 本次真实 API 测的是 `no-helper` 能力，意思是：只给模型公开题目、数据表和输出格式，让它自己写解题代码，看看它在“不看项目内部参考答案、不走项目内主流程辅助”的情况下能做到什么程度。
- product workflow 更像正式产品里的“任务办理流程”：它会先帮模型整理表格信息，再执行模型写出的代码，还会把校验错误整理成下一轮修改建议。这个流程对真实用户任务有价值，但如果放进 `no-helper` 考试里，就等于给考生配了一个会整理题目、检查答案并提示如何修改的场外助手，测出来的就不再是模型独立解题能力。
- 所以本轮真实 API benchmark 主动不开放 product workflow，也不允许模型绕路调用项目里的参考实现或测试用标准答案。这样可以保证 `no-helper` 结果只反映模型自己根据公开材料写代码的能力。
- trace 中 `llm_tool_call_observed=true`、`tool_call_count=15` 只表示模型调用了允许的普通工具，例如读文件、看表格、运行命令；不表示它调用了 product workflow。本次真实 API 中 product workflow 是不可用的。

## product workflow 是否需要补充测试

需要，但测试类型要分清：

- 已补充本地代码测试：`tests/test_unit/test_product_workflow_loop.py` 覆盖上下文准备、代码生成 brief、sandbox 执行、validator 通过、坏 JSON repair feedback、二次候选修复通过、连续失败后 `repair_needed`、空表上下文错误可观测。
- 已补充 no-helper 防线测试：`tests/test_unit/test_real_api_code_agent_contract.py` 覆盖 `tablecodeagent.workflow`、旧 `tablecodeagent.product_agent`、`tests.test_workflows`、动态 import 和 `run_table_product_workflow` 工具禁用。
- 现有 no-helper 真实 API benchmark 仍然不应该直接使用 product workflow。no-helper 像“闭卷考试”，要看模型只凭公开题目和数据能不能自己写出代码；product workflow 像“正式办事流程”，会帮模型整理题目、执行代码、反馈错误和引导修改。两者都重要，但不能放在同一张成绩单里。
- 后续如果要测 product workflow 的真实 API 链路，应新增一个独立入口或任务组，例如 `product_workflow_agent`。这个新入口要在名字和报告里写清楚：它测的是“模型 + 产品流程协同完成任务”的能力，不是 no-helper 独立解题能力。
- product workflow 真实 API 测试建议记录更接近产品链路的证据：是否真的调用了 product workflow、模型给了几版候选代码、每一版失败在哪里、workflow 给了什么修复反馈、最后 schema / pytest / validator 是否通过、trace 和 workspace 在哪里。
- product workflow 测试结果只能归到“产品链路验证”或“workflow-assisted 结果”，不能并入 no-helper pass rate，也不能拿来证明模型在没有帮助的情况下独立完成了任务。

## 本地验证

已运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_unit/test_prompt_project_instructions.py tests/test_unit/test_product_workflow_loop.py tests/test_unit/test_real_api_code_agent_contract.py tests/test_unit/test_finance_operations_skill_contract.py -q
```

结果：`20 passed in 2.84s`。

已运行完整本地闭环：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration -q
```

结果：`40 passed in 15.34s`。

覆盖点包括：prompt / `CLAUDE.md` / rules / skill metadata 注入、product workflow 上下文准备、sandbox 执行、schema/validator、repair loop 修复与未修复失败、空表上下文错误、no-helper 动态 import 防线、产品 workflow 工具禁用、simulated Agent 输出的枚举大小写、缺失字段、字段类型、嵌套 JSON、重复计数口径、NaN/NaT 缺失值归一化、账龄边界、付款匹配、adjustment/ECL 口径、sandbox 固定解回归和 pytest 业务断言。

## 唯一一次真实 API 复测

选择任务：`benchmarks/tasks/finance_operations_001`。原因：它是当前最接近真实多表业务场景的任务，能验证本轮 product/oracle 迁移后 no-helper runner 仍能隐藏 helper、调用真实模型、观察工具调用、生成 `solve.py`、执行 sandbox、运行 Pydantic schema 和 pytest。该测试不把产品主 Loop 当 helper 暴露。

命令：

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner --env configs/api/local/deepseek.env --task-dir benchmarks/tasks/finance_operations_001 --task-group v0.0.5-product-loop-boundary-20260612
```

结果：真实 API 已调用，但未通过。没有追加第二次 API 复测。

- `result_dir`：[benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612)
- `results.jsonl`：[results.jsonl](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/results.jsonl)
- `trace_path`：[finance_operations_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/traces/finance_operations_001.real_api_code_agent.json)
- `workspace_path`：[finance_operations_001.real_api_code_agent](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent)
- `solve.py`：[solve.py](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/solve.py)
- `answer.json`：[answer.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/answer.json)

关键字段：

- `api_called=true`
- `llm_tool_call_observed=true`
- `tool_call_count=15`
- `tool_error_count=0`
- `schema_check.passed=true`
- `run_python_exit_code=0`
- `pytest_exit_code=1`
- `validation.passed=null`
- `failure_type=pytest_failed`
- `generated_code_saved=true`
- `answer_file_saved=true`

精确失败归因：模型生成代码能运行，`answer.json` 也满足 Pydantic schema，但业务 pytest 失败。缺失的 required exception type 是 `missing_po`，对应 `tests/test_solution.py::test_finance_operations_answer_contract_and_business_findings` 断言失败。该问题属于模型输出业务口径遗漏，不是本轮目录迁移或产品主 Loop 接线失败。

## 风险与未验证项

- product workflow 已接入 MiniClaude tool schema，但真实交互式产品任务只在本地 unit test 中验证；本轮真实 API benchmark 仍按 no-helper 口径禁用产品工具。
- `run_table_product_workflow` 当前是单 agent vertical slice；已接入 MiniClaude tool schema，但未实现多 worker、并行 profiling、长期 cross-thread memory 或生产级容器 sandbox。
- product workflow 尚未做单独真实 API 产品链路复测；本轮真实 API 是 no-helper benchmark，按设计禁用了 `run_table_product_workflow`。
- `analysis_memory` 当前明确为 report-scoped，不声明跨线程或长期项目 memory。
- 真实 API 本轮只跑一次且失败，不能写成 finance no-helper 通过。
