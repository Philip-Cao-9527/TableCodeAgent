# v0.0.5 代码审核报告

## 审核范围

本轮是只读代码审核，目标是审核当前仓库中用户口径的 TableCodeAgent `v0.0.5` 变更。唯一允许写入的文件是本报告：`docs/reproduce/code-review-v0.0.5-20260608.md`；未修改业务代码、测试、README、架构文档或历史修复报告。

版本证据来自当前仓库的 `docs/reproduce/fix-report-v0.0.5-20260608.md`、README、架构文档和相关源码。根目录未假设存在 `pyproject.toml`；已核对 `src/pyproject.toml`，其中 baseline 包版本不能直接等同于 TableCodeAgent `v0.0.5`。

真实 API 测试边界：本轮不运行真实 LLM/API benchmark，不读取或输出任何真实 key/token/secret，不运行 `scripts/run_real_api_code_agent_benchmark.sh`、`scripts/run_deepseek_smoke.sh`、`scripts/run_openai_compatible_smoke.sh` 或等价真实 API 命令。历史真实 API 结果只作为历史报告证据引用，不作为本轮复测结论。

## 必读材料与代码入口

已读必读文档：

- `.codex/AGENTS.md`
- `README.md`
- `docs/reproduce/tablecodeagent_architecture.md`
- `docs/reproduce/why_table_code_agent.md`
- `docs/reproduce/fix-report-v0.0.5-20260608.md`
- `docs/reproduce/fix-report-v0.0.4-20260608.md`
- `docs/reproduce/code-review-v0.0.4-20260608.md`
- `src/pyproject.toml`

已核对 v0.0.5 直接相关代码、任务与测试：

- `src/tablecodeagent/table_tools/core.py`
- `src/tablecodeagent/table_tools/quality.py`
- `src/tablecodeagent/agent_tools.py`
- `src/mini_claude/tools.py`
- `src/tablecodeagent/benchmark/benchmark_runner.py`
- `src/tablecodeagent/benchmark/real_api_code_agent.py`
- `src/tablecodeagent/benchmark/answer_models.py`
- `src/tablecodeagent/validation/answer.py`
- `src/tablecodeagent/tracing/logger.py`
- `src/tablecodeagent/workflows/finance_operations.py`
- `src/tablecodeagent/workflows/credit_risk_scoring.py`
- `src/tablecodeagent/workflows/growth_campaign_audit.py`
- `benchmarks/tasks/*/task.json`
- `benchmarks/tasks/*/tests/test_solution.py`
- `tests/test_unit/`
- `tests/test_integration/`

v0.0.5 fix report 声称的主要变更是新增财务运营 workflow、answer schema、benchmark task、测试、skill 文档和真实 API benchmark 记录。已对照当前代码确认：财务运营 deterministic workflow、task contract、Pydantic schema、pytest validator 和本地回归测试均已落地；历史真实 API 两次结果仍未通过，不能写成本轮通过。

## Findings first

### P1：`no_helper` 防护仍依赖字符串 denylist，v0.0.4 评审风险在 v0.0.5 中未根治

- 严重级别：P1 / 中等偏高。
- 文件路径：`src/tablecodeagent/benchmark/real_api_code_agent.py`。
- 证据：`FORBIDDEN_HELPER_MARKERS` 仍是固定字符串列表；`_generated_helper_usage_denial()` 读取生成的 `solve.py` 后只做子串匹配；sandbox 执行生成代码时仍把仓库 `src` 注入 `PYTHONPATH`。当前定位到的行号为 `real_api_code_agent.py:30`、`real_api_code_agent.py:302`、`real_api_code_agent.py:610`、`real_api_code_agent.py:619`。v0.0.4 审核报告已经把同类问题列为 Finding 1，v0.0.5 未改变该防护模型。
- 影响：如果模型用动态 import、字符串拼接 import、间接导入或运行期反射绕过子串检查，生成代码仍可能调用 `tablecodeagent.workflows` 或 `build_*_report()` 等 helper。这样 `results.jsonl` 可能仍显示 `benchmark_profile=no_helper`、`helper_hints_exposed=false`，但结果已被 helper-assisted 污染，影响真实 benchmark 口径。
- 最小修复建议：no-helper 模式执行 `solve.py` 时优先不要把项目 `src` 放入生成代码的 `PYTHONPATH`；若 pytest 或 runner 必须访问项目包，则对生成代码增加 AST/import hook 级禁止策略，覆盖 `Import`、`ImportFrom`、`__import__`、`importlib.import_module` 和字符串拼接导入。
- 验证建议：新增不触发真实 API 的 sandbox 回归测试，构造恶意 `solve.py` 分别使用显式 import、`importlib.import_module("tablecodeagent." + "workflows...")`、`__import__` 和 helper 函数间接调用，期望 runner 记录 `failure_type=helper_usage_forbidden` 或执行期 import 失败。

