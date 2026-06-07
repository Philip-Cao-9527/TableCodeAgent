﻿# v0.0.3 代码评审与诊断报告

## 评审范围与证据

本轮为代码评审、诊断报告落盘和真实 API 验证；未修改业务代码、测试代码、`.gitignore` 或配置文件。唯一新增文件是本文档。

已读文件：

- [`.codex/AGENTS.md`](../.codex/AGENTS.md)
- [`README.md`](../README.md)
- [`docs/reproduce/tablecodeagent_architecture.md`](reproduce/tablecodeagent_architecture.md)
- [`docs/reproduce/why_table_code_agent.md`](reproduce/why_table_code_agent.md)
- [`docs/reproduce/fix-report-v0.0.3-20260607.md`](reproduce/fix-report-v0.0.3-20260607.md)
- [`docs/reproduce/fix-report-v0.0.2-benchmark-restructure-20260606.md`](reproduce/fix-report-v0.0.2-benchmark-restructure-20260606.md)
- [`src/tablecodeagent/benchmark/benchmark_runner.py`](../src/tablecodeagent/benchmark/benchmark_runner.py)
- [`src/tablecodeagent/benchmark/real_api_code_agent.py`](../src/tablecodeagent/benchmark/real_api_code_agent.py)
- [`src/tablecodeagent/workflows/growth_campaign_audit.py`](../src/tablecodeagent/workflows/growth_campaign_audit.py)
- [`src/tablecodeagent/workflows/credit_risk_scoring.py`](../src/tablecodeagent/workflows/credit_risk_scoring.py)
- [`src/tablecodeagent/agent_tools.py`](../src/tablecodeagent/agent_tools.py)
- [`src/tablecodeagent/table_tools/quality.py`](../src/tablecodeagent/table_tools/quality.py)
- [`src/mini_claude/tools.py`](../src/mini_claude/tools.py)
- [`src/mini_claude/subagent.py`](../src/mini_claude/subagent.py)
- [`benchmarks/tasks/growth_campaign_audit_001/task.json`](../benchmarks/tasks/growth_campaign_audit_001/task.json)
- [`benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py`](../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py)
- [`benchmarks/tasks/credit_risk_scoring_001/task.json`](../benchmarks/tasks/credit_risk_scoring_001/task.json)
- [`benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py`](../benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py)
- [`.gitignore`](../.gitignore)

已运行只读或验证命令：

```powershell
git status --short
git log --oneline --decorate -n 20
git diff --stat
git diff
rg -n ".env|configs/api/local|provider_chatanywhere.env|--env|api_env_missing|SKIP|skipped" -S .
rg -n "benchmarks?/results|benchmark/results|.gitignore|无关生成文件|提交|忽略" -S .codex README.md docs scripts src tests benchmarks/tasks .gitignore
```

真实 API benchmark 前已确认 `configs/api/local/provider_chatanywhere.env` 存在，且只核对变量名存在性，未输出任何 key/token 值。必要变量名检查结果：`MINI_CLAUDE_MODEL=true`、`MINI_CLAUDE_API_BASE=true`、`OPENAI_API_KEY=true`。

已运行项目代码测试：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration
```

结果：`10 passed in 3.13s`。这只证明项目代码测试通过，不证明真实 LLM Agent benchmark 通过。

真实 API benchmark 首次直接运行失败：

```powershell
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/provider_chatanywhere.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-dir benchmarks/tasks/credit_risk_scoring_001 `
  --task-group v0.0.3-code-review-20260607
```

失败证据：终端输出 `OpenBLAS error: Memory allocation still failed after 10 retries, giving up.`，未进入 runner 结果写入阶段。

真实 API benchmark 等价 Windows 命令：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/provider_chatanywhere.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-dir benchmarks/tasks/credit_risk_scoring_001 `
  --task-group v0.0.3-code-review-20260607-thread1
```

结果目录：

