# fix-report-v0.0.3-20260607

## 1. 目标

本轮按 `v0.0.3 benchmark 审阅、失败归因与信贷风险评分 workflow 计划` 实施最小必要改动，重点解决三类问题：

- 真实 API benchmark 失败归因不够清晰，尤其是 `answer.json` 顶层 schema 错误会被混在 `pytest_failed` 中。
- pytest 型任务没有 `expected.answer` 时，`validation_pass_rate` 曾把“`answer.json` 存在”写成通过，容易误导真实 API 归因。
- 新增信贷风险评分 coding agent workflow 需要复用通用 runner、公开输出契约和 pytest/trace 验证链路，不能堆进 `src/mini_claude/tools.py`。

## 2. 改动文件

- [src/tablecodeagent/benchmark/real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py)
- [src/tablecodeagent/tracing/logger.py](../../src/tablecodeagent/tracing/logger.py)
- [src/tablecodeagent/runtime/sandbox.py](../../src/tablecodeagent/runtime/sandbox.py)
- [src/tablecodeagent/workflows/credit_risk_scoring.py](../../src/tablecodeagent/workflows/credit_risk_scoring.py)
- [src/mini_claude/agent.py](../../src/mini_claude/agent.py)
- [src/mini_claude/tools.py](../../src/mini_claude/tools.py)
- [benchmarks/tasks/growth_campaign_audit_001/task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json)
- [benchmarks/tasks/credit_risk_scoring_001/task.json](../../benchmarks/tasks/credit_risk_scoring_001/task.json)
- [benchmarks/tasks/credit_risk_scoring_001/applications.csv](../../benchmarks/tasks/credit_risk_scoring_001/applications.csv)
- [benchmarks/tasks/credit_risk_scoring_001/expected.json](../../benchmarks/tasks/credit_risk_scoring_001/expected.json)
- [benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py](../../benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py)
- [tests/test_unit/test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py)
- [tests/test_integration/test_credit_risk_scoring_workflow_expected_check.py](../../tests/test_integration/test_credit_risk_scoring_workflow_expected_check.py)
- [README.md](../../README.md)
- [.gitignore](../../.gitignore)
- [docs/reproduce/tablecodeagent_architecture.md](./tablecodeagent_architecture.md)

## 3. 关键修复

### 3.1 公开输出契约

`task.json` 新增 `output_contract`：

- `validation_mode`
- `answer_json_required_keys`
- `schema_description`

`real_api_code_agent` prompt 只暴露公开契约和任务文件，不暴露 `expected.json` 的答案值。

### 3.2 schema 自检与失败分类

`real_api_code_agent` 在 `solve.py` sandbox 执行后、pytest 前执行 `_schema_check_answer_json()`，并继续运行 pytest。trace/result 会写入：

- `schema_check`
- `answer_file_saved`
- `pytest_exit_code`
- `pytest_failure_summary`
- `tool_error_count`
- `api_error_type`

如果 `answer.json` 缺少公开契约要求的顶层字段，`failure_type` 优先记为 `answer_schema_mismatch`。这不会跳过 pytest，也不会放宽正确性口径。

### 3.3 pytest 型 validation 口径

当 `expected.json` 没有 `answer` 且 `output_contract.validation_mode == "pytest"` 时，`_validate_answer_json()` 返回 `passed: None`。因此 `validation_pass_rate` 不再把“`answer.json` 存在”写成任务通过。

最终通过口径为：

- `failure_type is None`
- 且 `validation.passed is True` 或 `test_pass_rate == 1.0`

### 3.4 信贷风险评分 workflow

新增 `src/tablecodeagent/workflows/credit_risk_scoring.py`，领域逻辑保留在 `tablecodeagent` 包内，不放入 `src/mini_claude/tools.py`。最小输出统一为 `answer.json`，顶层包含：

- `row_counts`
- `field_summary`
- `data_quality`
- `feature_processing`
- `scoring_result`
- `business_rule_checks`
- `explanations`
- `warnings`
- `how_to_do_differently`
- `validation`

新增 `benchmarks/tasks/credit_risk_scoring_001/` fixture，覆盖重复申请主键、异常年龄、贷后泄漏字段、特征排除、规则卡评分、高风险样本和 pytest 外部校验。

## 4. 验证结果

本轮后续已在 Windows 下创建仓库本地虚拟环境：

```powershell
C:\Python314\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e src
```

虚拟环境版本：

```text
Python 3.14.0
pluggy 1.6.0
pytest 9.0.3
numpy 2.4.6
pandas 3.0.3
```

