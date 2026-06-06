# fix-report-v0.0.2-20260606

## 1. 本轮目标与范围

本轮目标版本为 `v0.0.2`，用于记录 TableCodeAgent 从最小表格工具闭环升级到 pandas backend、依赖管理、process-level light sandbox、营销增长三层 benchmark、trace 指标和规范化 skill 的过程。

本轮还完成了项目源码目录迁移：原 Python 主实现目录从 `python/` 调整为 `src/`。旧 TypeScript baseline 顶层 `src/*.ts` 已删除，当前 `src/` 作为 Python 包源码目录使用。

本轮范围：

1. 将 Python 包源码目录迁移为 `src/`，同步脚本、README、架构文档和 benchmark runner 的路径。
2. 将 `src/tablecodeagent/table_tools/core.py` 重构为 pandas backend，支持 CSV、XLSX、Feather、NPY、NPZ。
3. 新增 runtime dependency 管理与 process-level light sandbox。
4. 新增营销增长数据质量工具、固定 workflow 和三层 benchmark。
5. 新增 table context compression 与 analysis memory 的最小领域模块。
6. 规范 `.tca/skills/growth-campaign-audit/` skill 目录，删除冗余 `.tca/skills/growth_campaign_audit.md`。
7. 规范 README 文档头、功能亮点、本地验证和后续开发计划。

## 2. 改动文件清单

### 2.1 目录迁移与入口路径

- `src/`
- `scripts/run_table_tools_smoke.sh`
- `scripts/run_agent_table_tools_smoke.sh`
- `scripts/run_benchmark_smoke.sh`
- `scripts/run_demo_table_agent_smoke.sh`
- `src/tablecodeagent/benchmark/runner.py`

### 2.2 README 与文档

- `README.md`
- `docs/reproduce/2026-06-03_tablecodeagent_architecture.md`
- `docs/reproduce/2026-06-03_python_baseline_install.md`
- `docs/reproduce/2026-06-03_why_table_code_agent.md`
- `docs/reproduce/fix-report-v0.0.2-20260606.md`

### 2.3 Runtime、sandbox 与依赖

- `src/pyproject.toml`
- `src/tablecodeagent/runtime/dependency.py`
- `src/tablecodeagent/runtime/sandbox.py`

### 2.4 表格工具、质量检查与 Agent 接入

- `src/tablecodeagent/table_tools/core.py`
- `src/tablecodeagent/table_tools/quality.py`
- `src/tablecodeagent/agent_tools.py`
- `src/mini_claude/tools.py`

### 2.5 Workflow、context、memory、trace、benchmark

- `src/tablecodeagent/workflows/growth_campaign_audit.py`
- `src/tablecodeagent/context/table_context.py`
- `src/tablecodeagent/memory/analysis.py`
- `src/tablecodeagent/tracing/logger.py`
- `src/tablecodeagent/benchmark/runner.py`
- `benchmarks/tasks/growth_campaign_audit_001/`

### 2.6 Skill

- `.tca/skills/growth-campaign-audit/SKILL.md`
- `.tca/skills/growth-campaign-audit/agents/openai.yaml`

## 3. 关键修复内容

### 3.1 源码目录迁移为 `src/`

项目现在以 `src/` 作为 Python 包源码目录。运行脚本统一设置：

```bash
PYTHONPATH=src
```

editable install 入口同步调整为：

```bash
cd /root/workspace/TableCodeAgent/src
python -m pip install -e .
```

旧 `python/` 路径不再作为当前源码入口。历史 fix report 中保留的 `python/` 路径属于历史记录，不做回写修改。

### 3.2 pandas backend

`src/tablecodeagent/table_tools/core.py` 已从标准库 CSV / openpyxl 为主的实现升级为 pandas backend：

- `pd.read_csv`
- `pd.ExcelFile` / `pd.read_excel`
- `pd.read_feather`
- `np.load`
- `DataFrame.isna`
- `DataFrame.agg`
- `pd.to_numeric`

工具输出仍保持现有 JSON 协议，避免破坏 `load_table`、`profile_table`、`query_table` 和 Agent 工具 schema 的调用方式。

### 3.3 依赖管理与自动安装

新增 `src/tablecodeagent/runtime/dependency.py`：

