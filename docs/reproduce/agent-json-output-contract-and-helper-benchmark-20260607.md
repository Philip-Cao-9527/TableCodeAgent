# Agent 输出 JSON 结构规范化与 helper-assisted benchmark 诊断

本文回应 [code-review-v0.0.3-20260607.md](code-review-v0.0.3-20260607.md#L318) 中“专项诊断四”的三个问题：

- 业界规范 Agent 输出 JSON 结构通常怎么做。
- TableCodeAgent 当前 `output_contract` / `schema_check` / pytest 口径的优缺点，以及更好的方案。
- 为什么 [growth_campaign_audit_001/task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json#L29) 里的 `implementation_hints.allowed_project_helpers` 会降低 benchmark 难度。

## 可直接口述版本

如果面试官问“你怎么规范 Agent 输出的 JSON 结构”，我会这样回答：

第一，业界一般不会只靠 prompt 说“请输出 JSON”。更稳的做法是把输出结构显式变成机器可校验的契约，例如 JSON Schema、Pydantic model、Zod schema 或 tool/function calling 的参数 schema。OpenAI 的 Structured Outputs 就是把 `response_format` 设置成 `json_schema` 并开启 `strict: true`，让模型输出尽量受 schema 约束；Anthropic 的 tool use 也要求工具输入用 `input_schema` 描述，并支持 strict tool use 来保证 tool input 符合 schema。核心思想是：**把自然语言要求变成结构化契约，再用程序二次校验**。

第二，结构化输出一般分三层。第一层是生成时约束，让模型少犯格式错误；第二层是解析时校验，用 JSON Schema / Pydantic / pytest 验证字段、类型、枚举、数组元素、嵌套对象；第三层是业务验证，比如数值是否等于 expected、是否命中风险标签、测试是否全部通过。公式可以写成：

$$
pass = syntax\_valid \land schema\_valid \land semantic\_valid
$$

其中 `syntax_valid` 表示 JSON 能解析，`schema_valid` 表示字段和类型满足契约，`semantic_valid` 表示答案业务上正确。TableCodeAgent 当前的 `schema_check` 只覆盖了 `schema_valid` 的一小部分，也就是顶层 key 是否存在；真正的业务正确性仍然依赖 pytest。

第三，你现在的做法是合理的 MVP 过渡方案。`task.json` 里公开了 `output_contract`，runner 会把它写进模型 prompt，要求 `answer.json` 满足契约；同时 `_validate_answer_json()` 对 pytest 型任务返回 `passed: None`，避免把“写出了 answer.json”误判成答对；最终 `result_from_trace()` 只有在没有 `failure_type`，且 `validation.passed is True` 或 `test_pass_rate == 1.0` 时才算通过。这比“模型随便输出 JSON，runner 只看文件存在”严谨很多。

第四，它的问题是契约还不够结构化。当前 [task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json#L40) 的 `output_contract.answer_json_required_keys` 只列出了顶层字段，例如 `row_counts`、`join_cardinality`、`smd_summary` 等；但 pytest 实际还读取了 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py#L33) 里的嵌套字段 `unique_keys.rewards_duplicate_key.duplicate_key_count` 和 `key_columns`。所以模型只要满足顶层 key，就可能通过 `schema_check`，但 pytest 仍失败。这不是模型“没写 JSON”，而是公开契约没有覆盖真实验证依赖。

第五，更好的方案是把 `output_contract` 从“顶层 key 列表 + 文本描述”升级成“完整 JSON Schema 或 Pydantic schema”。比如在 task 中声明 `answer_json_schema`，包含 `type`、`properties`、`required`、`additionalProperties`、嵌套对象、数组元素类型、枚举和数值范围；runner 生成 prompt 时展示 schema 摘要，执行后用 `jsonschema` 或 Pydantic 真校验 `answer.json`。这样 `schema_check` 才能覆盖 `unique_keys.rewards_duplicate_key.duplicate_key_count` 这种嵌套字段。

第六，`implementation_hints.allowed_project_helpers` 会降低 benchmark 难度，是因为它不只是告诉模型“可以用哪些库”，而是直接给出了项目里已经写好的完整 workflow helper：

```json
"from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report"
```

并且 `solve_py_suggestion` 还明确说可以在 `solve.py` 中调用 `build_growth_campaign_audit_report(...)` 后写出 `answer.json`。这会把任务从“Agent 自主读表、设计审计流程、实现 join 检查、平衡性检查、SMD、异常值和时间窗口校验”降级成“Agent 是否会按提示 import 一个已有函数并序列化结果”。它不是 oracle 泄露，因为没有把 `expected.json` 或标准答案暴露给模型；但它会泄露解题路线和核心实现入口，所以更适合 smoke / helper-assisted 口径，不适合宣称模型独立完成完整表格推理 workflow。

记忆点：**规范 JSON 输出不是一句 prompt，而是三件事：生成时受约束、落盘后可校验、业务上能判对错。helper 提示不是答案泄露，但会把 benchmark 从自主解题变成调用既有解法。**

## 从零讲清楚：Agent 输出 JSON 为什么难规范

普通程序的输出结构是开发者写死的，函数返回什么字段、字段是什么类型，基本由代码决定。Agent 不一样，它的中间产物和最终回答往往由大模型生成。大模型擅长生成“像 JSON 的文本”，但如果只靠自然语言提示，它可能出现这些问题：

- 多包一层，例如把结果包在 `audit_results` 下。
- 少字段，例如漏掉 `unique_keys`。
- 字段名近似但不一致，例如 `duplicate_keys` 和 `unique_keys`。
- 类型不一致，例如本应是字符串列表，却输出成对象。
- 值格式不稳定，例如枚举值、日期、百分比、布尔值混用。
- JSON 可解析，但业务含义不满足测试。

所以业界通常把“让模型输出 JSON”拆成两个不同目标：

1. **格式正确**：输出必须是合法 JSON，能被 `json.loads()` 解析。
2. **结构正确**：字段、类型、嵌套层级、枚举、数组元素、必填字段必须符合契约。
3. **语义正确**：字段值必须真的算对，不能只是长得像答案。

这三者不能混为一谈。一个 `answer.json` 可以格式正确，但结构不对；也可以结构对，但数值错。TableCodeAgent 的 benchmark 正是这种场景：Agent 需要生成 `solve.py`，执行后写出 `answer.json`，然后 runner 再根据 schema、pytest 和 trace 判断是否通过。

## 业界常见做法

### 1. JSON mode：只保证“像 JSON”，不保证结构完整

早期很多系统会要求模型“只输出 JSON”，或者开启 JSON mode。它的价值是减少自然语言前后缀，让输出更容易被解析。但它通常不保证嵌套字段齐全，也不保证类型正确。

这类方案适合简单场景，例如只要模型输出：

```json
{
  "label": "positive",
  "confidence": 0.92
}
```

但如果输出是多层表格审计报告，只靠 JSON mode 不够。因为模型可能输出合法 JSON，却缺少 pytest 读取的字段。

### 2. JSON Schema / strict structured output：生成阶段就加结构约束

更成熟的方案是把输出契约写成 JSON Schema。JSON Schema 的核心元素包括：

- `type`: 字段类型，例如 `object`、`array`、`string`、`number`、`boolean`。
- `properties`: 对象里有哪些字段。
- `required`: 哪些字段必填。
- `items`: 数组元素是什么结构。
- `enum`: 只能取哪些值。
- `additionalProperties`: 是否允许多余字段。
- `minimum` / `maximum` / `minItems`: 数值和数组约束。

官方 JSON Schema 文档明确说明，`properties` 用来定义对象字段，`required` 用来指定必填字段；如果嵌套对象也有必填字段，`required` 要写在对应嵌套对象自己的作用域里。这正好解释了当前 TableCodeAgent 的问题：只检查顶层 `required`，无法自动约束 `unique_keys.rewards_duplicate_key.duplicate_key_count`。

OpenAI Structured Outputs 的工程口径也是类似的：用 `response_format: { "type": "json_schema", "json_schema": ..., "strict": true }` 给模型一个 schema，并建议 key 命名清晰、给重要字段写 description、用 evals 选择适合的结构。它还强调拿到匹配 schema 的 JSON 后，可以再解析到语言里的类型系统，例如 Pydantic model 或 TypeScript type。

### 3. Tool / function calling：把结构化输出包装成“调用一个工具”

另一类常见方案是让模型调用一个“提交答案”的工具，例如：

```json
{
  "name": "submit_answer",
  "input_schema": {
    "type": "object",
    "properties": {
      "row_counts": {"type": "object"},
      "join_cardinality": {"type": "object"},
      "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["row_counts", "join_cardinality", "warnings"]
  }
}
```

Anthropic 的 tool use 文档就是这种思路：工具定义里包含 `name`、`description`、`input_schema`，其中 `input_schema` 是 JSON Schema 对象；复杂输入还可以加 `input_examples`，但 examples 必须符合 schema。更进一步，strict tool use 可以要求工具输入严格符合 schema。

这种方式的优点是输出直接走工具调用参数，而不是从一段自然语言里提取 JSON。缺点是它更适合“最终答案就是一份结构化对象”的场景；TableCodeAgent 目前要求模型生成并执行 `solve.py`，所以最终 `answer.json` 还是需要落盘校验。

### 4. Pydantic / dataclass：用代码里的类型模型生成 schema，并做二次校验

工程上更可维护的方案，是先在代码里定义答案类型，再由类型模型生成 JSON Schema。例如用 Pydantic：

```python
from pydantic import BaseModel, Field

class DuplicateKeyReport(BaseModel):
    duplicate_key_count: int
    key_columns: list[str]

class UniqueKeys(BaseModel):
    rewards_duplicate_key: DuplicateKeyReport

class GrowthCampaignAuditAnswer(BaseModel):
    row_counts: dict[str, int]
    unique_keys: UniqueKeys
    warnings: list[str]
```

然后：

- prompt 中展示 `GrowthCampaignAuditAnswer.model_json_schema()` 的简化版。
- 执行后用 `GrowthCampaignAuditAnswer.model_validate_json(answer_path.read_text())` 校验。
- 校验错误写入 trace，明确是哪个路径缺失或类型错误。

这样做的好处是“文档、prompt、校验”来自同一个 schema 源，减少三处不一致。Pydantic 官方文档也支持从 model 生成 JSON Schema，例如 `model_json_schema()`。

### 5. 解析失败后的 repair loop

很多生产系统不会只跑一次。如果模型输出 JSON 解析失败或 schema 校验失败，会把错误信息反馈给模型，让它只修复结构，不重新自由发挥答案。这类 repair loop 的常见流程是：

```text
模型生成 -> JSON parse -> schema validate -> 失败则返回精确错误路径 -> 模型修复 -> 再校验
```

例如错误可以写成：

```text
answer.json 不满足 schema：
- $.unique_keys.rewards_duplicate_key.duplicate_key_count 缺失
- $.warnings 应为 array[string]，实际为 object
请只修复 answer.json 结构，不要读取 expected.json。
```

对 benchmark 要谨慎使用 repair loop：如果 repair 阶段能看到 pytest 的 expected 值，就可能引入 oracle 泄露；但如果只返回 schema 错误路径，不返回标准答案数值，它可以作为结构修复能力的一部分。

## TableCodeAgent 当前做法

当前 `growth_campaign_audit_001` 的配置包含两块关键信息。

第一块是实现提示：[task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json#L29) 公开了：

```json
"implementation_hints": {
  "allowed_project_helpers": [
    "from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report"
  ],
  "solve_py_suggestion": "可以在 solve.py 中调用 build_growth_campaign_audit_report(Path(__file__).resolve().parent)，再用 json.dumps(..., ensure_ascii=False, indent=2) 写出 answer.json。"
}
```

第二块是输出契约：[task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json#L40) 公开了：

```json
"output_contract": {
  "validation_mode": "pytest",
  "answer_json_required_keys": [
    "row_counts",
    "join_cardinality",
    "group_distribution",
    "smd_summary",
    "outlier_summary",
    "time_window_alignment",
    "warnings",
    "how_to_do_differently"
  ]
}
```

runner 会在 `_task_prompt()` 中把 `output_contract` 和 `implementation_hints` 都写进 prompt，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L310)。同时 prompt 明确要求不要读取 `expected.json`，要写出 `solve.py` 和 `answer.json`，并让 `answer.json` 满足公开的 `output_contract`。

执行后，runner 会调用 `_schema_check_answer_json()`，但这个函数当前只做顶层 key 检查，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L224)。它读取 `answer_json_required_keys`，比较 `answer.keys()`，然后返回缺失的顶层字段。它不会检查：

- `unique_keys` 是否存在。
- `unique_keys.rewards_duplicate_key` 是否存在。
- `duplicate_key_count` 是否为整数。
- `key_columns` 是否为字符串列表。
- `join_cardinality.row_expansion_ratio` 是否为数字。
- `warnings` 是否为 `array[string]`。

真正的业务验证发生在 pytest。`growth_campaign_audit_001` 的 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py#L21) 先检查顶层字段，然后在 [tests/test_solution.py](../../benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py#L33) 读取嵌套字段：

```python
duplicate_key = answer.get("unique_keys", {}).get("rewards_duplicate_key", {})
assert duplicate_key.get("duplicate_key_count") == expected["expected_duplicate_key_count"]
assert duplicate_key.get("key_columns") == expected["expected_duplicate_key_columns"]
```

而 helper 生成的报告实际上包含这些字段，见 [growth_campaign_audit.py](../../src/tablecodeagent/workflows/growth_campaign_audit.py#L139)：

```python
return {
    "task_id": task["id"],
    "row_counts": row_counts,
    "profiles": profiles,
    "missing_values": missing_values,
    "unique_keys": {
        "rewards_duplicate_key": duplicate_key,
    },
    ...
}
```

这说明当前失败风险不是 helper 算不出来，而是公开输出契约没有完整表达 pytest 的真实依赖。

## 当前方案的优点

### 1. 已经把“输出结构”从纯 prompt 升级成了 task 契约

`output_contract` 至少让模型知道 `answer.json` 应该有哪些顶层字段，避免完全靠模型猜测。这对 benchmark 非常重要，因为模型如果不知道结果应该平铺还是包一层，很容易输出形式正确但测试失败的 JSON。

### 2. 没有把 `answer.json` 存在误判为通过

`_validate_answer_json()` 对 pytest 型任务返回 `passed: None`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L279)。这避免了一个常见误区：只要模型写出了 `answer.json`，就把 validation 写成通过。当前最终通过口径在 [logger.py](../../src/tablecodeagent/tracing/logger.py#L85) 里是：

```python
passed = failure_type is None and (
    validation.passed is True or test_pass_rate == 1.0
)
```

这说明 pytest 失败不会被 `answer.json` 存在掩盖。

### 3. trace 能区分生成、执行、结构和测试失败

runner 会记录 `schema_check`、`validation`、`pytest_exit_code`、`pytest_failure_summary`、`generated_code_path`、`answer_path` 等字段，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L465)。这对归因很有价值：可以分清楚模型没写代码、代码运行失败、顶层 schema 不满足、pytest 失败、还是 API 环境缺失。

### 4. `implementation_hints` 对 MVP smoke 有实际价值

在早期 benchmark 还在收敛时，直接允许调用项目 helper 能验证：

- 真实 API Agent 是否能读 task。
- 是否能生成 `solve.py`。
- 是否能正确 import 项目模块。
- sandbox 的 `PYTHONPATH` 是否有效。
- 是否能把结构化结果写成 `answer.json`。
- pytest / trace / results 是否能跑通。

所以它不是“完全错误”，而是适用于 helper-assisted smoke，不适合作为“模型自主完成复杂表格推理”的强证据。

## 当前方案的缺点

### 1. `output_contract` 是“弱 schema”

当前契约只列顶层 key，没有表达嵌套字段、类型、枚举、数组元素、数值范围和额外字段策略。它能防止“完全跑偏”，但不能保证结构和 pytest 对齐。

对比 JSON Schema，当前契约缺少：

```json
{
  "type": "object",
  "properties": {
    "unique_keys": {
      "type": "object",
      "properties": {
        "rewards_duplicate_key": {
          "type": "object",
          "properties": {
            "duplicate_key_count": {"type": "integer"},
            "key_columns": {
              "type": "array",
              "items": {"type": "string"}
            }
          },
          "required": ["duplicate_key_count", "key_columns"]
        }
      },
      "required": ["rewards_duplicate_key"]
    }
  },
  "required": ["unique_keys"]
}
```

这就是 review 里说“顶层 `schema_check` 不能检查嵌套字段”的具体含义。

### 2. prompt 中公开 helper 会改变任务性质

`allowed_project_helpers` 当前直接暴露 `build_growth_campaign_audit_report` 的 import 路径，并且 `solve_py_suggestion` 直接给出调用方式。这等于告诉模型：

1. 解题入口在哪里。
2. 不需要自己设计审计流程。
3. 不需要自己实现 join cardinality、SMD、outlier、time window 逻辑。
4. 只需要把 helper 结果写入 `answer.json`。

因此这个 benchmark 的难度从“自主代码生成 + 表格审计推理”下降为“读提示 + 调 helper + 序列化”。它仍然能测 Agent 是否会使用现有项目 API，但不能完整测 Agent 是否能从 task 和 CSV 自主写出 workflow。

### 3. helper 不是 oracle 泄露，但属于解题路线泄露

这里要区分两个概念：

- **oracle 泄露**：把 `expected.json`、标准答案、测试断言里的目标数值直接给模型。
- **解题路线泄露**：不告诉标准答案，但告诉模型调用哪个已实现函数即可生成答案。

当前 `implementation_hints.allowed_project_helpers` 属于第二类。它不会让模型直接看到 `expected_duplicate_key_count`，但它给了一个高覆盖的解题函数。对业务 smoke 来说可以接受；对能力评估来说要单独标注。

### 4. 契约、pytest、helper 返回结构三者没有统一来源

目前三处信息分别存在：

- `task.json.output_contract`：顶层字段列表。
- `tests/test_solution.py`：真实 pytest 断言。
- `growth_campaign_audit.py`：helper 返回结构。

当三者不一致时，就会出现当前问题：helper 返回了 `unique_keys`，pytest 依赖 `unique_keys`，但公开契约没写 `unique_keys`。这会让模型按公开契约做了一个看似合理的 JSON，却仍然 pytest 失败。

## 更好的方案

### 方案一：最小修复，补全 `output_contract` 的嵌套字段

这是当前仓库最小可行改法。可以保留现有结构，新增一组 `required_nested_fields` 或 `answer_json_required_paths`：

```json
"output_contract": {
  "validation_mode": "pytest",
  "answer_json_required_keys": [
    "row_counts",
    "join_cardinality",
    "group_distribution",
    "smd_summary",
    "outlier_summary",
    "time_window_alignment",
    "warnings",
    "how_to_do_differently",
    "unique_keys"
  ],
  "answer_json_required_paths": [
    "unique_keys.rewards_duplicate_key.duplicate_key_count",
    "unique_keys.rewards_duplicate_key.key_columns",
    "join_cardinality.cardinality",
    "join_cardinality.row_expansion_ratio",
    "smd_summary.warning_columns",
    "outlier_summary.outlier_count",
    "time_window_alignment.mismatch_count"
  ]
}
```

然后 `_schema_check_answer_json()` 支持按路径检查存在性和基础类型。这比完整 JSON Schema 简单，但足以修掉当前“顶层通过、pytest 嵌套失败”的问题。

适用场景：v0.0.3 到 v0.0.4 的小步修复。

### 方案二：升级为完整 JSON Schema

更规范的方案是在 task 中加入 `answer_json_schema`：

```json
"answer_json_schema": {
  "type": "object",
  "additionalProperties": true,
  "properties": {
    "row_counts": {
      "type": "object",
      "properties": {
        "users": {"type": "integer"},
        "campaign_exposure": {"type": "integer"},
        "rewards": {"type": "integer"},
        "orders": {"type": "integer"}
      },
      "required": ["users", "campaign_exposure", "rewards", "orders"]
    },
    "unique_keys": {
      "type": "object",
      "properties": {
        "rewards_duplicate_key": {
          "type": "object",
          "properties": {
            "duplicate_key_count": {"type": "integer"},
            "key_columns": {
              "type": "array",
              "items": {"type": "string"}
            }
          },
          "required": ["duplicate_key_count", "key_columns"]
        }
      },
      "required": ["rewards_duplicate_key"]
    },
    "warnings": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": [
    "row_counts",
    "unique_keys",
    "join_cardinality",
    "group_distribution",
    "smd_summary",
    "outlier_summary",
    "time_window_alignment",
    "warnings",
    "how_to_do_differently"
  ]
}
```

runner 执行后用 `jsonschema` 校验 `answer.json`。schema 校验失败时，把错误路径写进 trace，例如：

```json
{
  "schema_check": {
    "passed": false,
    "errors": [
      {
        "path": "$.unique_keys.rewards_duplicate_key.duplicate_key_count",
        "message": "required property missing"
      }
    ]
  }
}
```

适用场景：要让 benchmark 的结构校验和 pytest 更一致，并沉淀成可复用 benchmark contract。

### 方案三：用 Pydantic 作为单一事实来源

如果后续 task 增多，建议把答案结构定义成 Pydantic model，并由 model 生成 JSON Schema：

```python
class GrowthCampaignAuditAnswer(BaseModel):
    row_counts: RowCounts
    unique_keys: UniqueKeys
    join_cardinality: JoinCardinality
    group_distribution: GroupDistribution
    smd_summary: SmdSummary
    outlier_summary: OutlierSummary
    time_window_alignment: TimeWindowAlignment
    warnings: list[str]
    how_to_do_differently: list[str]
```

这样可以让三件事共享同一个来源：

- prompt 展示的公开契约来自 `model_json_schema()`。
- `schema_check` 用同一个 model 校验。
- pytest 可以复用 model 解析后的对象，再检查业务值。

优点是维护成本更低，不容易出现“pytest 读了字段，但 contract 忘了写”的问题。缺点是前期要多写一些类型模型；对 MVP 来说工作量比方案一大。

### 方案四：区分 benchmark 难度档位

建议把 `implementation_hints` 拆成不同难度口径：

```json
"benchmark_profiles": {
  "helper_assisted": {
    "allowed_project_helpers": [
      "from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report"
    ]
  },
  "library_assisted": {
    "allowed_libraries": ["pandas", "numpy"],
    "allowed_project_helpers": []
  },
  "from_scratch": {
    "allowed_libraries": ["pandas", "numpy"],
    "allowed_project_helpers": [],
    "hide_workflow_module_names": true
  }
}
```

报告中分别写：

- `helper_assisted_pass_rate`: 模型会不会正确调用项目已有 workflow。
- `library_assisted_pass_rate`: 模型能否用 pandas 自己实现任务。
- `from_scratch_pass_rate`: 模型只依赖 task/data/schema，自主完成流程。

这样既保留 smoke 价值，又不会夸大真实自主代码生成能力。

## 为什么 helper 会降低 benchmark 难度

以 `growth_campaign_audit_001` 为例，原始任务要解决的问题包括：

- 读取四张 CSV。
- 按 `user_id`、`campaign_id`、`campaign_window` 做 join。
- 检查 rewards 是否存在重复 key。
- 计算 join 膨胀比例。
- 统计 treatment/control 分布。
- 计算协变量 SMD。
- 检查补贴极端值。
- 检查订单时间是否和活动窗口错配。
- 组织 warnings 和改进建议。

如果不提供 helper，Agent 必须从 [task.json](../../benchmarks/tasks/growth_campaign_audit_001/task.json#L16) 的 `audit_config` 和 CSV 文件推断这些步骤，然后写出完整 `solve.py`。这考察的是：

```text
任务理解能力 + 表格推理能力 + pandas 实现能力 + 输出结构遵循能力
```

但提供 `allowed_project_helpers` 后，模型看到：

```python
from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report
```

再结合 `solve_py_suggestion`，最短可行解就变成：

```python
from pathlib import Path
import json
from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report

report = build_growth_campaign_audit_report(Path(__file__).resolve().parent)
Path("answer.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
```

这个解法几乎不需要模型自己实现审计逻辑。真正做 join、SMD、outlier、time window 的代码已经在 [growth_campaign_audit.py](../../src/tablecodeagent/workflows/growth_campaign_audit.py#L73) 里写好了。模型主要负责把现成 helper 接起来。

所以难度下降可以形式化理解为：

$$
D_{from\_scratch} = U + P + C + S + V
$$

其中：

- $U$ 是理解任务和业务风险。
- $P$ 是规划审计步骤。
- $C$ 是写 pandas / workflow 代码。
- $S$ 是满足 JSON schema。
- $V$ 是通过验证。

而 helper-assisted 情况下：

$$
D_{helper} = I + S + V
$$

其中 $I$ 是正确 import 和调用 helper。`P` 和 `C` 的大部分已经被项目 helper 吸收了。难度当然下降。

这不是坏事，但要在报告里讲清楚。`helper_assisted` 适合证明“项目 workflow、sandbox、trace、pytest、真实 API 调用链能跑通”；`from_scratch` 才适合证明“模型能自主完成表格审计代码生成”。

## 规则卡评分固定示例是什么意思

`credit_risk_scoring_001` 里说“规则卡评分是固定示例，不代表训练真实模型或通用风控能力”，指的是当前信贷风控 workflow 只是用一套手写、确定性的业务规则给样本打分，而不是从数据中训练出一个可泛化的风控模型。

具体看 [credit_risk_scoring.py](../../src/tablecodeagent/workflows/credit_risk_scoring.py#L45)，`_score_applications()` 会把 `loan_amount`、`income`、`age`、`credit_score`、`existing_debt`、`employment_years` 转成数值，再按固定公式计算 `risk_score`。核心逻辑在 [credit_risk_scoring.py](../../src/tablecodeagent/workflows/credit_risk_scoring.py#L55)：

```python
risk_score = (
    20
    + debt_to_income * 25
    + loan_to_income * 20
    + credit_component
    + age_component
    + employment_component
).clip(0, 100)
```

随后它把分数映射成 `high`、`medium`、`low` 风险档，并在 [credit_risk_scoring.py](../../src/tablecodeagent/workflows/credit_risk_scoring.py#L137) 标记方法为 `rule_based_scorecard`。这类规则卡的价值是可解释、可复现、适合做最小 fixture：它能验证 Agent 是否完成了字段读取、缺失值检查、重复主键检查、异常年龄检查、贷后泄漏字段排除、结构化 JSON 输出和 pytest 校验。

但它不等于“训练了真实风控模型”。真实风控模型至少还会涉及训练 / 验证 / 测试切分、样本时间窗、标签窗口、特征工程、模型拟合、调参、AUC / KS / PR-AUC 等指标、校准、稳定性和上线监控。当前代码没有 `fit()` 一个 Logistic Regression、XGBoost、LightGBM 或深度模型，也没有证明这套固定权重能泛化到新用户、新时间段或真实业务分布。

所以这个场景的证据级别应该这样写：

- 可以说：它是一个信贷风险评分 workflow fixture，用固定规则卡验证表格质量检查、泄漏字段排除、评分输出和 validation 闭环。
- 可以说：它帮助 benchmark 覆盖风控任务里的数据质量与输出结构问题。
- 不能说：它已经训练了生产级风控模型。
- 不能说：它证明 TableCodeAgent 具备通用信贷风控建模能力。
- 不能说：它代表真实业务可上线的评分卡或机器学习模型。

一句话记忆：**固定规则卡是在小样本上演示“风控 workflow 应该检查什么、输出什么”，不是在真实业务数据上学习“如何预测违约”。**

## 推荐落地路线

### v0.0.4 最小路线

1. 在 `growth_campaign_audit_001/task.json` 的 `output_contract.answer_json_required_keys` 中补 `unique_keys`。
2. 新增 `output_contract.answer_json_required_paths`，至少覆盖 pytest 读取的嵌套字段。
3. 扩展 `_schema_check_answer_json()`，支持点路径存在性检查和基础类型检查。
4. 在 trace 中记录 `schema_check.errors`，每条包含 `path`、`expected`、`actual`、`message`。
5. README 和 report 中明确当前 growth 任务是 `helper-assisted`，不要写成完全 from-scratch。

### v0.0.5 更规范路线

1. 为每类 benchmark task 建 Pydantic answer model。
2. 用 model 生成公开 JSON Schema。
3. runner prompt 展示压缩后的 schema，不只展示顶层 key。
4. schema 校验和 pytest 复用同一份类型定义，减少契约漂移。
5. benchmark 结果拆分 `helper_assisted`、`library_assisted`、`from_scratch` 三个口径。

### 不建议的做法

- 不建议只在 prompt 里追加一大段自然语言描述，因为它仍然不可校验。
- 不建议把 pytest 失败信息里的 expected 数值直接反馈给模型修复，这会接近 oracle 泄露。
- 不建议删除 `implementation_hints` 后仍沿用同一个历史 pass rate，因为 benchmark 难度已经变化。
- 不建议把 `schema_check.passed=true` 写成最终通过；它只代表结构的一部分通过。

## 面试官可能追问

### 追问 1：为什么不用 prompt 直接要求“严格 JSON”？

因为 prompt 是软约束，模型可能遵守，也可能漏字段或改字段名。结构化输出要靠 schema 和程序校验形成硬约束。我的项目里已经从纯 prompt 进化到 `output_contract`，但还需要从顶层 key 检查升级到完整嵌套 schema。

### 追问 2：`output_contract` 和 pytest 是什么关系？

`output_contract` 是公开给模型的结构要求，pytest 是隐藏的最终业务验证。理想状态是 pytest 依赖的结构字段都应该在公开 contract 里声明，但具体 expected 数值不能泄露。当前问题就是 pytest 读取了 `unique_keys.rewards_duplicate_key`，但公开 contract 没写这个嵌套字段。

### 追问 3：helper-assisted benchmark 有没有价值？

有价值，但价值边界不同。它可以验证真实 API Agent 能否读任务、写代码、调用项目模块、落盘 answer、跑 sandbox、跑 pytest、写 trace。它不能证明模型独立实现了完整 workflow，所以报告里必须标成 helper-assisted。

### 追问 4：你会怎么避免 oracle 泄露？

生成阶段不复制 `expected.json`，prompt 明确禁止读取 `expected.json`，工具层限制 workspace 访问；外部 pytest 前再恢复 expected。修复阶段如果做 repair loop，只反馈 schema 错误路径，不反馈 expected 数值。

### 追问 5：如果要做真正自主代码生成评测，应该怎么改？

把 benchmark 分档。from-scratch 档只给 task、CSV、输出 schema 和允许库，不给 `build_growth_campaign_audit_report` 这种项目 helper；helper-assisted 档单独保留，用来测工程链路和工具调用能力。两套结果分别报，不混在一个 pass rate 里。

## 外部依据

- OpenAI Structured Outputs 官方文档：说明 `response_format: {"type": "json_schema", ... "strict": true}`、schema 命名/description/evals 建议，以及解析到 Pydantic / TypeScript 类型的做法。<https://developers.openai.com/api/docs/guides/structured-outputs>
- JSON Schema 官方入门文档：说明 `properties`、`required`、嵌套对象里的 `required` 只在对应对象作用域生效。<https://json-schema.org/learn/getting-started-step-by-step>
- Pydantic JSON Schema 官方文档：说明可以用 `model_json_schema()` 从模型生成 JSON Schema。<https://docs.pydantic.dev/latest/concepts/json_schema/>
- Anthropic tool use 官方文档：说明工具定义包含 `input_schema`，复杂输入可以提供符合 schema 的 examples，并可通过 strict tool use 强化工具输入结构。<https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools>
