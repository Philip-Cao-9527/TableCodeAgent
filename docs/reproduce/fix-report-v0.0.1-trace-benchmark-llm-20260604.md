# fix-report-v0.0.1-trace-benchmark-llm-20260604

## 1. 本轮目标与范围

本轮继续沿用 `v0.0.1`，完成两层闭环：

1. 第一阶段：trace logger、benchmark runner、真实 LLM Agent 行为验证。
2. 第二阶段：Excel / 多表 / 多 header / 合并单元格的最小可验证支持。

本轮明确不做：

- 不修改 package version。
- 不创建 `v0.0.2`。
- 不提交 git commit。
- 不修改 `configs/api/local/provider_chatanywhere.env`。
- 不打印、读取或写入 API key。
- 不引入 `pandas`、`duckdb`、`pyarrow`。
- 不实现 WikiTQ / TabMWP / FinQA / TAT-QA 转换。

## 2. 改动文件清单

- `python/tablecodeagent/tracing/logger.py`
- `python/tablecodeagent/benchmark/__init__.py`
- `python/tablecodeagent/benchmark/runner.py`
- `python/tablecodeagent/table_tools/core.py`
- `python/tablecodeagent/agent_tools.py`
- `python/mini_claude/agent.py`
- `python/pyproject.toml`
- `scripts/run_benchmark_smoke.sh`
- `scripts/run_demo_table_agent_smoke.sh`
- `benchmarks/tasks/excel_table_001/*`
- `benchmarks/tasks/multi_table_001/*`
- `benchmarks/tasks/multi_header_001/*`
- `benchmarks/tasks/merged_cell_001/*`
- `.gitignore`
- `README.md`
- `docs/reproduce/fix-report-v0.0.1-trace-benchmark-llm-20260604.md`

## 3. 关键实现内容

### 3.1 trace logger 与 benchmark runner

新增 `tablecodeagent.tracing.logger`，写入：

```text
benchmarks/runs/<run_id>/results.jsonl
benchmarks/runs/<run_id>/traces/<task_id>.<mode>.json
```

trace / result 记录：

- `task_id`
- `mode`
- `provider`
- `model_name`
- `api_called`
- `skipped`
- `llm_tool_call_observed`
- `tool_call_count`
- `final_answer`
- `expected_answer`
- `validation.passed`
- `failure_type`
- `elapsed_ms`

`tablecodeagent.benchmark.runner` 支持：

- `direct`：不调用 API，直接执行表格工具函数和答案校验。
- `agent_tool_dispatch`：不调用 API，通过 `mini_claude.tools.execute_tool()` 分发工具调用。
- `optional_llm_agent`：调用 OpenAI-compatible API，验证真实模型是否发起表格工具调用并通过 `validate_answer`。

### 3.2 真实 LLM tool call 观测

`mini_claude.agent.Agent` 新增默认关闭的 `trace_callback`。benchmark runner 显式传入 callback 时，可以记录真实模型触发的表格工具调用。

`optional_llm_agent` 的 `passed=true` 条件：

- `api_called=true`
- `skipped=false`
- `llm_tool_call_observed=true`
- `tool_call_count > 0`
- `validation.passed=true`

失败分类包括：

- `llm_tool_call_missing`
- `llm_runtime_error`
- `validation_failed`
- `tool_error`
- `table_read_error`

### 3.3 Excel / 多表 / 多 header / 合并单元格支持

`tablecodeagent.table_tools.core` 增加最小表格读取与查询能力：

- CSV 与 `.xlsx` 统一读取。
- `.xlsx` 支持 `sheet_name`。
- 多 header 支持 `header_rows`，通过 `__` 规范化多行表头，例如 `sales__revenue`。
- 合并单元格支持 `fill_merged_cells=true`，读取前用左上角值展开合并区域。
- 新增 `query_multi_table`，支持两表 inner join 后进行 `count/sum/mean/min/max` 聚合。

`tablecodeagent.agent_tools` 同步更新：

- `load_table` / `profile_table` / `query_table` 增加 `sheet_name`、`header_rows`、`fill_merged_cells`。
- 新增 `query_multi_table` 工具 schema 和 adapter。

依赖变化：

- 新增 `openpyxl>=3.1.0`，用于 `.xlsx` 读取。
- 未引入 `pandas`、`duckdb`、`pyarrow`。
- 未修改 package version。

## 4. 新增 benchmark 任务

新增 4 个任务：

- `benchmarks/tasks/excel_table_001`
  - 读取 `data.xlsx` 的 `Sales` sheet。
  - 计算 `region == North` 的 `revenue` 总和。
  - 标准答案：`32.5`。

- `benchmarks/tasks/multi_table_001`
  - 读取 `orders.csv` 与 `regions.csv`。
  - 按 `region_id` join。
  - 计算 `regions.region == North` 的 `orders.revenue` 总和。
  - 标准答案：`32.5`。

- `benchmarks/tasks/multi_header_001`
  - 读取两行 header CSV。
  - 使用 `header_rows=2` 将列名规范化为 `sales__revenue`。
  - 计算 `region == North` 的 `sales__revenue` 总和。
  - 标准答案：`32.5`。

