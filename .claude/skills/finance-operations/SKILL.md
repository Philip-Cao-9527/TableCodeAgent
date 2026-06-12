---
name: finance-operations
description: TableCodeAgent 财务运营应收账款与现金回款 workflow 指导。需要设计、实现、审核或运行 invoices、payments、customers、disputes、adjustments、policy 多表应收匹配、账龄、未核销、异常归因、客户风险和运营动作建议时使用；必须区分已接入能力、工业场景目标和未验证能力，且不得暴露 benchmark 答案或 helper。
---

# 财务运营应收回款分析

## 适用范围

本 skill 用作财务运营 benchmark 场景和应收账款/现金回款 workflow 的流程指导。它描述通用业务检查顺序、输入输出边界、验证要求和失败处理；确定性 oracle 已迁移到 `tests/test_workflows/`，产品态主 Loop 应通过 `src/tablecodeagent/workflow/` 和表格工具进入 MiniClaude Agent Loop。

三层边界必须写清：

- 当前已实现 / 已接入能力：公开 task contract、Pydantic schema、本地 fixture oracle、模拟 Agent 输出回归、sandbox + pytest/validator 验证，以及产品 Loop 的任务解析、表格画像、上下文压缩、候选代码执行和 repair feedback。
- 面向工业业务场景的目标能力：把应收回款、账龄、争议款、调整项、客户风险和运营动作组织成可追踪、可复核的 Coding Agent 工作流。
- 尚未接入 / 尚未验证能力：真实企业 ERP 接线、银行流水自动核销、法定财务审计意见、税务申报、外汇折算和真实催收决策。

## 不适用范围

- 不用于把未接入的企业系统能力写成已完成。
- 不用于替代会计系统、收款核销系统、授信管理、法定审计或合规审批。
- 不用于把固定 fixture 结果、`expected.json`、项目 helper import 路径或可直接复制的 `solve.py` 暴露给真实 LLM Agent benchmark。
- 不用于为了通过 benchmark 放宽异常、账龄、争议、币种或金额校验。

## 执行步骤

1. 识别输入表和主键：
   - `invoices` 通常以 `invoice_id` 作为发票业务键。
   - `payments` 通常以 `payment_id` 作为回款业务键，并优先用 `invoice_id` 匹配发票。
   - `customers` 提供客户状态、账期、默认币种和运营负责人。
   - `disputes` 提供争议发票、争议金额、原因和状态。
   - `adjustments` 提供 credit memo、write-off、chargeback 等会计调整。
   - `policy` 提供 `reference_date`、账龄分桶、金额精度和争议口径。

2. 先做数据质量检查：
   - 检查必需字段是否存在。
   - 检查重复发票、重复回款、负金额、缺失 due date、未知客户、未知发票。
   - 先归一化缺失值：空字符串、只含空白、null、pandas `NaN`/`NaT`、字符串 `"nan"`/`"NaN"`/`"NaT"`/`"None"`/`"null"` 都按缺失处理；缺失 due date 输出为 JSON `null`，不要输出字符串 `"nan"`。
   - 检查付款币种与发票币种是否一致。
   - 检查 payment cutoff、GL date、voided/reversed receipt、future-dated receipt。
   - 检查客户状态是否 active，以及非 active 客户是否仍有未清应收。
   - 检查 credit limit、缺失 PO、due date 是否符合客户账期；PO 缺失按归一化后的空值判断，而不是只判断原始空字符串。

3. 执行发票与回款匹配：
   - 按 `invoice_id` 优先匹配回款。
   - 重复 `payment_id` 只保留首次，后续重复行报告异常。
   - 无法匹配、缺失 `invoice_id`、未知发票或币种不一致的回款计入 unapplied cash。
   - Future-dated receipt、voided receipt、reversed receipt 不得减少当前 reference date 的 AR。
   - 部分付款保留剩余 open amount。
   - 超额付款的 applied amount 以 invoice amount 为上限，超出部分计入 overpayment 和 unapplied cash。