### P2：`api_called` 在进入真实 provider 前置为 `true`，失败归因仍可能漂移

- 严重级别：P2 / 中等。
- 文件路径：`src/tablecodeagent/benchmark/real_api_code_agent.py`。
- 证据：`trace["api_called"] = True` 位于 `await agent.run_once(_task_prompt(workspace))` 之前，当前定位到 `real_api_code_agent.py:593` 和 `real_api_code_agent.py:595`。Python 会先求值 `_task_prompt(workspace)`，再进入 `run_once()`；如果 prompt 构造或 workspace 前置读取失败，trace 仍可能记录 `api_called=true`。v0.0.4 审核报告 Finding 2 已指出该边界，v0.0.5 未改动。
- 影响：真实 API 归因字段可能把本地前置失败误记为已发起 API 调用，影响 `api_called`、`skipped`、`failure_type` 的审计口径，也会误导后续成本、稳定性和 API 可用性分析。
- 最小修复建议：先构造 prompt 并完成 workspace 前置检查，再设置 API 调用状态；更稳的方案是在 provider 请求入口设置 `api_request_started=true` / `api_called=true`，并区分 `api_attempted`、`api_completed`。
- 验证建议：用 mock 或 monkeypatch 构造 `_task_prompt()` 抛错、`Agent.run_once()` 进入前抛错、provider 请求后抛错三类场景，断言 `api_called`、`api_error_type`、`failure_type` 分别符合实际阶段。

### P2：README 同时呈现 v0.0.4 版本口径、v0.0.5 内容和开发日志，入口文档存在误导风险

- 严重级别：P2 / 中等。
- 文件路径：`README.md`。
- 证据：README version badge 仍显示 `v0.0.4`，正文写“当前 `v0.0.4` 已完成以下可验证能力”，但同一能力列表已经包含 v0.0.5 财务运营 workflow；Roadmap 附近仍保留 Codex 进度播报和历史真实 API 命令日志。当前定位到 `README.md:13`、`README.md:62`、`README.md:72`、`README.md:345`、`README.md:359`、`README.md:373`。
- 影响：用户从 README 进入项目时容易混淆 v0.0.4 与 v0.0.5 的版本边界，也可能把历史真实 API 命令、开发过程日志或旧版复测记录误读为当前推荐执行流程或本轮验证结论。
- 最小修复建议：后续单独清理 README，不在本轮审核中直接修改。最小改法是统一版本段落，保留 v0.0.5 的真实能力边界；把开发过程长日志移入对应 reproduce 报告或删除；历史真实 API 结果要标明日期、任务组和是否通过。
- 验证建议：文档修复后用 `rg -n "v0.0.4|v0.0.5|真实 API|Ran \\$env|🧩 步骤" README.md` 复查，确认入口文档只保留稳定使用说明，不混入历史流水日志。

### P3：提交前仍需人工确认生成/缓存/敏感配置文件边界

- 严重级别：P3 / 轻微。
- 文件路径：工作区状态、`.gitignore`、`benchmarks/results/`、`configs/api/local/`。
- 证据：`git status --short` 显示当前工作区存在多处未提交改动和新增结果目录，包括 `benchmarks/results/real_api_code_agent/...`、`benchmarks/tasks/finance_operations_001/`、`.tca/skills/finance-operations/` 等；本轮只列出 `configs/api/local` 下文件名为 `deepseek.env`、`provider_chatanywhere.env`、`provider_tiktok.env`，未读取内容。`.gitignore` 已包含 `.env`、`__pycache__/`、`*.pyc`、`configs/api/local/`，但提交前仍需确认实际暂存内容。
- 影响：如果误把本地 API env、缓存文件或大体积历史结果当作业务变更提交，可能引入敏感信息、仓库体积膨胀或评测证据口径混乱。
- 最小修复建议：提交前单独执行 `git status --short`、`git diff --stat`、`git check-ignore configs/api/local/deepseek.env` 和缓存文件扫描；只提交经过人工确认的结果证据，不提交 env 内容和 `__pycache__` / `.pyc`。
- 验证建议：在最终提交前用 `git ls-files configs/api/local benchmarks/results --error-unmatch` 或等价命令确认敏感配置未被跟踪；如需要提交 benchmark 结果，先做 secret 扫描和体积检查。

## 未发现明确问题的区域

