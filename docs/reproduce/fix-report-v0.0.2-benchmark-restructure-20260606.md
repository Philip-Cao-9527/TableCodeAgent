# fix-report-v0.0.2-benchmark-restructure-20260606

## 1. 本轮问题 / 目标与范围

本轮不修改版本号，目标是重构 benchmark 口径、结果目录和测试架构：

- 将非 API 检查迁移到 `tests/`，作为项目代码测试。
- 将真实 Agent benchmark 收敛为 `real_api_code_agent`。
- 将新 benchmark 输出目录从 `benchmarks/runs/` 改为 `benchmarks/results/`。
- 删除旧 `src/tablecodeagent/benchmark/runner.py`，不保留兼容 wrapper。

本轮不声明 TableCodeAgent 已完成 SFT、RL、RAG、Memory 增强或 SOTA 能力。

## 2. 改动文件清单

- [benchmark_runner.py](../../src/tablecodeagent/benchmark/benchmark_runner.py)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py)
- [logger.py](../../src/tablecodeagent/tracing/logger.py)
- [dependency.py](../../src/tablecodeagent/runtime/dependency.py)
- [benchmark/__init__.py](../../src/tablecodeagent/benchmark/__init__.py)
- [tests/test_unit/](../../tests/test_unit/)
- [tests/test_integration/](../../tests/test_integration/)
- [run_benchmark_smoke.sh](../../scripts/run_benchmark_smoke.sh)
- [run_real_api_code_agent_benchmark.sh](../../scripts/run_real_api_code_agent_benchmark.sh)
- [README.md](../../README.md)
- [.codex/AGENTS.md](../../.codex/AGENTS.md)
- [.gitignore](../../.gitignore)

删除：

- `src/tablecodeagent/benchmark/runner.py`
- `scripts/run_demo_table_agent_smoke.sh`

## 3. 关键修复内容

- `direct`、`agent_tool_dispatch`、`growth_l0_tools`、`growth_workflow`、`sandbox_code_agent` 已从 benchmark 口径迁移为 pytest 单元测试或集成测试。
- `optional_llm_agent` 不再作为独立 benchmark；真实 API 能力由 `real_api_code_agent` 承担。
- `benchmark_runner.py` 只调度真实 API benchmark，输出到：

```text
benchmarks/results/real_api_code_agent/<YYYYMMDD-HHMMSS>__model-<model_name>__tasks-<task_id_or_group>/
```

- 每个真实 benchmark 结果目录应包含 `results.jsonl`、`summary.json`、`traces/`、`workspaces/`。
- `real_api_code_agent` 在模型生成和执行阶段不提供 `expected.json`；`expected.json` 仅在外部 pytest 或 validator 阶段用于评测。
- `code_generation_source=llm_generated` 只用于真实 API 生成的 `solve.py`；固定模板只出现在 `tests/test_integration/test_sandbox_runs_fixed_solve_py.py`。

## 4. 验证命令

项目代码测试：

```bash
cd /root/workspace/TableCodeAgent
PYTHONPATH=src pytest tests/test_unit tests/test_integration
```

结果：`7 passed in 3.68s`。

语法检查：

```bash
cd /root/workspace/TableCodeAgent
PYTHONPATH=src python -m compileall -q src/tablecodeagent tests
```

结果：通过，无输出。

缺 API env 的失败可观测性验证：

```bash
cd /root/workspace/TableCodeAgent
PYTHONPATH=src python -m tablecodeagent.benchmark.benchmark_runner \
  --env configs/api/local/nonexistent.env \
  --task-dir benchmarks/tasks/demo_table_001
```

结果目录：

- [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122440__model-unknown__tasks-demo_table_001/results.jsonl)
- [summary.json](../../benchmarks/results/real_api_code_agent/20260606-122440__model-unknown__tasks-demo_table_001/summary.json)
- [demo_table_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260606-122440__model-unknown__tasks-demo_table_001/traces/demo_table_001.real_api_code_agent.json)

关键字段：

- `api_called=false`
- `skipped=true`
- `failure_type=api_env_missing`
- `generated_code_saved=false`

真实 API benchmark：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_real_api_code_agent_benchmark.sh \
  configs/api/local/provider_chatanywhere.env \
  benchmarks/tasks/growth_campaign_audit_001