4. 处理会计调整：
   - Approved credit memo 和 approved write-off 可减少 open AR。
   - Pending write-off 只能报告并建议复核，不能提前减少 open AR。
   - Approved chargeback 会增加 open AR，并需要 payment investigation。
   - 未匹配到有效发票或币种不一致的 adjustment 必须报告为异常。

5. 执行账龄、争议和坏账准备口径：
   - 日期必须以 task/policy 公开的 `reference_date` 为准，不能使用系统当前日期。
   - 账龄分桶必须写清边界，例如 `0-30`、`31-60`、`61-90`、`90+` 的包含关系。
   - 缺失 due date 进入单独 bucket，不要静默当作未逾期或 0 天逾期。
   - Open dispute 保留在 aging 和 open receivables 中，同时单独报告 disputed open amount。
   - 客户风险金额应说明是否排除 disputed amount。
   - 如 task 提供 provision matrix / loss rates，只能按公开 policy 计算 expected credit loss，不能声明为真实 IFRS/GAAP 审计结论。

6. 输出客户级风险和运营动作：
   - 按客户汇总 open amount、overdue amount、disputed amount、max days overdue。
   - 输出 `risk_band`、`action_tags`、expected credit loss 和可解释 rationale。
   - 常见动作包括催收逾期款、处理争议、修复 due date、核销 unapplied cash、复核非 active 客户、复核 credit hold、补 PO、处理 pending write-off 和调查 chargeback。

7. 输出结构化结果：
   - `summary`
   - `customer_risk`
   - `invoice_reconciliation`
   - `aging_buckets`
   - `exceptions`
   - `recommended_actions`
   - `data_quality`
   - `audit_notes`
   - `validation`

## 输入输出约定

- 输入通常来自 `benchmarks/tasks/<task_id>/task.json` 以及 `invoices.csv`、`payments.csv`、`customers.csv`、`disputes.csv`、`policy.csv`。
- 真实 LLM Agent benchmark 只能看到 task、数据文件、允许库、业务目标和公开输出 schema。
- 真实 LLM Agent benchmark 不允许看到 `expected.json`、项目 workflow helper import 路径或任何项目内解题 helper。
- 输出必须落盘为 `answer.json`，并通过 Pydantic schema、task 内 pytest 和 trace/result 共同校验。

## 证据与验证要求

- `tests/test_workflows/` 中的 deterministic oracle 只能用作 unit / integration / smoke / regression 测试。
- 模拟 Agent 测试应覆盖账龄边界、部分/超额付款、枚举大小写、缺失字段、字段类型、NaN/NaT 缺失值归一化、adjustment 口径、ECL 口径和异常结构。
- 真实 API benchmark 必须记录 `benchmark_profile=no_helper`、`helper_hints_exposed=false`、`api_called`、`skipped`、`failure_type`、`generated_code_path`、`answer_path`、`schema_check.errors`、`run_python.exit_code`、`pytest_exit_code` 和 `validation.passed`。
- `SKIP`、env 缺失、API 失败、schema 不匹配、pytest 失败、未生成代码或未写出 `answer.json` 必须按真实失败写入报告，不能伪装通过。

## 注意事项

- 不要静默 drop duplicates。
- 不要把币种不一致的回款强行应用到发票。
- 不要把争议款从 aging 中删除；应单独说明争议口径。
- 不要把 future-dated、voided、reversed receipt 当作已核销现金。
- 不要把 pending write-off 或未匹配 credit memo 提前冲减 AR。
- 不要把 provision matrix 结果包装成真实会计准则审计意见。
- 不要使用当前系统日期计算账龄。
- 不要为了让模型通过而降低关键异常、金额或枚举校验。
- 报告中必须区分 product workflow、helper-assisted oracle 和 no-helper capability evaluation。