已执行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src/tablecodeagent src/mini_claude tests
```

结果：通过。

已执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration
```

结果：通过。

```text
10 passed in 2.99s
```

已执行直接 helper 验证：

```text
real_api_contract_helpers=passed
```

该验证确认 `_schema_check_answer_json()` 能识别缺失顶层字段，且 pytest 型 `_validate_answer_json()` 不再把 `answer.json` 存在记为通过。

已对营销增长与信贷风控两个场景按 benchmark workspace 形态单独复测：复制任务目录、写入最小 `solve.py`、生成 `answer.json`，再运行任务自带 `tests/test_solution.py`。

```text
growth_campaign_audit_001: run_exit_code=0, test_exit_code=0, 1 passed
credit_risk_scoring_001: run_exit_code=0, test_exit_code=0, 1 passed
```

同时修复了后续复测暴露的问题：

- `src/tablecodeagent/runtime/sandbox.py`：补齐 Windows 子进程必要环境变量，并在 sandbox 内 pytest 关闭第三方插件自动加载，避免 benchmark 被外部插件污染。
- `src/tablecodeagent/workflows/credit_risk_scoring.py`：内部 validation 的 `output_keys` 检查把最终写回的 `validation` 顶层字段计入输出契约。
- `src/mini_claude/agent.py`：真实 API benchmark 使用 `is_sub_agent=True`，该路径不再打印工具调用、工具结果和权限提示，避免 Windows GBK 控制台被 emoji / 特殊符号打断。
- `src/mini_claude/tools.py`：文件工具统一显式使用 `encoding="utf-8"`；`run_shell` 中的 `python ...` 映射到当前 `.venv` 的 `sys.executable`，避免模型自测时误用系统 Anaconda Python。
- `src/tablecodeagent/benchmark/real_api_code_agent.py`：prompt 增加公开 `implementation_hints`，用于告诉模型可以复用项目 helper，但不暴露 `expected.json`。

### 4.1 Windows 兼容性记录

本轮从 v0.0.3 Plan Mode 审阅到真实 API 重复测试期间，在 Windows 环境中遇到以下兼容性问题，后续做 Windows/Linux 双环境开发时需要纳入回归清单：

- Shell 差异：`bash scripts/run_benchmark_smoke.sh` 和 `bash scripts/run_real_api_code_agent_benchmark.sh` 在当前 Windows PowerShell 环境不可直接运行；后续需要提供 PowerShell 等价命令或 Python 入口文档。
- PowerShell heredoc 差异：`python - <<'PY'` 是 Bash 写法，在 PowerShell 下会报 `Missing file specification after redirection operator`；本轮改用 `@' ... '@ | python -`。
- 基础 Python 环境不满足项目要求：系统默认 `python` 是 Anaconda `Python 3.9.7`，项目声明 `requires-python >=3.11`，且该环境缺少 `pluggy`，`pytest` 无法启动。
- Anaconda 依赖损坏：默认环境中 `numpy` 导入后没有 `__version__`，导致 `pandas` 报 `AttributeError: module 'numpy' has no attribute '__version__'`。
- 本地虚拟环境：已用 `C:\Python314\python.exe -m venv .venv` 创建仓库本地虚拟环境，并安装 `pytest 9.0.3`、`pluggy 1.6.0`、`numpy 2.4.6`、`pandas 3.0.3`；`.venv/` 已加入 `.gitignore`，不应提交。
- editable install 副作用：`.\.venv\Scripts\python.exe -m pip install -e src` 曾改动 `src/claude_code_from_scratch.egg-info/`，这是安装生成物副作用，已恢复，不作为功能变更提交。
- Windows 子进程环境变量：sandbox 早期 allowlist 去掉了 `SYSTEMROOT`、`SYSTEMDRIVE`、`COMSPEC`、`OS`、`TEMP`、`TMP` 等变量，导致 Python 子进程导入 `asyncio/_overlapped` 时报 `OSError: [WinError 10106]`；已在 `src/tablecodeagent/runtime/sandbox.py` 补齐。
- pytest 插件污染：sandbox 内 `python -m pytest` 会自动加载当前环境第三方插件，例如 `anyio`，在受限 Windows env 下触发 `_overlapped` 初始化失败；已在 `run_tests_in_sandbox()` 设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- 控制台编码：Windows PowerShell 默认 GBK 输出不能编码 `📖`、`ℹ`、`✅` 等符号，真实 API 子 Agent 曾因此记录 `UnicodeEncodeError`；已让 `is_sub_agent=True` 的真实 benchmark 路径跳过工具调用、工具结果和权限提示的 UI 打印。
- 文件编码：`src/mini_claude/tools.py` 原先多处 `Path.read_text()` / `write_text()` 未指定 encoding，在 Windows 下默认 GBK，读取 UTF-8 任务文件或写入中文/符号内容会失败；已改为显式 `encoding="utf-8"`。
- Python 解释器选择：`run_shell` 原先执行 `python solve.py` 时会走 PATH 中的 Anaconda Python，而不是当前 `.venv` Python，导致模型自测误报 pandas/numpy 损坏；已把 shell 工具中的 `python ...` 映射到 `sys.executable ...`。
- 路径显示：包含中文的仓库路径 `D:\桌面\TableCodeAgent` 在部分 runner 输出中显示为 `D:\����\TableCodeAgent`，trace 内路径仍可用，但后续跨平台报告中应优先使用相对路径。
- PowerShell 资源异常：一次轻量 env 检查时 PowerShell 报 `The paging file is too small for this operation to complete` 并终止；后续长时间真实 API 循环应减少控制台大段输出，优先汇总 result/trace 字段。
- 长日志输出：真实 API 循环如果直接把工具结果打到 PowerShell，会产生大量输出并放大编码/资源问题；后续应优先把完整日志写到临时文件，再只汇总 `results.jsonl` 和 trace 字段。
- benchmark 结果目录：本轮按用户要求不忽略 `benchmarks/results/`，所以真实 API 或 SKIP 结果会显示为未跟踪文件；提交前需人工确认是否纳入版本库。

