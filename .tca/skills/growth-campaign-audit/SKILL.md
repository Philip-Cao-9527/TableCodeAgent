---
name: growth-campaign-audit
description: Marketing growth campaign table audit guidance for TableCodeAgent. Use when Codex needs to design, implement, review, or run a pre-modeling audit for campaign exposure, rewards, users, and orders tables, especially tasks involving treatment/control checks, join expansion, group balance, SMD, subsidy outliers, time-window alignment, warnings, and how-to-do-differently notes.
---

# Growth Campaign Audit

## Scope

Use this skill as procedural guidance for marketing growth data audits before modeling. Keep it as methodology and review criteria only; do not put deterministic calculations here.

This skill does not claim support for uplift modeling, PSM/IPW training, causal effect estimation, intelligent pricing models, automatic campaign strategy generation, or an enterprise BI platform.

## Audit Workflow

1. Identify input tables and keys:
   - `users`: user attributes and historical behavior.
   - `campaign_exposure`: campaign assignment and treatment/control group.
   - `rewards`: subsidy or reward records.
   - `orders`: conversion and GMV evidence.

2. Check table quality before any modeling interpretation:
   - Missing values by column and missing rate.
   - Business key uniqueness, especially reward keys such as `user_id + campaign_window`.
   - Duplicate records and whether duplicates affect rows, subsidy totals, or conversions.

3. Check sample construction:
   - Join cardinality between `campaign_exposure` and `rewards`.
   - `row_expansion_ratio` after join.
   - Whether the join risk is `one_to_many`, `many_to_one`, or `many_to_many`.

4. Check treatment/control comparability:
   - Treatment/control counts and minority-to-majority ratio.
   - Key covariate balance, such as `historical_orders_30d`, `historical_gmv_30d`, `active_days_30d`, and `user_level`.
   - SMD for numeric covariates and categorical distribution gaps for categorical covariates.
   - Overlap and extreme weights only as audit warnings unless a deterministic tool/workflow implements them.

5. Check business timing and incentives:
   - `subsidy_amount` outliers or extreme values.
   - Whether `order_time` falls inside `campaign_window`.
   - Whether conversion windows match campaign windows.

6. Produce a structured audit report:
   - `data issue`: observed data quality problems.
   - `blocking issue`: problems that make a downstream estimate unsafe.
   - `warning issue`: risks that should be reviewed but do not necessarily block the audit.
   - `how_to_do_differently`: concrete next actions for future runs.

## Required Cautions

- Do not treat a raw treatment/control conversion-rate difference as a causal effect.
- Do not silently `drop_duplicates`.
- Report duplicate ratio and impacted sample first; deduplicate only after the business rule is confirmed.
- Do not hide join expansion as a validation failure or empty data.
- Record duplicate keys, row expansion, time-window mismatch, and outlier evidence in trace or benchmark output when the runtime supports it.

## TableCodeAgent Mapping

- Put deterministic checks in `src/tablecodeagent/table_tools/quality.py`.
- Put fixed multi-step orchestration in `src/tablecodeagent/workflows/`.
- Put benchmark tasks and expected outputs in `benchmarks/tasks/`.
- Use this skill only for instructions, review criteria, and workflow discipline.