- 强依赖：`pandas`、`numpy`、`openpyxl`。
- 格式依赖：`.feather` 需要 `pyarrow`。
- 测试依赖：`pytest`。
- LLM demo 依赖：`openai`、`anthropic`、`rich`。
- 每个 run 每个 package 最多 3 次安装尝试。
- 第 3 次尝试使用官方 PyPI：`https://pypi.org/simple`。
- 失败类型包括 `dependency_missing`、`dependency_install_failed`。

该机制不是 silent fallback；安装行为和失败原因会进入可观察结果。

### 3.4 process-level light sandbox

新增 `src/tablecodeagent/runtime/sandbox.py`：

- `run_python_in_sandbox`
- `run_tests_in_sandbox`
- `subprocess.run(shell=False)`
- 显式 `workspace_dir`
- 显式 `timeout_seconds`
- 显式 `max_output_chars`
- 捕获 `stdout` / `stderr`
- 超长输出设置 `output_truncated=true`
- 使用 env 白名单
- 拒绝 `.env`、`configs/api/local`、API key 文件和用户 home 敏感路径
- 返回结构化结果：`command`、`cwd`、`exit_code`、`stdout`、`stderr`、`timeout`、`duration_seconds`、`output_truncated`、`sandbox_policy`

该 sandbox 是 process-level light sandbox，不是 Docker、Firecracker、gVisor 级强安全隔离。

### 3.5 表格质量工具

新增 `src/tablecodeagent/table_tools/quality.py`，覆盖：

- `check_missing_values`
- `check_unique_key`
- `check_join_cardinality`
- `check_treatment_control_distribution`
- `check_group_balance`
- `calculate_smd`
- `check_subsidy_outliers`
- `check_time_window_alignment`
- `expected_warning_coverage`

这些工具服务于营销增长建模前置数据审计，不声明支持完整因果推断或智能定价建模。

### 3.6 营销增长 workflow 与三层 benchmark

新增 `src/tablecodeagent/workflows/growth_campaign_audit.py` 和 `benchmarks/tasks/growth_campaign_audit_001/`。

任务包含：

- `users.csv`
- `campaign_exposure.csv`
- `rewards.csv`
- `orders.csv`
- `task.json`
- `expected.json`
- `tests/test_solution.py`

benchmark runner 新增三层模式：

- `growth_l0_tools`：验证 pandas backend 和确定性质量工具。
- `growth_workflow`：运行固定营销增长审计 workflow，生成结构化报告并对照 `expected.json`。
- `sandbox_code_agent`：生成 `solve.py`，在 sandbox 中执行，生成 `answer.json`，再用 `pytest` / `expected.json` 校验。

该任务聚焦多表样本构造、join 膨胀、treatment/control 分布偏差、SMD、补贴极端值和时间窗口错配。

### 3.7 trace 与评测指标

`src/tablecodeagent/tracing/logger.py` 的 trace version 已更新为 `v0.0.2`。runner 增加或汇总以下指标：

- `code_execution_success_rate`
- `test_pass_rate`
- `validation_pass_rate`
- `tool_call_count`
- `generated_code_saved`
- `solve_py_runtime_seconds`
- `sandbox_timeout_count`
- `dependency_failure_count`
- `row_expansion_detected`
- `warning_recall`
- `expected_warning_coverage`
- `failure_type`

`warning_recall` 当前使用 `expected_required_warnings` 的字符串或标签覆盖率，不做复杂 NLP 评估。

### 3.8 README 与 skill 规范化

README 顶部新增居中文档头、badge、快捷锚点、功能亮点和后续开发计划，当前项目定位更接近标准开源 README。

新增规范化 skill 目录：

```text
.tca/skills/growth-campaign-audit/
├── SKILL.md
└── agents/openai.yaml
```

冗余的 `.tca/skills/growth_campaign_audit.md` 已删除。

## 4. 验收方式与结果

### 4.1 编译检查

执行：

```bash
cd /root/workspace/TableCodeAgent
python -m compileall -q src/tablecodeagent src/mini_claude/tools.py
```

结果：通过。

### 4.2 表格工具 smoke test

