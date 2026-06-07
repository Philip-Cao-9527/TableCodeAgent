---
name: credit-risk-scoring
description: TableCodeAgent 信贷风控样本处理与评分 workflow 指导。需要设计、实现、审核或运行贷前申请表、贷后泄漏字段、标签窗口、重复申请、客户唯一性、缺失/异常/字段类型、规则卡评分和 no-helper benchmark 时使用；不用于声明生产风控模型、SOTA、SFT、RL、RAG 或 Memory 增强已经实现。
---

# 信贷风控样本处理

## 适用范围

本 skill 用作信贷风险评分 benchmark 场景和风控数据处理 workflow 的流程指导。它只描述检查顺序、业务边界和验证要求；确定性计算应放在 `src/tablecodeagent/workflows/` 或相关表格工具中。

本 skill 不声明支持生产风控模型、自动授信审批、真实监管合规审计、SOTA 建模、SFT、RL、RAG 或 Memory 增强。

## 不适用范围

- 不用于直接给真实用户做授信或拒贷决策。
- 不用于把固定规则卡包装成已训练模型。
- 不用于替代模型训练、验证集评估、上线监控、公平性审计或合规审批。
- 不用于给真实 API benchmark 暴露 workflow helper 或 `build_*_report()`。

## 执行步骤

1. 识别输入表和字段边界：
   - 申请主键通常是 `application_id`。
   - 客户主键通常是 `user_id`。
   - 贷前时间字段通常是 `application_time`、`feature_window_start`、`feature_cutoff_date`。
   - 标签窗口通常由 `label_window_start`、`label_window_end` 和 `default_90d` 描述。
   - 贷后或泄漏字段如 `post_loan_collection_calls`、`post_loan_dpd_max` 不能作为贷前特征。

2. 先做数据质量检查：
   - 检查必需字段是否存在。
   - 检查缺失值、空字符串、字段类型异常。
   - 检查 `application_id` 是否唯一。
   - 检查同一 `user_id` 是否多次申请，并明确这不是自动删除理由。
   - 检查年龄、收入、贷款金额、信用分等字段的异常值或不可解析值。

3. 检查贷前/贷后隔离：
   - `default_90d` 是标签，不是特征。
   - 贷后催收、贷后 DPD、还款表现等字段必须进入 `excluded_columns`。
   - 每个排除字段必须给出 `exclusion_reasons`。

4. 检查时间窗和标签窗口：
   - 特征只能来自 `feature_cutoff_date` 及以前。
   - 标签窗口必须晚于申请时点，并明确窗口长度。
   - 如果任务没有真实训练/验证切分，只能写成 workflow fixture，不能写成生产建模。

5. 输出风险分层和解释：
   - 可使用可复现规则卡或轻量规则生成 `risk_score` 和 `risk_band`。
   - 输出必须说明该评分不代表生产模型。
   - 高风险样本应触发人工复核或业务告警字段。

6. 输出结构化结果：
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

## 输入输出约定

- 输入通常来自 `benchmarks/tasks/credit_risk_scoring_001/task.json` 和 `applications.csv`。
- 真实 LLM Agent benchmark 只能看到 task、数据文件、允许库、业务目标和公开输出 schema。
- 真实 LLM Agent benchmark 不允许看到 `expected.json`、workflow helper import 路径或 `build_credit_risk_scoring_report()`。
- 输出必须落盘为 `answer.json`，并通过 Pydantic schema、pytest 和 trace 共同校验。

## 证据与验证要求

- 内部 workflow helper 只能用作 unit / integration / smoke / regression 测试。
- 真实 API benchmark 必须记录 `benchmark_profile=no_helper`、`helper_hints_exposed=false`、`api_called`、`skipped`、`failure_type`、`generated_code_path`、`answer_path`、`run_python.exit_code`、`pytest_exit_code` 和 `schema_check.errors`。
- `SKIP`、env 缺失、API 失败、schema 不匹配、pytest 失败或模型未生成代码，必须按真实失败写入报告，不能伪装通过。

## 注意事项

- 不要静默 drop duplicates。
- 不要把贷后字段、标签字段或人工催收字段用作贷前特征。
- 不要把规则卡示例包装成生产模型。
- 不要为了通过 pytest 放宽 validation 或删除业务断言。
- 报告中必须写清本场景是 benchmark/workflow fixture，不是可上线风控系统。