## 5. 真实 API 状态

上一轮没有运行真实 API 重复 5 次测试，原因是当轮请求没有明确要求读取具体 env 文件；按照仓库规则，真实 API 验证只能读取用户指定 env 文件，不能自行扫描或猜测 `configs/api/local/` 下的密钥配置。

本轮用户已要求进行真实 API 重复测试，并读取用户指定 env 文件；后续测试使用 `configs/api/local/provider_chatanywhere.env`。

已检查该指定路径：

```text
configs/api/local/provider_chatanywhere.env
```

结果：文件不存在，因此无法发起真实 API 调用。

已按 benchmark runner 运行一次双任务 SKIP 记录：

```powershell
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/provider_chatanywhere.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-dir benchmarks/tasks/credit_risk_scoring_001 `
  --task-group v0.0.3-env-missing-check
```

结果目录：

```text
benchmarks/results/real_api_code_agent/20260607-015513__model-unknown__tasks-v0.0.3-env-missing-check
```

两条结果均为：

```text
api_called=false
skipped=true
failure_type=api_env_missing
```

这只能证明 runner 对 env 缺失的 SKIP 记录口径正确，不能写成真实 API benchmark 通过，也不能用于模型稳定性结论。

### 5.2 env 上传后真实 API 重测

用户上传 env 后，已确认 `configs/api/local/provider_chatanywhere.env` 存在，且包含必要键名：

```text
MINI_CLAUDE_MODEL
MINI_CLAUDE_API_BASE
OPENAI_API_KEY
```

未在报告或终端摘要中输出 API key 值。

按用户后续要求，真实 API 回归只跑 2 轮，避免耗时过长。最终 2 轮重测命令形态：

```powershell
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/provider_chatanywhere.env `
  --task-dir benchmarks/tasks/growth_campaign_audit_001 `
  --task-dir benchmarks/tasks/credit_risk_scoring_001 `
  --task-group v0.0.3-real-api-retry-N
```

最终 2 轮结果目录：

```text
benchmarks/results/real_api_code_agent/20260607-032932__model-deepseek-v4-flash__tasks-v0.0.3-real-api-retry-1
benchmarks/results/real_api_code_agent/20260607-033327__model-deepseek-v4-flash__tasks-v0.0.3-real-api-retry-2
```

两轮均已真实调用 API：

```text
api_called=true
skipped=false
model_name=deepseek-v4-flash
```

汇总：

