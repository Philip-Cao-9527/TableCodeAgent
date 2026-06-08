# TableCodeAgent v0.0.5 修复报告

日期：2026-06-08  
仓库：`D:\桌面\TableCodeAgent`  
版本说明：用户口径中的 `0.05` 对应本仓库本轮文档命名 `v0.0.5`。

## 本轮目标

本轮新增并闭环了财务运营 workflow、task contract、answer schema、deterministic 回归、skill 文档和真实 API benchmark 验证。

目标场景是 B2B 应收账款与现金回款运营，不再停留在单表聚合 demo，而是覆盖：

- invoices / payments / customers / disputes / adjustments / policy 多表读取
- 发票与回款匹配
- 账龄分桶
- 未核销现金
- 争议款、部分付款、超额付款、重复付款
- 币种不一致、负金额发票、缺失 due date、非 posted / future-dated receipt
- credit limit、PO 缺失、账期不匹配、ECL / provision matrix
- 客户级风险分层、运营动作建议与审计说明

## 外部业务依据

本轮按用户要求使用 `academic-web-search` 方向检索了实际 AR / cash application / ECL 业务口径，并把结论落到可验证 contract 与测试中：

- Oracle Receivables 文档说明收款应用会产生 unapplied / applied 状态、amount applied、cross-currency application 等记录。本轮据此设计 `unapplied_cash`、币种不一致回款和 receipt cutoff 口径。参考：<https://docs.oracle.com/en/cloud/saas/financials/25c/oadsr/ReceivableApplicationExtractPVO.html>
- SAP Help Portal 区分 partial payment 与 residual item，并说明 partial payment 下原始发票与付款都可能保留为 open items。本轮据此保留部分付款后的 open amount，并要求 `partial_payment` 单独标注。参考：<https://help.sap.com/docs/SAP_S4HANA_CLOUD/b978f98fc5884ff2aeb10c8fdeb8a43b/279bad94d6414e05aab0cacf42eb3803.html>
- IFRS 9 对 trade receivables 的 simplified approach / provision matrix 口径支持按账龄 bucket 估算 ECL。本轮只把它作为 benchmark 的 provision-matrix 计算口径，不声明为真实审计或会计结论。参考：<https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ifrs-9-financial-instruments.pdf>

## 关键改动

- 新增 workflow：[`src/tablecodeagent/workflows/finance_operations.py`](../../src/tablecodeagent/workflows/finance_operations.py)
- 新增 answer schema：[`src/tablecodeagent/benchmark/answer_models.py`](../../src/tablecodeagent/benchmark/answer_models.py)
- 新增 benchmark task：[`benchmarks/tasks/finance_operations_001/task.json`](../../benchmarks/tasks/finance_operations_001/task.json)
- 新增 task 数据：[`benchmarks/tasks/finance_operations_001/*.csv`](../../benchmarks/tasks/finance_operations_001/)
- 新增 task 断言：[`benchmarks/tasks/finance_operations_001/tests/test_solution.py`](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py)
- 新增模拟 Agent 测试：[`tests/test_integration/test_finance_operations_simulated_agent_outputs.py`](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py)
- 新增 workflow expected check：[`tests/test_integration/test_finance_operations_workflow_expected_check.py`](../../tests/test_integration/test_finance_operations_workflow_expected_check.py)
- 新增 skill 文档：[`./.tca/skills/finance-operations/SKILL.md`](../../.tca/skills/finance-operations/SKILL.md)
- 新增 skill 元数据：[`./.tca/skills/finance-operations/agents/agent.yaml`](../../.tca/skills/finance-operations/agents/agent.yaml)
- 更新架构说明：[`docs/reproduce/tablecodeagent_architecture.md`](tablecodeagent_architecture.md)
- 更新项目总览：[`README.md`](../../README.md)

## 业务契约

公开 contract 明确了：

- `invoice_id`、`payment_id` 去重口径
- posted / future-dated / voided 回款 cutoff
- invoice_id 优先匹配，未知或币种不一致计入 unapplied cash
- 部分/超额付款处理
- approved credit memo / write-off / chargeback 的会计口径
- disputed open amount 与 risk amount 的拆分
- `0-30`、`31-60`、`61-90`、`90+`、`missing_due_date` 的边界
- 缺失 due date、负金额、缺失 PO、term mismatch、信用额度超限、客户状态异常的输出方式
- 输出字段、枚举、小写约束、排序规则和金额精度

