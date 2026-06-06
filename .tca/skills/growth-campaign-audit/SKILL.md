---
name: growth-campaign-audit
description: TableCodeAgent 营销增长活动表格审计指导。需要设计、实现、审核或运行 campaign exposure、rewards、users、orders 等建模前审计时使用；涉及 treatment/control 检查、join expansion、group balance、SMD、subsidy outliers、time-window alignment、warnings、how-to-do-differently 时触发。不用于声明 uplift modeling、PSM/IPW、因果效应估计或智能投放策略已经实现。
---

# 营销活动审计

## 适用范围

本 skill 用作营销增长数据建模前审计的流程指导和审核标准。它只提供方法、边界和检查顺序；确定性计算应放在项目代码中，不要写进 skill 正文。

本 skill 不声明支持 uplift modeling、PSM/IPW training、causal effect estimation、intelligent pricing models、automatic campaign strategy generation 或 enterprise BI platform。

## 执行步骤

1. 识别输入表和关键键：
   - `users`：用户属性与历史行为。
   - `campaign_exposure`：活动分组与 treatment/control 曝光记录。
   - `rewards`：补贴或奖励记录。
   - `orders`：转化与 GMV 证据。

2. 在任何建模解释之前检查表质量：
   - 按列统计缺失值与缺失率。
   - 检查业务键唯一性，尤其是 `user_id + campaign_window` 这类 rewards 侧关键键。
   - 检查重复记录，以及重复是否影响行数、补贴总额或转化结果。

3. 检查样本构造：
   - 检查 `campaign_exposure` 与 `rewards` 之间的 join cardinality。
   - 检查 join 后的 `row_expansion_ratio`。
   - 判断 join 风险是否为 `one_to_many`、`many_to_one` 或 `many_to_many`。

4. 检查 treatment/control 可比性：
   - 检查 treatment/control 样本数与 minority-to-majority ratio。
   - 检查关键协变量平衡性，例如 `historical_orders_30d`、`historical_gmv_30d`、`active_days_30d`、`user_level`。
   - numeric covariates 使用 SMD；categorical covariates 使用分布差异。
   - overlap 和 extreme weights 只能作为审计告警，除非已有确定性 tool/workflow 实现。

5. 检查业务时序和激励：
   - 检查 `subsidy_amount` outliers 或 extreme values。
   - `order_time` 是否落在 `campaign_window` 内。
   - 转化时间窗是否匹配活动时间窗。

6. 输出结构化审计结果：
   - `data_issue`：已观察到的数据质量问题。
   - `blocking_issue`：会让下游估计不安全的问题。
   - `warning_issue`：需要审核但不一定阻断审计的风险。
   - `how_to_do_differently`：后续运行的具体改进动作。

## 边界与注意事项

- 不要把原始的 treatment/control `conversion-rate` 差值直接当作 causal effect。
- 不要静默执行 `drop_duplicates`。
- 先报告重复占比和受影响样本；只有确认业务规则后才能去重。
- 不要把 `join expansion` 隐藏成 `validation failure` 或 `empty data`。
- runtime 支持时，应在 trace 或 benchmark output 中记录重复键、行扩张、时间窗错配和异常值证据。
- 如果依赖缺失、env 缺失、API 未实际调用、工具未触发或验证提前结束，必须写成失败或 `SKIP`，不能写成通过。

## 输入输出约定

- 输入通常来自 `benchmarks/tasks/<task_id>/task.json` 以及 `users`、`campaign_exposure`、`rewards`、`orders` 等表格文件。
- 输出应是结构化审计结果，并保留 `warnings`、`validation`、`how_to_do_differently` 等可审查字段。
- 如果运行真实 benchmark，应记录 `result_dir`、`trace_path`、`workspace_path`、`generated_code_path` 和 `answer_path`。

## 证据与验证要求

- 确定性检查应由 `tests/`、workflow 或 benchmark result 提供证据。
- 真实 API benchmark 只有在 `api_called=true`、模型生成代码、sandbox 执行、pytest/validator 校验和 trace 写出后，才能写成已验证。
- `SKIP`、dependency missing、env missing、未实际调用 API 或未触发关键工具调用，必须显式记录原因。

## TableCodeAgent 映射

- 确定性检查应放在 `src/tablecodeagent/table_tools/quality.py`。
- 固定多步编排应放在 `src/tablecodeagent/workflows/`。
- benchmark 任务与期望输出应放在 `benchmarks/tasks/`。
- 本 skill 只用于说明、审核标准和工作流约束，不替代项目代码实现。