- [`results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/results.jsonl)
- [`summary.json`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/summary.json)
- [`growth trace`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/traces/growth_campaign_audit_001.real_api_code_agent.json)
- [`credit trace`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/traces/credit_risk_scoring_001.real_api_code_agent.json)
- [`credit solve.py`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/workspaces/credit_risk_scoring_001.real_api_code_agent/solve.py)
- [`credit answer.json`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/workspaces/credit_risk_scoring_001.real_api_code_agent/answer.json)

未运行命令与原因：

- 未直接运行 `scripts/run_real_api_code_agent_benchmark.sh`：当前 shell 是 Windows PowerShell，`.sh` 不是最稳入口；本轮使用 README 与脚本等价的 `python -m tablecodeagent.benchmark.benchmark_runner`。
- 未运行 Linux 复测：当前环境是 Windows，Linux / AutoDL 兼容性仍需另行复测。

v0.0.3 diff 边界：版本边界未完全确认。当前 `git log` 最新提交仍是 `069f833 chore v0.0.2 添加营销增长场景简单benchmark测试结果`，v0.0.3 内容主要处于未提交工作区，包括已修改的 `.gitignore`、`README.md`、`real_api_code_agent.py`、`tracing/logger.py`、`runtime/sandbox.py`、`mini_claude/*`，以及新增的 `credit_risk_scoring_001/`、`credit_risk_scoring.py`、v0.0.3 fix report 和测试文件。因此本文采用 `git status --short`、`git diff --stat`、`git diff`、v0.0.3 报告与当前源码共同作为替代证据。

## 结论摘要

最高风险结论：真实 API benchmark 已能读取指定 env 并实际调用 API，但两个任务本轮均未通过；其中 `growth_campaign_audit_001` 在模型多轮工具调用后发生 `APITimeoutError`，`credit_risk_scoring_001` 生成了 `solve.py` 和 `answer.json`，但生成代码执行失败且 pytest 校验不通过。

高风险结论：`task.json.implementation_hints.allowed_project_helpers` 公开推荐模型直接调用项目 workflow helper，这对 MVP smoke 有帮助，但会弱化“真实 Code Agent 自主完成表格推理”的测评含义；报告和 README 必须明确这是 helper-assisted code generation，不应包装成模型独立完成完整 workflow。

中风险结论：`benchmarks/results/` 当前未被 `.gitignore` 忽略，但 README 写着“禁止提交”，AGENTS 又要求报告保留可跳转证据，存在“证据可追溯”和“生成物不提交”的张力。建议保持大规模结果默认不提交，同时用 `docs/` 记录关键摘要和 curated 小样例。

中风险结论：Windows 运行需要设置 BLAS 线程变量才能绕过 OpenBLAS 内存分配失败；`.sh`、PowerShell heredoc、编码、Python 版本、`.venv`、pytest 插件自动加载都是跨平台风险。Linux 虚拟环境不应上传 GitHub，应通过依赖文件和平台本地 `.venv` 重建。

## Findings

### 1. 高：公开 helper 提示会弱化真实 Agent benchmark 口径

- 严重级别：高
- 文件路径和行号：
  - [`src/tablecodeagent/benchmark/real_api_code_agent.py:315`](../src/tablecodeagent/benchmark/real_api_code_agent.py)
  - [`src/tablecodeagent/benchmark/real_api_code_agent.py:332`](../src/tablecodeagent/benchmark/real_api_code_agent.py)
  - [`benchmarks/tasks/credit_risk_scoring_001/task.json:35`](../benchmarks/tasks/credit_risk_scoring_001/task.json)
  - [`benchmarks/tasks/growth_campaign_audit_001/task.json:29`](../benchmarks/tasks/growth_campaign_audit_001/task.json)
- 证据：runner 把 `implementation_hints` 直接写入 prompt；两个 task 都公开 `allowed_project_helpers` 和 `solve_py_suggestion`，提示模型可调用 `build_*_report()`。
- 影响：这不是数据泄露到 `expected.json`，但会把 benchmark 从“模型自主规划并实现表格 workflow”变成“模型是否会按提示调用已有 helper”。如果报告或 README 不区分，会夸大真实 Agent 能力。
- 最小修复建议：保留 helper-assisted smoke，但新增或标注一个不公开 helper 的 real API task 口径；summary/result 增加 `helper_hint_exposed=true/false` 或在 `task_group` 中标注。
- 验证建议：分别跑 helper-assisted 与 no-helper 两组真实 API，比较 `tool_call_count`、`generated_code_path`、`pytest_exit_code`、`failure_type` 与通过率。

### 2. 高：真实 API 本轮仍未通过，失败不是 env 读取受阻

- 严重级别：高
- 文件路径和行号：
  - [`src/tablecodeagent/benchmark/real_api_code_agent.py:375`](../src/tablecodeagent/benchmark/real_api_code_agent.py)
  - [`src/tablecodeagent/benchmark/real_api_code_agent.py:390`](../src/tablecodeagent/benchmark/real_api_code_agent.py)
  - [`benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/results.jsonl)
- 证据：本轮结果两条均 `api_called=true`、`skipped=false`、`llm_tool_call_observed=true`。`growth_campaign_audit_001` 为 `failure_type=real_api_code_agent_error`、`api_error_type=APITimeoutError`；`credit_risk_scoring_001` 为 `failure_type=code_execution_failed`。
- 影响：env 读取已可达，真实失败集中在 API 超时、模型生成代码质量、输出内部 schema 和执行环境稳定性，不能写成真实 API 通过。
- 最小修复建议：runner 对 API timeout 单独分类为 `api_timeout`；模型生成代码执行失败时在 result 中暴露 `run_python.exit_code` 和 stderr 摘要，避免只看 `code_execution_failed`。
- 验证建议：固定 `OPENBLAS_NUM_THREADS=1` 后至少跑 5 次小样本稳定性观察；正式报告只写成功率分布和失败类型分布，不写统计充分。

### 3. 中：`growth_campaign_audit_001` 的公开 `output_contract` 缺少 pytest 真实依赖的 `unique_keys`

- 严重级别：中
- 文件路径和行号：
  - [`benchmarks/tasks/growth_campaign_audit_001/task.json:42`](../benchmarks/tasks/growth_campaign_audit_001/task.json)
  - [`benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py:27`](../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py)
- 证据：`output_contract.answer_json_required_keys` 要求 `row_counts`、`join_cardinality`、`group_distribution` 等顶层字段，但 pytest 还读取 `answer.get("unique_keys", {}).get("rewards_duplicate_key", {})` 并断言 `duplicate_key_count` 和 `key_columns`。
- 影响：模型可能满足公开顶层 schema，却仍因隐藏的内部字段要求失败；这会把失败归因为模型不稳，但其中一部分是公开契约不完整。
- 最小修复建议：把 `unique_keys` 加入公开 required keys，并在 `schema_description` 中说明 `unique_keys.rewards_duplicate_key.duplicate_key_count/key_columns`。
- 验证建议：补单元测试确认 `output_contract` 覆盖 pytest 读取的顶层字段和关键嵌套字段。

### 4. 中：`credit_risk_scoring_001` 的字段类型契约不够明确，导致真实生成答案内部 schema 不匹配

- 严重级别：中
- 文件路径和行号：
  - [`benchmarks/tasks/credit_risk_scoring_001/task.json:49`](../benchmarks/tasks/credit_risk_scoring_001/task.json)
  - [`benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py:27`](../benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py)
  - [`src/tablecodeagent/workflows/credit_risk_scoring.py:79`](../src/tablecodeagent/workflows/credit_risk_scoring.py)
- 证据：真实 API 生成的 `answer.json` 中 `data_quality.leakage_columns_present` 是对象 `{has_leakage, leakage_columns, note}`，但 pytest 把它当列表校验，导致 `{'post_loan_collection_calls'}.issubset(set(answer["data_quality"]["leakage_columns_present"]))` 失败。
- 影响：顶层 `schema_check.passed=true` 不代表内部结构满足 pytest；当前 schema 自检只能抓顶层字段，不能抓嵌套字段类型。
- 最小修复建议：在 `output_contract.schema_description` 中明确 `data_quality.leakage_columns_present` 必须是字符串列表；或把 task 的嵌套契约结构化到 `output_contract.required_nested_fields`。
- 验证建议：新增 `_schema_check_answer_json()` 的嵌套字段检查用例，至少覆盖 list/dict 类型差异。

### 5. 中：Windows 下真实 benchmark 对 BLAS 线程和本地 Python 环境敏感

- 严重级别：中
- 文件路径和行号：
  - [`src/pyproject.toml:9`](../src/pyproject.toml)
  - [`docs/reproduce/fix-report-v0.0.3-20260607.md:119`](reproduce/fix-report-v0.0.3-20260607.md)
  - [`src/tablecodeagent/runtime/sandbox.py:11`](../src/tablecodeagent/runtime/sandbox.py)
  - [`src/tablecodeagent/runtime/sandbox.py:216`](../src/tablecodeagent/runtime/sandbox.py)
- 证据：第一次 benchmark 直接失败于 `OpenBLAS error: Memory allocation still failed after 10 retries`；设置 `OPENBLAS_NUM_THREADS=1` 等变量后同一命令进入真实 API 调用并写入结果目录。
- 影响：Windows 本地复现不稳定，可能把本地依赖初始化失败误判成 API/env 失败。
- 最小修复建议：在 README 或脚本中为 Windows 提供等价 PowerShell 命令并设置 BLAS 线程变量；不要只提供 `.sh`。
- 验证建议：在 Windows 与 Linux 各跑一次 `pytest tests/test_unit tests/test_integration` 和双任务真实 API smoke，分别记录 Python 版本、依赖版本、线程变量和结果目录。

### 6. 低：`benchmarks/results/` 提交策略与证据链接规则存在张力

- 严重级别：低
- 文件路径和行号：
  - [`README.md:140`](../README.md)
  - [`.codex/AGENTS.md:141`](../.codex/AGENTS.md)
  - [`.codex/AGENTS.md:162`](../.codex/AGENTS.md)
  - [`.gitignore:19`](../.gitignore)
  - [`docs/reproduce/fix-report-v0.0.3-20260607.md:284`](reproduce/fix-report-v0.0.3-20260607.md)
- 证据：README 写 `benchmarks/results/` “禁止提交”；AGENTS 要求 benchmark/fix-report 留文件级链接；当前 `.gitignore` 没有忽略 `benchmarks/results/`，只忽略 `.venv/`、`configs/api/local/` 等。
- 影响：后续 Codex 可能反复自动把结果目录加入 `.gitignore`，或反过来提交大量运行产物。
- 最小修复建议：保持大规模运行产物默认不提交；在 `docs/` 写关键摘要；如需保留结果，新增 curated fixture 或 `benchmarks/results/README.md` 说明可提交范围。
- 验证建议：提交前运行 `git status --short`，人工确认结果目录是否作为 curated evidence 纳入。

## 真实 API benchmark 结果

run_id：

```text
20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1
```

result_dir：

```text
benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1
```

summary：

- `result_count=2`
- `passed_count=0`
- `skipped_count=0`
- `failed_count=2`

### growth_campaign_audit_001

- `results.jsonl`：[`results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/results.jsonl)
- trace：[`growth_campaign_audit_001.real_api_code_agent.json`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/traces/growth_campaign_audit_001.real_api_code_agent.json)
- workspace：[`growth workspace`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/workspaces/growth_campaign_audit_001.real_api_code_agent/task.json)
- generated_code_path：记录为 `.../workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py`，但本轮未实际保存成功
- answer_path：记录为 `.../workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json`，本轮不存在
- `api_called=true`
- `skipped=false`
- `llm_tool_call_observed=true`
- `tool_call_count=11`
- `validation.passed=false`
- `failure_type=real_api_code_agent_error`
- `api_error_type=APITimeoutError`
- `code_generation_source=llm_generated`

结论：真实调用 API 且观察到工具调用，但模型交互阶段 API 超时，未进入可执行 `solve.py` / `answer.json` 校验闭环。

### credit_risk_scoring_001

- `results.jsonl`：[`results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/results.jsonl)
- trace：[`credit_risk_scoring_001.real_api_code_agent.json`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/traces/credit_risk_scoring_001.real_api_code_agent.json)
- workspace：[`credit workspace task.json`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/workspaces/credit_risk_scoring_001.real_api_code_agent/task.json)
- generated_code：[`solve.py`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/workspaces/credit_risk_scoring_001.real_api_code_agent/solve.py)
- answer：[`answer.json`](../benchmarks/results/real_api_code_agent/20260607-045504__model-deepseek-v4-flash__tasks-v0.0.3-code-review-20260607-thread1/workspaces/credit_risk_scoring_001.real_api_code_agent/answer.json)
- `api_called=true`
- `skipped=false`
- `llm_tool_call_observed=true`
- `tool_call_count=11`
- `validation.passed=null`
- `failure_type=code_execution_failed`
- `code_generation_source=llm_generated`
- `schema_check.passed=true`
- `pytest_exit_code=1`
- `pytest_failure_summary`：`leakage_columns_present` 被生成成对象，pytest 期望可作为列表包含 `post_loan_collection_calls`

结论：真实 API 生成了代码和答案，顶层 schema 通过，但内部字段结构不满足 pytest，且生成代码执行失败。不能写成通过。

## 专项诊断一：env 文件读取与真实 API 未运行

本轮已确认：只要 prompt 明确允许读取 `configs/api/local/provider_chatanywhere.env`，当前 Codex 会话可以读取该 env 文件用于 benchmark，并能运行真实 API。env 读取没有被 `.codex/AGENTS.md` 直接禁止；AGENTS 的核心限制是不要提交真实 API key、`configs/api/local/`、`.env`。

runner 行为：

- [`benchmark_runner.py`](../src/tablecodeagent/benchmark/benchmark_runner.py) 默认 env 是 `configs/api/local/provider_chatanywhere.env`。
- env 文件不存在时，[`real_api_code_agent.py:375`](../src/tablecodeagent/benchmark/real_api_code_agent.py) 写 `failure_type=api_env_missing`。
- 变量不完整时，[`real_api_code_agent.py:390`](../src/tablecodeagent/benchmark/real_api_code_agent.py) 写 `failure_type=api_config_missing`。
- 本轮 env 存在且包含必要变量名；真实结果为 `api_called=true`，所以这次不是 env 读取受阻。

三类原因区分：

- 项目指令原因：历史报告提到“当轮请求没有明确要求读取具体 env 文件”，这是安全边界和 prompt 明确性问题。后续 prompt 应明确指定允许读取哪个 env 文件，只允许用于加载变量，不输出密钥值。
- Codex 安全策略原因：本轮无证据显示 Codex 系统层阻止读取指定 env；相反，已完成变量名核对和真实 API 调用。
- Windows / Shell / 依赖原因：本轮首次运行因 OpenBLAS 内存分配失败中断；设置 `OPENBLAS_NUM_THREADS=1` 后进入真实 API benchmark。该问题属于本地运行环境，不是 env 权限。

最小解决方案：

- 后续真实 API prompt 明确写：允许读取 `configs/api/local/provider_chatanywhere.env`，不得打印 key/token/secret。
- runner 对 env 缺失继续写 `api_env_missing`，对变量缺失写 `api_config_missing`。
- Windows 真实 benchmark 命令显式设置 `PYTHONPATH=src` 和 BLAS 线程变量。
- 建议 runner 把 API timeout 单独分类为 `api_timeout`。

## 专项诊断二：benchmark results 与 .gitignore

当前 `.gitignore` 没有 `benchmark/results`，也没有 `benchmarks/results`。注意单复数：当前代码和文档使用的是 `benchmarks/results/`。

为什么 Codex 容易自动加入 `.gitignore`：

- README 写 `benchmarks/results/` 是真实 API 输出结果且“禁止提交”。
- `.codex/AGENTS.md:162` 写不要提交“无关生成文件”。
- benchmark 结果目录包含 trace、workspace、模型生成代码、answer、expected 副本和可能大量重复运行产物，符合一般“生成产物默认不提交”的工程习惯。
- 历史文档 [`fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md`](reproduce/fix-report-v0.0.2-skill-authoring-agents-docs-20260606.md) 曾明确解释忽略 `benchmarks/results/` 的原因。

是否应纳入 Git：

- 大量重复运行产物、workspaces、LLM 生成代码、trace 不应默认纳入 Git。
- 精选可复现实验结果可以保留，但更适合通过 `docs/` 摘要、压缩样例或小型 fixture 管理。
- 当前 AGENTS 要求报告给文件级证据链接，和 README “禁止提交结果目录”存在张力；链接对本地审计有用，但不等于应该提交所有结果。

最小解决方案：

- `.gitignore` 可以保持不改，或后续由用户明确决定是否恢复 `benchmarks/results/` 忽略。
- 推荐新增 `benchmarks/results/README.md` 或 `docs/reproduce/benchmark-results-policy.md`，说明哪些结果可提交、哪些只作本地证据。
- 本轮不修改 `.gitignore`。

## 专项诊断三：Windows / Linux 跨平台兼容与虚拟环境策略

v0.0.3 报告提到的 Windows 兼容问题已在本轮静态核对与运行中得到部分确认：

- `.sh` 脚本在 PowerShell 下不是默认入口；本轮使用 `python -m tablecodeagent.benchmark.benchmark_runner` 等价运行。
- PowerShell heredoc 与 Bash 不同，不能使用 `python - <<'PY'`。
- `src/pyproject.toml:9` 要求 Python `>=3.11`，不能依赖旧 Anaconda Python。
- Windows 下 pandas/numpy/OpenBLAS 可能在线程初始化和内存上失败；本轮需要设置 BLAS 线程变量。
- `src/tablecodeagent/runtime/sandbox.py` 已补 `SystemRoot`、`SYSTEMROOT` 等 Windows 子进程变量，并在 `run_tests_in_sandbox()` 里设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- `src/mini_claude/tools.py` 已把 read/write 改成显式 UTF-8，并把 shell 中的 `python ...` 映射到当前解释器。

明确回答：不建议把 Linux 虚拟环境上传到 GitHub。

理由：

- 虚拟环境包含平台相关二进制、入口脚本和绝对路径，Windows / Linux 不可可靠复用。
- 体积大，会污染仓库，容易引入依赖供应链和安全风险。
- Git 适合管理源码、依赖声明和小型可复现样例，不适合管理可重建环境产物。

替代方案：

- 用 [`src/pyproject.toml`](../src/pyproject.toml) 记录主依赖；后续可补 `requirements.txt` 或 lock 文件。
- Windows 和 Linux 各自本地创建 `.venv`。
- `.venv/` 应加入 `.gitignore`，当前 `.gitignore` 已包含 `.venv/`。
- 提供或文档化 `scripts/setup_windows.ps1`、`scripts/setup_linux.sh`；当前仓库已有 `.sh` 运行脚本，但缺少 PowerShell 等价脚本。
- AutoDL 和本地同步源码、配置模板、任务数据、小型 curated result；不同步虚拟环境目录。

## 专项诊断四：v0.0.2 benchmark 重构、v0.0.3 修复与真实测评口径

v0.0.2 重构方向总体合理：

- 非 API 检查迁移到 `tests/`，避免把 fixed workflow 或 sandbox smoke 写成真实 Agent benchmark。
- 真实 benchmark 入口收敛到 `python -m tablecodeagent.benchmark.benchmark_runner` 和 `real_api_code_agent`。
- `expected.json` 在模型生成阶段被移动到 traces 副本，模型 prompt 明确禁止读取 `expected.json`。
- `results.jsonl` / `summary.json` / trace / workspace 结构便于归因。

v0.0.3 修复总体合理：

- `output_contract` 让公开 schema 不再完全依赖模型猜测。
- `_validate_answer_json()` 对 pytest 型任务返回 `passed: None`，避免把“answer.json 存在”误写成通过。
- `result_from_trace()` 的 passed 口径为 `failure_type is None` 且 `validation.passed is True` 或 `test_pass_rate == 1.0`。
- trace/result 已写入本轮要求核对的字段：`api_called`、`skipped`、`llm_tool_call_observed`、`tool_call_count`、`failure_type`、`code_generation_source`、`generated_code_path`、`answer_path`、`validation.passed`。

风险边界：

- 没有发现 `expected.json` 被直接传给模型或复制到生成阶段 prompt；但 workspace 在外部 pytest 前会恢复 `expected.json`，因此后续模型如果在生成代码阶段执行额外文件读取，必须继续依赖 `guarded_agent_tools()` 的路径限制和 prompt 约束。
- 当前 `implementation_hints.allowed_project_helpers` 会降低 benchmark 难度，不是 oracle 泄露，但会弱化自主代码生成评价。
- 顶层 `schema_check` 不能检查嵌套字段；本轮 credit 失败正是嵌套字段类型不匹配。
- 五次重复测评可作为轻量小样本稳定性观察，但不能声称统计充分。正式 benchmark 应记录每次 run 的模型、temperature、seed 或不可控采样条件、失败类型、成功率分布，并报告均值/方差/置信区间或至少成功率分布。

## 专项诊断五：信贷风控场景代码与架构风险

信贷风控新增内容证据级别：

- [`src/tablecodeagent/workflows/credit_risk_scoring.py`](../src/tablecodeagent/workflows/credit_risk_scoring.py)：可复用领域 workflow，但当前是最小规则卡示例，不是生产风控模型。
- [`benchmarks/tasks/credit_risk_scoring_001/`](../benchmarks/tasks/credit_risk_scoring_001/task.json)：单个 benchmark task / fixture。
- 项目测试 `test_credit_risk_scoring_workflow_expected_check.py`：非 API 固定 workflow smoke。
- 本轮真实 API：真实 LLM Agent 能力验证未通过。

合理点：

- 领域逻辑放在 `src/tablecodeagent/workflows/`，没有堆进 `src/mini_claude/tools.py`。
- workflow 使用 pandas / table_tools 读取、统计、评分，没有手写 CSV 解析。
- 数据包含重复申请、异常年龄、贷后泄漏字段，能覆盖基础风控数据质量问题。
- `default_90d` 和 `post_loan_collection_calls` 被排除为贷前特征，避免直接目标泄漏。

风险点：

- 规则卡评分是固定示例，不代表训练真实模型或通用风控能力。
- task 的公开 schema 对嵌套字段约束不足，真实模型生成了 pytest 不接受的 `leakage_columns_present` 对象。
- `business_rule_checks.leakage_columns_excluded` 当前只要发现泄漏列就为 true，语义偏弱；更准确应检查泄漏列确实不在 `feature_processing.excluded_columns` 外的特征集合中。
- `implementation_hints` 直接建议调用 helper，适合 smoke，不适合证明模型自主完成完整风控 workflow。

“规则卡评分是固定示例”的具体含义：

- 当前 [`credit_risk_scoring.py`](../src/tablecodeagent/workflows/credit_risk_scoring.py) 里的评分逻辑是人工写死的一组可复现规则，例如按债收比、贷收比、信用分、异常年龄、就业年限等字段计算 `risk_score`，再映射到 `low` / `medium` / `high` 风险档位。
- 它没有从历史样本中训练模型参数，也没有进行训练集 / 验证集 / 测试集切分、特征选择、类别编码、缺失值拟合、模型训练、阈值调优、AUC / KS / PR-AUC 等离线评估。
- 它没有完成生产风控必须关注的时间穿越检查、样本外稳定性、拒绝推断、群体公平性、模型监控、校准、审批策略联动和合规审计。
- 因此它能证明的是：该 fixture 可以检查 Agent 是否会读取申请表、发现重复主键、异常年龄、贷后泄漏字段，并输出一个结构化、可 pytest 校验的规则卡示例。
- 它不能证明的是：TableCodeAgent 已经具备训练真实信贷评分模型、泛化到任意风控数据集、替代生产风控建模流程，或完成通用风控 Agent 能力。
- 在 benchmark 口径上，这更接近“领域 workflow / fixture smoke”，不是“真实建模能力 benchmark”。后续如果要验证真实风控建模能力，应新增独立 task，要求 Agent 完成时间切分、训练/验证、指标报告、泄漏检查和严格外部校验。

最小修复建议：

- 明确 `credit_risk_scoring_001` 是 helper-assisted MVP fixture，不是生产风控能力。
- 补充嵌套 schema 契约，尤其 `data_quality.duplicate_keys`、`data_quality.leakage_columns_present`、`feature_processing.excluded_columns`。
- 后续 no-helper task 要求模型用 pandas/numpy 成熟接口处理，不允许标准库手写 CSV 聚合替代常规表格能力，除非是 Windows 依赖失败时的临时降级且必须记录。

## 外部实践参考

本轮使用 `$academic-web-search` 检索，外部结论只作为评测实践参考，不替代本仓库代码证据。

- HumanEval / Codex 论文，2021：<https://arxiv.org/abs/2107.03374>。代码生成评测常用 pass@k，多样本采样用于估计若干候选中至少一个通过测试的概率；对本项目的落地点是：重复运行可以观察采样稳定性，但要记录 k、温度和通过率分布。
- HELM，Stanford CRFM，2022 起持续维护：<https://crfm.stanford.edu/helm/>。强调多场景、多指标和透明评估；对本项目的落地点是：不要只报告 pass/fail，应报告失败类型、成本、工具调用和不确定性边界。
- AgentBench，ICLR 2024 / arXiv 2023：<https://arxiv.org/abs/2308.03688>。LLM-as-Agent 评测需要交互环境、工具使用和多轮决策，不只是单轮文本输出；对本项目的落地点是：`tool_call_count`、`llm_tool_call_observed`、环境失败和任务失败应分开。
- SWE-bench 官方项目：<https://www.swebench.com/>。软件工程 benchmark 以真实 issue、补丁和测试为核心；对本项目的落地点是：生成代码必须由外部测试/validator 校验，不能只看文件存在或模型解释。
- OpenAI Evals 文档：<https://github.com/openai/evals>。工程 eval 应把样本、运行器、评分器分开；对本项目的落地点是：task、runner、trace、validation 的边界应保持清晰，防止 oracle/expected 泄露。

## 建议修复路线

必须先修：

- 为 Windows benchmark 文档或脚本加入 BLAS 线程变量和 PowerShell 等价命令。
- 扩展 `output_contract`，覆盖 pytest 读取的关键嵌套字段。
- 把 `api_error_type=APITimeoutError` 单独分类，避免混入泛化 `real_api_code_agent_error`。
- 在 README / 报告里明确 helper-assisted benchmark 的证据级别。

建议后续修：

- 增加 no-helper real API task 口径，与 helper-assisted smoke 分开统计。
- 增加 `benchmarks/results` 提交策略文档或 curated fixture 策略。
- 为 Windows / Linux 各提供 setup 脚本，依赖由 `pyproject.toml` / lock 文件管理。
- 对 5 次重复运行生成成功率和失败类型分布摘要。

暂不建议做：

- 不上传 Linux `.venv` 到 GitHub。
- 不放宽 pytest / validation 让当前真实 API 通过。
- 不把 `benchmarks/results/` 大量历史运行产物全部提交。
- 不把信贷风控 fixture 包装成生产风控模型、SFT、RL、RAG、Memory 增强或 SOTA 项目。

## 未验证项与风险边界

- 静态审阅已覆盖入口、调用链、工具注册、数据路径、benchmark 输出路径、trace 字段和 validation 方式。
- 真实 API 已运行并覆盖 `growth_campaign_audit_001` 与 `credit_risk_scoring_001`，但两者均未通过。
- Linux / AutoDL 环境未复测，Windows 兼容结论不能自动外推到 Linux。
- v0.0.3 版本边界未完全确认，因为 v0.0.3 变更尚未形成 commit；本文基于当前工作区 diff 和当前源码。
- 外部实践参考只用于评测口径建议，不能证明 TableCodeAgent 当前已达到对应 benchmark 水平。

## 补充复测：growth_campaign_audit_001 使用 deepseek.env

复测时间：2026-06-07。

复测目标：删除旧 API 配置导致的错误归因，改用 `configs/api/local/deepseek.env` 对 `growth_campaign_audit_001` 重复运行 3 次，重新判断 `APITimeoutError` 是否复现，以及失败是 API/网络问题、代码层超时，还是模型生成代码/校验问题。

复测前提：

- 使用明确指定的 env 文件：`configs/api/local/deepseek.env`。
- 已确认该 env 文件存在，且包含 `MINI_CLAUDE_MODEL`、`MINI_CLAUDE_API_BASE`、`OPENAI_API_KEY` 变量名。
- 未输出 API key、token 或 secret 值。
- Windows 下继续设置 BLAS 线程变量，避免 OpenBLAS 初始化问题干扰真实 API 归因。

复测命令：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:NUMEXPR_MAX_THREADS = '1'

.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/deepseek.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-group v0.0.3-growth-deepseek-retest-1

.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/deepseek.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-group v0.0.3-growth-deepseek-retest-2

.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/deepseek.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-group v0.0.3-growth-deepseek-retest-3
```

三次结果目录：

- [`deepseek-retest-1 results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-135737__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-1/results.jsonl)
- [`deepseek-retest-1 trace`](../benchmarks/results/real_api_code_agent/20260607-135737__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-1/traces/growth_campaign_audit_001.real_api_code_agent.json)
- [`deepseek-retest-1 solve.py`](../benchmarks/results/real_api_code_agent/20260607-135737__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-1/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)
- [`deepseek-retest-1 answer.json`](../benchmarks/results/real_api_code_agent/20260607-135737__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-1/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)
- [`deepseek-retest-2 results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-135931__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-2/results.jsonl)
- [`deepseek-retest-2 trace`](../benchmarks/results/real_api_code_agent/20260607-135931__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-2/traces/growth_campaign_audit_001.real_api_code_agent.json)
- [`deepseek-retest-2 solve.py`](../benchmarks/results/real_api_code_agent/20260607-135931__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-2/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)
- [`deepseek-retest-2 answer.json`](../benchmarks/results/real_api_code_agent/20260607-135931__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-2/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)
- [`deepseek-retest-3 results.jsonl`](../benchmarks/results/real_api_code_agent/20260607-140112__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-3/results.jsonl)
- [`deepseek-retest-3 trace`](../benchmarks/results/real_api_code_agent/20260607-140112__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-3/traces/growth_campaign_audit_001.real_api_code_agent.json)
- [`deepseek-retest-3 solve.py`](../benchmarks/results/real_api_code_agent/20260607-140112__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-3/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)
- [`deepseek-retest-3 answer.json`](../benchmarks/results/real_api_code_agent/20260607-140112__model-deepseek-v4-flash__tasks-v0.0.3-growth-deepseek-retest-3/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)

复测结果汇总：

| run | api_called | skipped | llm_tool_call_observed | tool_call_count | failure_type | api_error_type | generated_code_saved | answer_file_saved | test_pass_rate | pytest_exit_code |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- | ---: | ---: |
| deepseek-retest-1 | true | false | true | 13 | `code_execution_failed` | null | true | true | 1.0 | 0 |
| deepseek-retest-2 | true | false | true | 21 | `real_api_code_agent_error` | `JSONDecodeError` | true | false | null | null |
| deepseek-retest-3 | true | false | true | 13 | `code_execution_failed` | null | true | true | 0.0 | 1 |

结论：

- 三次 deepseek 复测均未复现 `APITimeoutError`。
- 三次均 `api_called=true`、`skipped=false`、`llm_tool_call_observed=true`，说明 deepseek env 读取、API 请求、模型返回和工具调用链路均可达。
- 失败已经从 API 超时问题推进到生成代码 / 运行时 / 输出契约问题。
- 当前证据不支持“本仓库代码中防御性 API 超时设置导致报错”。代码层核对显示，当前 `AsyncOpenAI` 初始化和 `chat.completions.create()` 调用未显式传入自定义 API timeout。

逐次归因：

- deepseek-retest-1：模型生成了 `solve.py` 和 `answer.json`，外部 pytest 通过，`test_pass_rate=1.0`，但 `solve.py` 最后打印了 emoji，Windows GBK 控制台编码失败，导致 `run_python.exit_code=1`，runner 因 [`real_api_code_agent.py:501`](../src/tablecodeagent/benchmark/real_api_code_agent.py) 优先记为 `code_execution_failed`。这是接近通过但被生成代码的控制台输出编码问题拉失败。
- deepseek-retest-2：模型生成了 `solve.py`，但 runner 在读取 / 解析 `answer.json` 时出现 `JSONDecodeError: Expecting value`，`answer_file_saved=false`。这属于模型生成的 JSON 写入不完整或非法 JSON 问题。
- deepseek-retest-3：模型生成了 `solve.py` 和 `answer.json`，顶层 `schema_check.passed=true`，但 pytest 失败，原因是 `unique_keys.rewards_duplicate_key.duplicate_key_count` 缺失；这与前文 finding 一致，即公开 `output_contract` 没有把 pytest 真实依赖的 `unique_keys` 写入必填契约。

代码层超时核对：

- [`src/mini_claude/agent.py:235`](../src/mini_claude/agent.py) 创建 `openai.AsyncOpenAI(base_url=api_base, api_key=api_key)`，当前代码没有显式传入自定义 `timeout`。
- [`src/mini_claude/agent.py:1247`](../src/mini_claude/agent.py) 调用 `chat.completions.create(...)`，当前代码没有显式传入自定义 `timeout`。
- [`src/tablecodeagent/benchmark/real_api_code_agent.py:431`](../src/tablecodeagent/benchmark/real_api_code_agent.py) 创建 Agent 时设置 `max_turns=10`，这是最大交互轮数，不是 API 请求超时。
- [`src/tablecodeagent/benchmark/real_api_code_agent.py:499`](../src/tablecodeagent/benchmark/real_api_code_agent.py) 到 [`src/tablecodeagent/benchmark/real_api_code_agent.py:508`](../src/tablecodeagent/benchmark/real_api_code_agent.py) 是 sandbox / schema / pytest 失败分类逻辑，不是模型 API 超时逻辑。

可能解决方案：

1. 在 task prompt 或 runner wrapper 中明确禁止生成代码打印 emoji 或其他 Windows GBK 可能无法编码的字符；或者 sandbox 环境强制 `PYTHONIOENCODING=utf-8`。
2. 对 `answer.json` 增加写后读取自检；如果 JSON 非法，优先分类为 `answer_json_invalid`，不要落到泛化 `real_api_code_agent_error`。
3. 扩展 `output_contract`，把 `unique_keys.rewards_duplicate_key.duplicate_key_count` 和 `unique_keys.rewards_duplicate_key.key_columns` 写入公开契约，避免模型满足顶层 schema 但仍不满足 pytest。
4. 调整 runner 通过口径的解释：如果 `pytest_exit_code=0` 但 `run_python.exit_code!=0`，应保留失败，但 failure detail 要突出“答案已生成且 pytest 通过，失败来自脚本收尾输出/退出码”，避免误判为计算逻辑失败。
5. 后续若要继续排查 API timeout，可在 API 服务稳定时单独增加 `api_timeout` 分类和可配置 `TABLECODEAGENT_API_TIMEOUT_SECONDS`，并把 timeout 值写入 trace。