## 技能设计

新增了文档化 skill `finance-operations`，位置在 `.tca/skills/finance-operations/`。

边界如下：

- 描述通用财务运营分析步骤
- 不包含 expected answer
- 不包含项目 helper import 路径
- 不包含可直接复制的 solve.py
- 仅作为项目内文档/测试辅助资产，不代表 runtime 自动发现

## 本地验证

完整本地测试通过：

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

结果：`29 passed in 8.40s`

财务专项子集也通过：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_unit/test_real_api_code_agent_contract.py tests/test_unit/test_finance_operations_skill_contract.py tests/test_integration/test_finance_operations_workflow_expected_check.py tests/test_integration/test_finance_operations_simulated_agent_outputs.py tests/test_integration/test_sandbox_runs_fixed_solve_py.py -q
```

结果：`22 passed in 8.13s`

## 模拟 Agent 校验

已验证以下错误会被捕获：

- 账龄边界错误
- 部分/超额付款口径错误
- adjustment / allowance 口径错误
- 枚举大小写错误
- 缺失字段与类型错误
- `NaN` / `NaT` / `"nan"` 这类缺失值字符串化错误

这些用例均只在本地 deterministic / schema / pytest 层验证，不代表真实 LLM benchmark 通过。

## 真实 API 第 1 次

命令：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner --env configs/api/local/deepseek.env --task-dir benchmarks/tasks/finance_operations_001 --task-group v0.05-finance-ops-real-api-pass1-20260608
```

结果目录：

- [`benchmarks/results/real_api_code_agent/20260607-214925__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass1-20260608/`](../../benchmarks/results/real_api_code_agent/20260607-214925__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass1-20260608/)

关键字段：

- `api_called=true`
- `skipped=false`
- `benchmark_profile=no_helper`
- `helper_hints_exposed=false`
- `llm_tool_call_observed=true`
- `tool_call_count=15`
- `schema_check.passed=true`
- `run_python.exit_code=0`
- `pytest_exit_code=1`
- `failure_type=pytest_failed`
- `validation.passed=null`（pytest authoritative）

失败摘要：

- `missing_po_invoice_ids` 为空，但 task contract 期望 `INV-1006`

深入归因：

1. 真实 API 生成的 [`solve.py`](../../benchmarks/results/real_api_code_agent/20260607-214925__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass1-20260608/workspaces/finance_operations_001.real_api_code_agent/solve.py) 使用 `pd.read_csv(..., dtype=str)` 读取发票表。pandas 默认会把空 CSV 单元格解释为 `NaN`，即使指定 `dtype=str`，空 `po_number` 也可能在后续 `str(...)` 时变成字符串 `"nan"`。
2. 该代码的 PO 判断逻辑是 `if not str(row.get("po_number", "")).strip():`。对真实空值来说，`str(np.nan).strip()` 得到 `"nan"`，是非空字符串，因此没有给 `INV-1006` 添加 `missing_po`。
3. 同一个归一化问题也出现在 due date：[`answer.json`](../../benchmarks/results/real_api_code_agent/20260607-214925__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass1-20260608/workspaces/finance_operations_001.real_api_code_agent/answer.json) 中 `INV-1006.due_date` 输出为字符串 `"nan"`，而正确口径应是 JSON `null`。
4. pass1 的 Pydantic schema 仍然 `schema_check.passed=true`，原因是原 schema 只约束 `due_date` 为 `StrictStr | None`，没有拒绝 `"nan"` 这种 NaN-like 字符串；pytest 首先在 `data_quality.missing_po_invoice_ids` 断言处失败，因此报告只显示了第一个失败点。
5. 所以 pass1 不是 env、sandbox、API 权限或 runner 接线问题，也不能简单写成“模型漏了一个字段”。更准确的归因是：公开 contract 没有把 CSV 空值、pandas `NaN` / `NaT` 和字符串 `"nan"` 的缺失值归一化规则写得足够显式，schema 也没有阻止 `"nan"` 伪日期。

修复动作：