- 财务运营核心能力位于 `src/tablecodeagent/workflows/finance_operations.py`，未发现把业务 workflow 塞进 `src/mini_claude/` 的结构回归。
- `src/mini_claude/tools.py` 通过 `TABLE_TOOL_DEFINITIONS` 和 `execute_table_tool()` 做轻量工具注册与本地 routing，未发现 v0.0.5 将 mini_claude 扩展成业务分析层。
- 表格工具当前支持 CSV、XLSX、多 header、merged cell 填充、`.feather`、`.npy/.npz`；`query_multi_table` 对 exactly two tables 的限制在代码和 tool schema 中可见，未发现描述成任意多表 join 的夸大。
- `benchmarks/tasks/finance_operations_001/task.json` 已公开 `output_contract.validation_mode=pytest`、`missing_value_normalization`、schema 约束和 no-helper 禁止说明；未发现向模型公开 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`、完整 workflow import 路径或 `build_*_report()`。
- `FinanceOperationsAnswer` 相关 schema 已覆盖 due date 缺失值边界，`due_date` validator 拒绝空字符串、`nan`、`NaT` 等 NaN-like 字符串。
- `benchmarks/tasks/finance_operations_001/tests/test_solution.py` 对 `missing_po_invoice_ids`、`INV-1006.due_date is None`、`missing_po` exception 等 v0.0.5 关键口径已有 pytest 断言。
- `tracing/logger.py` 和 `benchmark_runner.py` 已提供 `api_called`、`skipped`、`tool_call_count`、`validation`、`failure_type`、`summary.json` 等基本归因字段。注意：`TRACE_VERSION` 当前仍为 `v0.0.4`，架构文档也这样描述；本轮未发现 v0.0.5 新增 trace schema 字段必须 bump 的直接证据，但版本边界需在后续文档中保持清楚。

## 非 API 验证记录

当前环境：

- 操作系统：Microsoft Windows 10 家庭中文版。
- Shell：Windows PowerShell `5.1.19041.6456`。
- Python：`D:\桌面\TableCodeAgent\.venv\Scripts\python.exe`，版本 `3.14.0`。
- 本轮未运行任何真实 API / LLM 端到端测试，未读取 `configs/api/local/*.env` 内容。

实际执行的非 API 命令：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration
```

结果摘要：

- `platform win32 -- Python 3.14.0, pytest-9.0.3`
- `collected 29 items`
- `29 passed in 8.28s`

覆盖范围包括表格工具 smoke、Agent 工具注册与 routing、real_api_code_agent contract、财务运营 workflow expected check、模拟 Agent 输出、sandbox fixed `solve.py` 和 growth / credit 历史 workflow 回归。Windows 下未运行 `.sh` 脚本；本轮使用 PowerShell 原生命令和 `.venv\Scripts\python.exe -m pytest ...` 作为非 API 等价验证。

## 未验证项与剩余风险

- 真实 API 测试未执行，原因：用户明确要求本轮不需要真实 API 测试。
- 历史 v0.0.5 fix report 记录过两次财务运营真实 API benchmark，但这不是本轮复测。历史 pass1 为 `api_called=true`、`schema_check.passed=true`、`run_python.exit_code=0`、`pytest_exit_code=1`、`failure_type=pytest_failed`，失败点是 `missing_po_invoice_ids` 未包含 `INV-1006`。历史 pass2 为 `api_called=true`、`schema_check.passed=false`、`run_python.exit_code=1`、`failure_type=code_execution_failed`，失败摘要为 `KeyError: 'tables'`，未生成 `answer.json`。
- v0.0.5 的 deterministic、本地 schema 和 pytest 已通过，但真实 no-helper 模型是否能稳定生成通过 `finance_operations_001` 的 `solve.py` 仍未验证。
- no-helper 防护仍需要更强的 import/runtime 隔离，否则后续通过结果仍需人工审计生成代码是否 helper-assisted。
- README 与版本口径清理未在本轮执行，仍需后续单独处理。
- `.tca/skills/finance-operations` 是文档化 skill 资产；本轮未验证 runtime 自动发现或自动加载该 skill。

## 结论

本轮未发现 v0.0.5 deterministic 财务运营 workflow、Pydantic schema、task pytest、表格工具注册和本地回归测试的阻塞级 P0 问题。非 API 测试 `tests/test_unit tests/test_integration` 全部通过。

但 v0.0.5 仍存在评测口径层面的 P1/P2 风险：no-helper 防护仍依赖字符串 denylist，`api_called` 归因边界仍可能漂移，README 仍混合 v0.0.4 / v0.0.5 和历史开发日志。建议下一步最小处理顺序是：先收紧 no-helper sandbox/import 边界并补回归测试，再修正 `api_called` 归因字段，最后单独清理 README 版本与历史日志口径。真实 API 通过性仍应标为未验证，不能把历史失败或本轮非 API 通过写成真实 LLM benchmark 通过。