| run | task | result |
| --- | --- | --- |
| retry-1 | `growth_campaign_audit_001` | `failure_type=real_api_code_agent_error`，`api_error_type=JSONDecodeError`，`llm_tool_call_observed=true`，`tool_call_count=23`，`generated_code_saved=true`，`answer_file_saved=false` |
| retry-1 | `credit_risk_scoring_001` | `failure_type=code_execution_failed`，`llm_tool_call_observed=true`，`tool_call_count=8`，`generated_code_saved=true`，`answer_file_saved=true`，`schema_check.passed=true`，pytest 摘要为 `KeyError: 'duplicate_key_count'` |
| retry-2 | `growth_campaign_audit_001` | `failure_type=pytest_failed`，`llm_tool_call_observed=true`，`tool_call_count=16`，`generated_code_saved=true`，`answer_file_saved=true`，`schema_check.passed=true`，pytest 摘要为 `duplicate_key_count` 缺失 |
| retry-2 | `credit_risk_scoring_001` | `failure_type=code_execution_failed`，`llm_tool_call_observed=true`，`tool_call_count=10`，`generated_code_saved=true`，`answer_file_saved=false`，`schema_check.passed=false`，pytest 摘要为 `answer.json must exist` |

结论：两轮失败不是简单网络中断。证据是 4 条 task result 均 `api_called=true`，且均观察到工具调用。当前主要失败集中在模型生成代码或输出结构不稳定：有时未生成 `answer.json`，有时生成的 `answer.json` 顶层字段存在但内部 schema 不满足 pytest，例如 `duplicate_key_count`、`duplicate_keys`、`join_cardinality` 或 `data_quality` 内部结构不符合测试要求。不能写成真实 API 通过，也不能写“初步稳定”。

### 5.3 后续真实 API 验收建议

```bash
bash scripts/run_real_api_code_agent_benchmark.sh \
  configs/api/local/provider_chatanywhere.env \
  benchmarks/tasks/growth_campaign_audit_001

bash scripts/run_real_api_code_agent_benchmark.sh \
  configs/api/local/provider_chatanywhere.env \
  benchmarks/tasks/credit_risk_scoring_001
```

验收口径：

- 继续真实 API 测试前，应先收敛 prompt/task spec 或提供更明确的公开 schema 细节，尤其是 `duplicate_key_count`、`duplicate_keys`、`join_cardinality`、`data_quality` 内部结构。
- 按用户当前要求，后续每次真实 API 回归先跑 2 轮，避免耗时过长；需要稳定性结论时再扩展到 5 轮。
- 只有多轮结果中 `passed=true` 且无未分类失败，才写“通过”或“初步稳定”。
- 单次成功只能写“本次通过”。
- env 缺失、网络失败、模型未生成 `solve.py`、工具未调用、权限受限或 schema 不匹配，必须记录 `SKIP` 或明确 `failure_type`。
- 不允许硬编码答案、跳过 pytest、放宽 correctness 口径或伪造 tool call。

## 6. 版本同步

- README badge 已同步到 `v0.0.3`。
- `src/tablecodeagent/tracing/logger.py` 的 `TRACE_VERSION` 已同步到 `v0.0.3`。
- 架构文档已补充 `output_contract`、`schema_check`、pytest 型 validation 口径和信贷风险评分 workflow。
- `src/pyproject.toml` 中的 `version = "1.0.0"` 仍保持不变；这是 baseline package version，不等同于 TableCodeAgent 开发记录版本。

## 7. 风险与后续

- 当前仓库本地 `.venv` 已解决 `pluggy` 缺失和 `numpy/pandas` 异常；`.venv/` 已加入 `.gitignore`，不应提交虚拟环境内容。
- 真实 API 失败归因字段已经补齐；上传 env 后两轮真实 API 均已调用模型并观察到工具调用，但尚未通过 pytest。当前不应写成真实 API 通过或稳定。
- 真实 API 失败已从 Windows 编码/环境中断推进到模型输出结构问题；后续优先补强公开 schema、task spec、prompt 或 retry/self-check 策略，而不是放宽 validation。
- 曾短暂把 `benchmarks/results/` 加入 `.gitignore`，原因是 benchmark runner 会生成真实 API 或 SKIP 结果，而早前约束要求不要提交 benchmark 结果；本轮已按用户要求撤销该忽略规则，因此结果目录会重新出现在 `git status` 中。
- 信贷风险评分 fixture 是最小 workflow 验证样例，不代表生产风控模型，也不声明 SOTA、SFT、RL、RAG 或 Memory 增强能力。

## 8. 结论

`v0.0.3` 已实现 benchmark 输出契约、schema 自检、pytest 型 validation 口径修正、trace/result 字段补强、Windows 兼容性修复和信贷风险评分 workflow fixture。当前 Windows `.venv` 下已完成语法检查、项目单元/集成测试、营销增长 fixture 外部 pytest 和信贷风控 fixture 外部 pytest。真实 API 已使用用户指定 env 完成 2 轮重测：API 调用和工具调用链路可达，但 4 条任务结果均未通过，失败集中在模型生成代码或 `answer.json` 内部结构不满足 pytest。