```

结果目录：

- [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl)
- [summary.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json)
- [growth_campaign_audit_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.real_api_code_agent.json)
- [growth_campaign_audit_001.expected.json.for_external_check](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.expected.json.for_external_check)
- [solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)
- [answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)
- [expected.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/expected.json)
- [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py)

本次真实 API 已调用并生成代码，但外部 `pytest` 校验失败，不能写成通过。

关键字段：

- `api_called=true`
- `skipped=false`
- `llm_tool_call_observed=true`
- `tool_call_count=19`
- `generated_code_saved=true`
- `code_generation_source=llm_generated`
- `code_execution_success_rate=1.0`
- `test_pass_rate=0.0`
- `validation_pass_rate=1.0`
- `failure_type=pytest_failed`

失败原因不能只写成“缺少 required keys”。从现有结果链条可以确认：

1. [solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py) 已由真实 API 生成，`results.jsonl` 中 `generated_code_saved=true`、`code_generation_source=llm_generated`。
2. [answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json) 已落盘，`results.jsonl` 中 `code_execution_success_rate=1.0`，说明 sandbox 执行成功。
3. sandbox 执行成功不等于任务通过；同一条 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl) 记录同时给出 `test_pass_rate=0.0`、`failure_type=pytest_failed`。
4. 外部校验要求来自 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py)。该测试要求 `answer.json` 顶层至少包含 `row_counts`、`join_cardinality`、`group_distribution`、`smd_summary`、`outlier_summary`、`time_window_alignment`、`warnings`、`how_to_do_differently`。
5. 当前 [answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json) 顶层只有 `task_id` 和 `audit_results`，没有上述 required keys，因此不能写成通过。

补充说明：`validation_pass_rate=1.0` 只说明结果目录里存在可读取的 `answer.json`，不代表外部 `pytest` 已通过；是否通过仍以 `test_pass_rate` 和 `failure_type` 为准。

可能解决方案：

1. 最直接的修法是把 `solve.py` 的输出契约改对，让它生成的 `answer.json` 顶层字段与 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py) 要求一致，而不是只输出 `task_id` 和 `audit_results`。
2. 如果 benchmark 设计允许模型参考任务级测试文件，可以在 prompt 或 workflow 中明确提醒先核对 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py) 的 required keys，再写 `answer.json`，避免“内容有了、结构错了”的失败。
3. 如果 benchmark 不希望模型读取测试文件，就应把答案 schema 以更稳定的方式公开给模型，例如写进 [task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json) 或 prompt，避免模型只能猜输出结构。
4. 可以在 sandbox 执行成功后、外部 pytest 前增加一层轻量 schema 自检，只检查顶层必填字段是否存在；缺字段时应明确记录为结构不匹配，而不是等到最终 pytest 才暴露。
5. 当前失败本质上是“输出格式契约不匹配”，不是“模型完全不会做审计逻辑”，所以修复优先级应先放在输出结构对齐，再考虑审计内容细节优化。

如果 API env、网络或依赖不可用，必须记录为 `SKIP` 或失败，不能写成通过。

## 5. 结果路径记录要求

后续真实 API benchmark 的 fix-report 必须记录：

- `result_dir`：结果目录见 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl) 与 [summary.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json)
- `trace_path`：[growth_campaign_audit_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.real_api_code_agent.json)
- `workspace_path`：workspace 内关键文件见 [solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)、[answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)、[expected.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/expected.json)
- `generated_code_path`：[solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)
- `answer_path`：[answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)
- `summary.json`：[summary.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json)
- `results.jsonl`：[results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl)

并明确说明 `solve.py` 是否由 LLM 生成，以及是否读取了 `expected.json`。

本次 `solve.py` 由 LLM 生成。按源码 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py) 与当前结果目录状态核对：

- 模型生成阶段不会读取 `expected.json`。
- `expected.json` 的外部校验副本保存在 [growth_campaign_audit_001.expected.json.for_external_check](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.expected.json.for_external_check)。
- 当前保留结果中，workspace 里也存在 [expected.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/expected.json)，供外部 `pytest` 读取。
- 因此按当前真实文件状态，不能把最终结果写成“只能在 traces 中找到 `expected.json`”。

## 6. 关键文件作用、生成代码与质量结论

关键代码文件：

- [benchmark_runner.py](../../src/tablecodeagent/benchmark/benchmark_runner.py)：真实 API benchmark 总调度器，负责解析参数、创建 `benchmarks/results/...` 结果目录、逐任务调用 `real_api_code_agent`、写 `summary.json`。
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py)：真实 API code agent 流程，负责隐藏 `expected.json`、调用 LLM、保存 `solve.py`、sandbox 执行、恢复外部校验文件并记录 trace。
- [logger.py](../../src/tablecodeagent/tracing/logger.py)：负责语义化结果目录、trace、`results.jsonl` 结果字段。
- [dependency.py](../../src/tablecodeagent/runtime/dependency.py)：负责依赖 preflight，包含 LLM 和 pytest 依赖。

关键测试文件：

- [test_table_query_and_validate.py](../../tests/test_unit/test_table_query_and_validate.py)：承接旧 `direct` 的项目代码测试价值。
- [test_tool_registration_and_routing.py](../../tests/test_unit/test_tool_registration_and_routing.py)：承接旧 `agent_tool_dispatch` 的工具注册与 routing 测试价值。
- [test_growth_quality_functions.py](../../tests/test_unit/test_growth_quality_functions.py)：承接旧 `growth_l0_tools` 的确定性质量函数测试价值。
- [test_growth_full_workflow_expected_check.py](../../tests/test_integration/test_growth_full_workflow_expected_check.py)：承接旧 `growth_workflow` 的固定 workflow 集成测试价值。
- [test_sandbox_runs_fixed_solve_py.py](../../tests/test_integration/test_sandbox_runs_fixed_solve_py.py)：承接旧 `sandbox_code_agent` 的 fixed `solve.py`、sandbox、pytest、`answer.json` 基础设施测试价值。

任务输入与外部校验文件：

- [task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json)：真实 benchmark 输入任务。
- [expected.json](../../benchmarks/tasks/growth_campaign_audit_001/expected.json)：外部 validator / pytest 期望，不提供给模型生成代码阶段。
- [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py)：任务级 pytest 校验脚本。

本次真实 API benchmark 生成的代码文件在 [solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)。它位于结果目录下的 workspace，来源是 `code_generation_source=llm_generated`，不是 runner 固定模板。

本次真实 API benchmark 的结果文件分别在：

- 汇总结果：[results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/results.jsonl)
- 单次汇总：[summary.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/summary.json)
- 执行轨迹：[growth_campaign_audit_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.real_api_code_agent.json)
- 模型生成代码：[solve.py](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/solve.py)
- 模型输出答案：[answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)
- 外部 pytest 读取的期望文件：[expected.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/expected.json)
- 外部核对保留副本：[growth_campaign_audit_001.expected.json.for_external_check](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/traces/growth_campaign_audit_001.expected.json.for_external_check)

这些文件的用途分别是：`results.jsonl` 记录逐任务结果字段，`summary.json` 汇总单次运行，trace 保存 API 与工具轨迹，`solve.py` 是模型生成代码，`answer.json` 是 sandbox 执行产物，workspace 内 `expected.json` 与任务侧 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py) 配合完成外部 `pytest` 校验。

代码质量结论：不能写成通过。依据是 `code_execution_success_rate=1.0`，说明 `solve.py` 能执行并生成 [answer.json](../../benchmarks/results/real_api_code_agent/20260606-122922__model-deepseek-v4-flash__tasks-growth_campaign_audit_001/workspaces/growth_campaign_audit_001.real_api_code_agent/answer.json)；但 `test_pass_rate=0.0` 且 `failure_type=pytest_failed`，说明输出结构不满足 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py) 的 required keys，因此只能记录为真实 API 代码生成失败案例。

## 7. 未验证项、SKIP 项与原因

- 缺 API env 验证已覆盖：`api_called=false`、`skipped=true`、`failure_type=api_env_missing`，对应证据文件为 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260606-122440__model-unknown__tasks-demo_table_001/results.jsonl)、[summary.json](../../benchmarks/results/real_api_code_agent/20260606-122440__model-unknown__tasks-demo_table_001/summary.json)、[demo_table_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260606-122440__model-unknown__tasks-demo_table_001/traces/demo_table_001.real_api_code_agent.json)。
- 真实 API benchmark 已调用 API，但最终不是通过项：`failure_type=pytest_failed`。
- 本报告不声明 `real_api_code_agent` 已达到稳定生产级能力；当前证据只能说明入口、路径、代码保存、sandbox 执行、trace 写出和失败归因已经可观测。
- 本报告不修改版本号。

## 8. 风险与备注

- `tests/` 只能证明项目代码本身没有明显回归，不能证明真实 Agent 能力。
- 真实 benchmark 只有在 API 调用、LLM 生成 `solve.py`、sandbox 执行、pytest/validator 校验和 trace 写出后，才能写成已验证。
- 历史 `benchmarks/runs/...` 路径不作为新结果路径模板，仅作为旧报告历史证据保留。