- `benchmarks/tasks/merged_cell_001`
  - 读取含合并单元格的 `data.xlsx`。
  - 使用 `fill_merged_cells=true` 展开合并区域。
  - 计算 `region == North` 的 `revenue` 总和。
  - 标准答案：`32.5`。

## 5. 验收方式与结果

### 5.1 编译检查

命令：

```bash
cd /root/workspace/TableCodeAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
python -m compileall -q python/tablecodeagent python/mini_claude/agent.py
```

结果：通过，无输出。

### 5.2 表格工具 smoke test

命令：

```bash
cd /root/workspace/TableCodeAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
bash scripts/run_table_tools_smoke.sh
```

结果要点：

```text
actual: {'value': 32.5, ...}
validation: {'passed': True, 'actual': 32.5, 'expected': 32.5, 'diff': 0.0}
```

结论：已验证基础表格工具函数。该测试不调用 API。

### 5.3 Agent 工具分发 smoke test

命令：

```bash
cd /root/workspace/TableCodeAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
bash scripts/run_agent_table_tools_smoke.sh
```

结果要点：

```text
table tool schemas: ['load_table', 'profile_table', 'query_table', 'validate_answer']
validation: {'passed': True, 'actual': 32.5, 'expected': 32.5, 'diff': 0.0}
```

结论：已验证 `execute_tool()` 分发路径。该测试不调用 API。

### 5.4 5 个任务的 direct / agent_tool_dispatch benchmark

命令：

```bash
cd /root/workspace/TableCodeAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
bash scripts/run_benchmark_smoke.sh
```

结果路径：

```text
benchmarks/runs/20260603-170510/results.jsonl
benchmarks/runs/20260603-170510/traces/
```

结果摘要：

```text
demo_table_001 direct passed=True actual=32.5
demo_table_001 agent_tool_dispatch passed=True actual=32.5
excel_table_001 direct passed=True actual=32.5
excel_table_001 agent_tool_dispatch passed=True actual=32.5
merged_cell_001 direct passed=True actual=32.5
merged_cell_001 agent_tool_dispatch passed=True actual=32.5
multi_header_001 direct passed=True actual=32.5
multi_header_001 agent_tool_dispatch passed=True actual=32.5
multi_table_001 direct passed=True actual=32.5
multi_table_001 agent_tool_dispatch passed=True actual=32.5
```

结论：4 个新增任务均已跑通 `direct` 和 `agent_tool_dispatch`，并写入 `results.jsonl` 与单任务 trace JSON。

### 5.5 新任务 optional_llm_agent 验证

命令：

```bash
cd /root/workspace/TableCodeAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
bash scripts/run_demo_table_agent_smoke.sh \
  configs/api/local/provider_chatanywhere.env \
  benchmarks/tasks/excel_table_001
```

说明：该命令调用 API；本轮没有运行 `scripts/run_openai_compatible_smoke.sh configs/api/local/provider_chatanywhere.env`。

结果路径：

```text
benchmarks/runs/20260603-170636/results.jsonl
benchmarks/runs/20260603-170636/traces/excel_table_001.optional_llm_agent.json
```

结果要点：

```json
{
  "task_id": "excel_table_001",
  "mode": "optional_llm_agent",
  "provider": "provider_chatanywhere",
  "model_name": "deepseek-v4-flash",
  "api_called": true,
  "skipped": false,
  "llm_tool_call_observed": true,
  "tool_call_count": 3,
  "actual": 32.5,
  "expected": 32.5,
  "passed": true,
  "failure_type": null
}
```

真实工具调用证据：

- `load_table`
- `query_table`
- `validate_answer`

结论：已验证真实 LLM Agent 在新增 Excel 任务上主动调用表格工具，并通过答案校验。

## 6. 版本与提交策略

- 继续沿用 `v0.0.1`。
- 不创建 `v0.0.2`。
- 不修改 package version。
- 不 git commit。
- benchmark 输出位于 `benchmarks/runs/`，已通过 `.gitignore` 忽略。

## 7. 风险与备注

- 当前 `.xlsx` 支持是最小读取能力，不是完整 Excel 公式/样式/透视表引擎。
- 当前多表只支持两个表的 inner join，不支持复杂 join plan 或自动主键推断。
- 当前多 header 采用 `__` 拼接规范化，复杂跨层表头仍需更多任务验证。
- 当前合并单元格展开采用左上角值填充合并区域，不代表所有业务报表口径。
- 真实 LLM 行为受 provider、模型版本、API 状态和工具调用策略影响；本报告只记录本次真实跑通结果。

## 8. 结论

本轮完成了 TableCodeAgent v0.0.1 第二阶段的最小可验证闭环：

- 已实现 Excel / `.xlsx` 读取。
- 已实现两表 join 聚合。
- 已实现多 header 规范化。
- 已实现合并单元格展开。
- 已新增 4 个 benchmark 任务。
- 4 个新增任务均跑通 `direct` 和 `agent_tool_dispatch`。
- 新增 Excel 任务跑通 `optional_llm_agent`，真实模型调用工具并通过 `validate_answer`。