执行：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_table_tools_smoke.sh
```

结果：通过。demo 表格任务实际值为 `32.5`，答案校验通过。

### 4.3 Agent 工具注册 smoke test

执行：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_agent_table_tools_smoke.sh
```

结果：通过。`load_table`、`profile_table`、`query_table`、`validate_answer` 可通过 `mini_claude.tools.execute_tool()` 执行。

### 4.4 benchmark / trace / validation smoke test

执行：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_benchmark_smoke.sh
```

结果：通过。证据路径：

```text
benchmarks/runs/20260606-041838/results.jsonl
benchmarks/runs/20260606-041838/traces/
```

该 run 共记录 13 条非 API 结果，全部 `passed=true`，`failure_type=null`。

覆盖模式包括：

- `direct`
- `agent_tool_dispatch`
- `growth_l0_tools`
- `growth_workflow`
- `sandbox_code_agent`

### 4.5 真实 LLM API demo

执行：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_demo_table_agent_smoke.sh configs/api/local/provider_chatanywhere.env
```

结果：通过。证据路径：

```text
benchmarks/runs/20260606-041843/results.jsonl
benchmarks/runs/20260606-041843/traces/demo_table_001.optional_llm_agent.json
```

关键结果：

- `api_called=true`
- `llm_tool_call_observed=true`
- `tool_call_count=2`
- `validation.passed=true`
- `model_name=deepseek-v4-flash`

本轮真实 API 验证暴露并修复过三类问题：

1. 缺少 `anthropic` 依赖。
2. 默认镜像安装 `openai` 失败。
3. LLM 将 `filters` 以 JSON 字符串传入 `query_table`，导致工具参数解析失败。

对应修复：

1. 将 `openai`、`anthropic`、`rich` 纳入 LLM demo 依赖检查。
2. 第 3 次安装尝试切换到官方 PyPI。
3. `query_table` 增加 JSON 字符串 filters 兼容。

### 4.6 skill 格式校验

执行：

```bash
cd /root/workspace/TableCodeAgent
python /root/.codex/skills/.system/skill-creator/scripts/quick_validate.py .tca/skills/growth-campaign-audit
```

结果：通过，输出 `Skill is valid!`。

## 5. 版本同步清单

- README badge 和项目说明已同步到 `v0.0.2`。
- `src/tablecodeagent/tracing/logger.py` 的 `TRACE_VERSION` 已同步为 `v0.0.2`。
- 新增本报告：`docs/reproduce/fix-report-v0.0.2-20260606.md`。
- Python package metadata 仍保持 `src/pyproject.toml` 中的 `version = "1.0.0"`，这是 baseline package version，不等同于 TableCodeAgent 开发记录版本。

## 6. 风险与备注

- `sandbox_code_agent` 当前验证的是 runner 生成的 `solve.py` scaffold 与 sandbox / pytest 闭环，不等同于完整 LLM 自主生成、执行、根据 stderr 多轮修复复杂代码。
- process-level light sandbox 只提供工作目录、env 白名单、敏感路径拒绝、timeout 和输出截断等边界，不是生产级强安全隔离。
- pandas backend 可能改变缺失值、类型推断、日期解析、浮点统计和 Excel 读取口径，因此必须继续用现有 smoke、L0/L1/L2 benchmark 回归兜底。
- 自动安装依赖是可观察、有限重试机制，不能被包装成总能恢复的依赖治理能力。
- `.tca/skills/` 已规范化，但 `mini_claude` 原生 skill discovery 仍以 baseline 机制为准；后续如需运行时自动发现 `.tca` skill，需要单独接入。
- 本轮不声明已支持 uplift 建模、PSM/IPW 训练、因果效应估计、智能定价模型、业务投放策略自动化或完整企业级数据分析平台。
- 工作区中存在 `en/` 文档删除项，属于本轮未处理的既有 dirty 状态；本报告不将其计入本轮功能范围。

## 7. 结论

`v0.0.2` 已把 TableCodeAgent 从最小表格工具闭环推进到可验证的 pandas backend、runtime dependency、light sandbox、营销增长 L0/L1/L2 benchmark、trace 指标和真实 API demo 闭环。

下一阶段建议优先继续补齐更真实的 L2 Coding Agent 自主代码生成与多轮修复能力，再扩展信贷风控、财务运营和表格问答 benchmark。