- 在 [`task.json`](../../benchmarks/tasks/finance_operations_001/task.json) 的 `finance_contract` 中新增 `missing_value_normalization`，明确 blank、null、pandas `NaN`/`NaT`、`"nan"`、`"NaT"`、`"None"`、`"null"` 都按缺失处理。
- 收紧 `aging_boundaries` 和 `terms_and_documentation`，明确缺失 due date 要输出 JSON `null`，PO 缺失要写入 `data_quality.missing_po_invoice_ids`、发票 `exception_tags` 和 `missing_po` exception row。
- 在 [`answer_models.py`](../../src/tablecodeagent/benchmark/answer_models.py) 给 `FinanceInvoiceReconciliationRow.due_date` 增加 validator，拒绝空字符串和 NaN-like 字符串。
- 在 [`tests/test_solution.py`](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py) 增加 `INV-1006.due_date is None`、`missing_po` 发票标签和 `missing_po` exception row 断言。
- 在 [`test_finance_operations_simulated_agent_outputs.py`](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py) 增加 `"nan"` due date 模拟 Agent 错误用例。
- 在 [`finance-operations` skill](../../.tca/skills/finance-operations/SKILL.md) 中同步缺失值归一化规则。

## 真实 API 第 2 次

第 1 次失败归因为公开 contract / schema 的缺失值归一化口径不够明确，已修复并重新通过完整本地测试后，运行第 2 次真实 API。

命令：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner --env configs/api/local/deepseek.env --task-dir benchmarks/tasks/finance_operations_001 --task-group v0.05-finance-ops-real-api-pass2-20260608
```

结果目录：

- [`benchmarks/results/real_api_code_agent/20260607-220543__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass2-20260608/`](../../benchmarks/results/real_api_code_agent/20260607-220543__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass2-20260608/)

关键字段：

- `api_called=true`
- `skipped=false`
- `benchmark_profile=no_helper`
- `helper_hints_exposed=false`
- `llm_tool_call_observed=true`
- `tool_call_count=15`
- `schema_check.passed=false`
- `run_python.exit_code=1`
- `pytest_exit_code=1`
- `failure_type=code_execution_failed`
- `validation.passed=false`

失败摘要：

- 没有生成 `answer.json`
- `run_python.stderr_summary=Traceback (most recent call last): KeyError: 'tables'`

深入归因：

1. pass2 的 [`solve.py`](../../benchmarks/results/real_api_code_agent/20260607-220543__model-deepseek-v4-flash__tasks-v0.05-finance-ops-real-api-pass2-20260608/workspaces/finance_operations_001.real_api_code_agent/solve.py) 已正确实现 `_is_missing()`，覆盖 blank、`NaN`、`NaT`、`"nan"` 等缺失值；这说明 pass1 的 contract 修复被模型注意到了。
2. 但 pass2 生成的 `_load()` 使用 `CFG["tables"][name]`，其中 `CFG = TASK["finance_config"]`。真实 task 的 `tables` 是 top-level 字段，不在 `finance_config` 内；因此代码启动时直接 `KeyError: 'tables'`，未进入业务计算，也未生成 `answer.json`。
3. 这是模型生成代码读取 task.json 路径错误，不是本地 deterministic workflow、Pydantic schema、sandbox、env 或 pytest 接线失败。公开 task.json 已有 top-level `tables`，runner 也把 task 原样复制进 workspace。
4. 由于第二次真实 API 后必须停止，本轮没有继续通过第三次 API 验证模型是否能同时修复路径读取和业务计算。

## 停止原因

本轮真实 API 共调用 2 次，已经达到用户设定上限。pass2 后无论结果如何都禁止第三次调用，因此停止真实 API。

## 风险与未验证项

- 第 2 次真实 API 仍失败，失败类型为 `code_execution_failed`，不是通过。
- pass2 未生成 `answer.json`，因此没有验证修复后的 `NaN` / missing PO 口径在真实模型输出中是否最终通过。
- Windows 下 `bash scripts/run_benchmark_smoke.sh` 仍不可用，报 WSL / bash 缺失提示；已用 PowerShell pytest 命令作为等价本地 smoke。
- `.tca/skills/finance-operations` 目前是文档化 skill 资产，不代表 runtime 已自动发现。
- 由于真实 API 调用已达 2 次，本轮不再继续 API 修复循环。
