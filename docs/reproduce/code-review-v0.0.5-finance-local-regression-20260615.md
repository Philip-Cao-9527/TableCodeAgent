# v0.0.5 集中 Code Review：finance_operations_001 本地回归与真实 API 前置审查

## 审查发现

### 严重：`missing_po` 真实失败的精确形态还没有本地 simulated Agent 回归

位置：
- [test_finance_operations_simulated_agent_outputs.py](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py#L37)
- [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L197)
- [results.jsonl](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/results.jsonl)
- [answer.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/answer.json)
- [solve.py](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/solve.py#L513)

证据：

- 2026-06-12 历史真实 API 结果保留了原始失败：`api_called=true`、`schema_check.passed=true`、`run_python.exit_code=0`、`pytest_exit_code=1`、`failure_type=pytest_failed`，见 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/results.jsonl)。
- 该 run 不是完全没识别 PO 缺失：历史 [answer.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/answer.json) 中 `data_quality.missing_po_invoice_ids=["INV-1006"]`，`INV-1006.exception_tags` 也包含 `missing_po`；真正缺口是 `exceptions` 列表没有 `missing_po` exception row。
- 历史生成代码在 [solve.py](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/solve.py#L513) 只 `tags.append("missing_po")`，没有像 `missing_due_date` 那样调用 `add_exception(...)`；后续 [solve.py](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/solve.py#L880) 只会输出已进入 `exceptions_map` 的类型。
- 当前 simulated Agent 测试覆盖了正确答案、账龄边界、付款匹配、adjustment/ECL、枚举大小写、字段缺失、类型漂移、嵌套 JSON、重复计数和 `"nan"` due date，见 [test_finance_operations_simulated_agent_outputs.py](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py#L37) 到 [test_finance_operations_simulated_agent_outputs.py](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py#L143)，但没有构造“`data_quality` 与 invoice tag 都写了 `missing_po`，只漏 exception row”的精确失败样例。
- README 最高优先级明确要求修复顺序必须先补本地回归：合同文本、Pydantic schema、pytest 业务断言、simulated Agent 错误输出、sandbox 执行和失败归因稳定后，才允许决定是否再次真实 API 复测，见 [README.md](../../README.md#L368)。

影响：

真实 API 已经暴露的最小失败形态仍只能由历史真实 run 或 task pytest 捕获，不能由当前 simulated Agent 回归前置捕获。继续直接复测真实 API 会违反 README 中“本地回归优先”的边界，也会继续用 API 成本发现本可本地构造的问题。

最小修复建议：

- 在 [test_finance_operations_simulated_agent_outputs.py](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py#L37) 增加一个精确变体：保留 `data_quality.missing_po_invoice_ids=["INV-1006"]` 和 `INV-1006.exception_tags=["missing_due_date","missing_po"]`，仅删除 `exceptions` 中的 `missing_po` row，断言 schema 当前状态和 pytest 失败形态。
- 若后续采用 Pydantic 语义校验，则该用例应进一步断言 schema 或新增 semantic validation 能提前失败。
- 报告和后续 fix-report 中要把该缺口写成“漏 `missing_po` exception row”，不要笼统写成“完全没覆盖 `missing_po`”。

验证建议：

- 运行 `.\.venv\Scripts\python.exe -m pytest tests/test_integration/test_finance_operations_simulated_agent_outputs.py tests/test_unit/test_real_api_code_agent_contract.py -q`。
- 再运行完整本地回归：`.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration -q`。

是否阻断后续动作：

会挡住后续修复交付后的真实 API 复测。先补这个本地回归，再谈是否运行第 1 次真实 API 复测。

### 高：Pydantic schema 仍不能表达 `required_exception_types` 覆盖和跨字段一致性

位置：

- [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L103)
- [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L197)
- [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L225)
- [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L247)
- [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L66)
- [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L70)
- [test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L55)

证据：

- `task.json` 已明确 PO 缺失必须同时落到 `data_quality.missing_po_invoice_ids`、`invoice_reconciliation.exception_tags` 和 `missing_po` exception row，见 [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L66)；`required_exception_types` 也包含 `missing_po`，见 [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L70) 到 [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L89)。
- pytest 会检查 expected exception types 是 `answer["exceptions"]` 的子集，并进一步检查 `exceptions["missing_po"]`，见 [test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L55) 到 [test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L95)。
- Pydantic 只把 `FinanceExceptionRow.exception_type` 限制为枚举值，见 [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L197)，但 `FinanceOperationsAnswer.exceptions` 只是 `list[FinanceExceptionRow]`，见 [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L252)，没有要求每个 `required_exception_types` 都出现，也没有要求 `data_quality.missing_po_invoice_ids`、invoice `exception_tags` 和 exception row 互相一致。
- 历史真实 API 因此出现 `schema_check.passed=true` 但 `pytest_exit_code=1`，见 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/results.jsonl)。

通俗解释：

这里的 `missing_po` 不是一个程序术语，而是一个财务 / 采购业务异常，意思是 **missing purchase order，缺少采购订单**。可以先把它理解成：公司收到一张供应商发票，但系统里找不到这张发票对应的采购订单。采购订单就是公司事先批准“可以买什么、向谁买、买多少、多少钱买”的单据。发票没有对应采购订单时，财务不能轻易付款，因为这可能表示采购流程没走完、供应商开票对象不清楚、金额没有被事先批准，或者数据录入漏了 PO 编号。

这份 benchmark 要模型生成一个 `answer.json`，可以把它理解成模型交上来的“财务异常检查报告”。报告里有几个英文 JSON 字段，但它们其实对应三张不同视角的表：

- `data_quality.missing_po_invoice_ids`：数据质量检查清单。中文意思是“哪些发票缺采购订单编号”。如果这里写了 `INV-1006`，就是在说 `INV-1006` 这张发票缺 PO。
- `invoice_reconciliation.exception_tags`：逐张发票的异常标签。中文意思是“这张发票身上贴了哪些异常标签”。如果 `INV-1006` 的标签里有 `missing_po`，就是在发票明细层面承认它缺采购订单。
- `exceptions`：异常汇总表。中文意思是“把所有异常按类型汇总成一张表”。这里必须有一行 `exception_type="missing_po"`，也就是“缺采购订单”这一类异常；这一行里的 `related_ids` 要列出相关发票，例如 `INV-1006`。

本次真实失败不是“某个字段拼错”这么简单，而是 **同一个业务事实没有在三张表里对齐**。业务事实是：`INV-1006` 缺采购订单。正确答案应该同时做到三件事：第一，在“缺采购订单发票清单”里写 `INV-1006`；第二，在 `INV-1006` 这张发票自己的异常标签里贴上 `missing_po`；第三，在“异常汇总表”里增加一行“缺采购订单”，并且这行也要关联到 `INV-1006`。历史真实 API 的答案前两件做到了，第三件漏了，所以不是完全没识别 `missing_po`，而是漏了 `missing_po` 的汇总行。

Pydantic schema 像第一道格式检查：它主要检查这份报告有没有这些栏目、每个栏目是不是列表或数字、枚举值是不是拼对了。例如 `exception_type` 只能写 `missing_po`，不能写 `Missing_PO` 或 `missing purchase order`。但当前 schema 还不会做更聪明的业务检查：它不能自动推理“既然 `INV-1006` 已经出现在缺采购订单清单里，也已经被贴了缺采购订单标签，那么异常汇总表里也必须有缺采购订单这一行”。这就是“不能表达跨字段一致性”的意思。pytest 业务断言比 schema 更懂这个业务关系，所以 schema 通过了，pytest 仍然失败。

影响：

`schema_check.passed=true` 容易被误读为业务输出已完整，只是 pytest 更严格；实际是 schema 没覆盖 pytest 业务断言真正关心的跨字段语义。后续模型仍可能输出结构正确但业务异常不完整的答案，失败继续落到 `pytest_failed`，不利于本地前置定位。

最小修复建议：

- 在 [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L247) 对 `FinanceOperationsAnswer` 增加语义级校验，至少覆盖：
  - `data_quality.missing_po_invoice_ids` 非空时，`exceptions` 必须包含 `exception_type="missing_po"`，且 `related_ids` 覆盖这些 invoice id。
  - 任一 invoice `exception_tags` 包含 `missing_po` 时，`exceptions` 必须包含 `missing_po` row。
  - `exception_tags` 中用于业务异常的值应限制为 `FinanceExceptionType` 或新增单独的 allowed tag schema，避免任意字符串漂移。
- 如果不希望把全部 pytest 业务口径塞进 Pydantic，则至少新增独立 semantic validation，并在 runner 中把 `schema_check` 与 `semantic_check` 分开记录。

验证建议：

- 增加单测：`missing_po_invoice_ids` 存在但缺少 `missing_po` exception row 应失败。
- 增加单测：只写 `missing_po` exception row 但 `related_ids` 不含 `INV-1006` 应失败。
- 增加单测：`exception_tags=["Missing_PO"]` 大小写漂移应失败。

是否阻断后续动作：

会影响修复交付质量；在该语义校验未补齐前，不建议把下一次真实 API 失败归因直接写成“模型能力不足”，因为本地 schema 仍有可前置收紧空间。

### 高：no-helper 防线已有 AST 检查，但生成代码运行期仍可接触项目 `src`

位置：

- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L31)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L313)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L327)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L702)
- [test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py#L236)

证据：

- 当前 no-helper 已禁用 `run_table_product_workflow`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L31)；也会扫描 `solve.py` 中的 forbidden helper markers 和 AST import，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L313) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L385)。
- 单测覆盖了动态 import 和产品/测试 oracle import，见 [test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py#L236) 到 [test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py#L263)。
- 但执行生成代码时仍设置 `PYTHONPATH` 指向项目 `src`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L702) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L711)。AST 检查覆盖常见字面量和简单拼接，但没有运行期 import hook；更复杂的计算式导入或间接加载仍需要人工审计才能确认未污染。

通俗解释：

`no-helper benchmark` 想测的是模型只看公开题目、CSV 数据和输出要求，能不能自己写出 `solve.py`。它不应该使用项目内部已经写好的参考答案、workflow helper 或测试用 oracle。否则就像闭卷考试时把标准答案放在旁边，最后分数就不能说明模型真的会做题。

这条链路可以拆成四步看：

1. **runner 先构造 prompt，发给真实 API。** 这里的 prompt 来自 `_task_prompt()`，只写入任务问题、workspace 文件列表、公开 `output_contract`、允许库、禁止读取 `expected.json`、禁止 import workflow helper 等文本，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L531) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L558)。这一步还没有执行 Python，也没有设置 `PYTHONPATH`。
2. **模型根据 prompt 写出 `solve.py`。** 模型看到的是上一步那段 prompt，不是整个仓库源码。prompt 没有把 [loop.py](../../src/tablecodeagent/workflow/loop.py#L20) 的源码内容粘给模型，所以不能说“模型因为 `PYTHONPATH` 指向 `src` 就阅读了 `loop.py`”。`PYTHONPATH` 是 Python 运行时环境变量，不是 LLM prompt 内容。
3. **runner 保存 `solve.py` 后，先做 helper 使用检查。** 也就是先读取生成文件本身，检查里面有没有明显违规的 helper 调用或 import，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L313) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L385)。这里的“检查”不是运行 `solve.py`，只是把生成文件当文本和 Python 代码结构看一遍。
4. **检查没有发现违规时，runner 才放行并执行 `solve.py`。** 这里要避免误解：不是“检查拦住了才执行”，而是相反。如果检查发现违规，会生成 `helper_denial`，runner 直接把 `failure_type` 记为 `helper_usage_forbidden` 并停止，不会执行 `solve.py`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L693) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L699)。只有检查返回 `None`，也就是没有发现明显 helper 使用，runner 才继续往下走。这时才设置 `PYTHONPATH` 指向项目 `src`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L702) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L711)。`PYTHONPATH` 可以理解成 Python 的“找包目录”。它的作用是：当 `solve.py` 里写 `import tablecodeagent...` 时，Python 会去 `src` 下寻找 `tablecodeagent` 包。

所以，`PYTHONPATH=src` 的影响路径不是“把源码发给模型看”，而是 **让模型生成的代码在运行时更容易导入项目内部模块**。如果没有 `PYTHONPATH=src`，`solve.py` 里写 `from tablecodeagent.workflow import run_product_workflow` 通常会因为找不到 `tablecodeagent` 包而失败；但有了 `PYTHONPATH=src`，Python 运行时就能找到 [workflow/loop.py](../../src/tablecodeagent/workflow/loop.py#L20) 里的 `run_product_workflow`。这会影响真实 API 测评的可信度：一旦生成代码调用了内部 workflow、测试 oracle 或参考解题函数，测到的就不是模型独立解题能力，而是“模型会不会借用项目内部解题器”。

更具体地说，helper 使用检查的返回值决定后续动作：`_generated_helper_usage_denial(solve_path)` 如果返回一段字符串，表示“发现违规理由”，runner 就拦截；如果返回 `None`，表示“这轮静态检查没有发现违规”，runner 才放行执行。这个 `None` 不是证明代码绝对安全，只是证明当前字符串检查和 AST 检查没有抓到 forbidden helper。

AST 检查就是“运行前把 `solve.py` 当成 Python 代码解析一遍，看它有没有明显违规导入”。AST 是 Python 的语法树。比如 `from tablecodeagent.workflow import run_product_workflow` 在文本里只是一行代码，但解析成 AST 后，runner 可以知道这是一个 `ImportFrom`，模块名是 `tablecodeagent.workflow`。当前 helper 使用检查包含两层：

- **字符串标记检查**：直接搜索 `tablecodeagent.workflow`、`tablecodeagent.product_agent`、`tests.test_workflows`、`build_finance_operations_report`、`run_finance_operations` 等 forbidden helper markers。
- **AST import 检查**：解析 `import ...`、`from ... import ...`、`__import__(...)`、`importlib.import_module(...)` 这类调用，并尝试识别字面量字符串和简单字符串拼接。

你引用的那句话理解是对的：这里说的 AST 检查，正是指“用字符串和 AST 检查明显的违规 import”。直接写 `tablecodeagent.workflow`、`tablecodeagent.product_agent`、`tests.test_workflows`、`build_finance_operations_report`、`run_finance_operations` 这类标记会被拦住；单测也覆盖了 `__import__('tablecodeagent.workflow.loop')` 和简单字符串拼接导入，见 [test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py#L236) 到 [test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py#L263)。

真正的问题是：AST 检查发生在运行前，属于“先看一遍代码文本”的静态检查；`PYTHONPATH=src` 的效果发生在运行时，属于“Python 实际去哪里找包”。如果生成代码用更复杂的运行期方式拼出模块名、通过未覆盖的加载 API 间接导入，或者访问某些没有被 denylist 覆盖但仍会影响 benchmark 独立性的内部模块，静态检查可能不一定全部拦住。换句话说，风险核心不是 `loop.py` 这一份文件本身，而是 no-helper benchmark 的运行环境还没有做到“项目内部模块天然不可见”。

所以这个 finding 不是说 2026-06-12 的失败已经被 helper 污染，也不是说模型已经读到了 `loop.py`。它说的是：后续如果某次真实 API 通过，仍要审计生成的 `solve.py` 到底是独立读取 CSV 解题，还是在运行时借用了项目内部模块。只要这个边界没完全收紧，`no-helper` 通过率就不能轻易当成无需复核的能力证据。

也就是说，这里的担心点可以更准确地收敛为：**仅靠运行前 AST / 字符串检查，不能百分百证明运行时不会导入内部 helper**。当前检查能抓直接写出来的违规 import，也能抓一部分简单动态 import；但如果生成代码在运行时用更复杂的方法拼模块名、调用未覆盖的加载 API，或者导入 denylist 没覆盖但仍可能泄露项目内部解题能力的模块，静态检查就可能漏掉。这个风险只有在 `PYTHONPATH=src` 让内部包运行时可见的情况下才真正成立。

影响：

当前 2026-06-12 失败不是 helper 污染导致；但后续如果真实 API 通过，仍需要人工检查生成 `solve.py` 是否绕过静态 denylist。否则 `benchmark_profile=no_helper` 与真实执行边界可能不一致，污染 no-helper pass rate。

最小修复建议：

- 不建议把“完全不注入项目 `src`”作为当前优先修复方案。这个方向理论上隔离最强，但在当前工程里不够贴合实际：真实 API runner 和 pytest 验证链路仍需要项目包，例如 schema / validation / sandbox / pytest 入口都依赖 `tablecodeagent` 代码；强行移除 `PYTHONPATH=src` 很可能先打断验证基础设施，而不是只隔离生成的 `solve.py`。如果后续要尝试这种方案，应作为单独架构改造评估，而不是本轮最小修复。
- 更现实的最小方案是在 sandbox 中增加运行期 import hook。含义是：即使 `PYTHONPATH=src` 仍然保留，Python 真正执行 `solve.py` 时也额外安装一层 import 拦截规则；一旦运行时尝试导入 `tablecodeagent.workflow`、`tests.test_workflows`、旧 `tablecodeagent.workflows`、`tablecodeagent.product_agent` 或等价 helper 路径，就立刻失败并记录 `helper_usage_forbidden`。这样可以覆盖一部分 AST 静态检查漏掉的运行期动态导入。
- 在 result/trace 中记录 `helper_usage_check_strategy` 和 `helper_usage_checked=true`，方便后续审计。含义是每次真实 API 结果都明确写清楚本次用了哪些 helper 防线，例如 `static_marker_scan`、`ast_import_scan`、`runtime_import_hook`；这样后续看到一次 no-helper 通过时，可以判断它是只经过静态检查，还是也经过运行期 import hook。

验证建议：

- 增加恶意 `solve.py` 测试：`".".join(["tests","test_workflows","finance_operations"])`、`getattr(importlib, "import_module")(...)`、从 `sys.modules` 或 `runpy` 间接加载 helper，都应失败。
- 对合法 no-helper `solve.py` 保持通过，避免把普通 `pandas/json/pathlib` 解法误杀。

是否阻断后续动作：

不影响修复 `missing_po` 本地回归，但会挡住后续把任何真实 API 通过结果写成无需人工审计的 no-helper 能力证据。

### 中：Windows 长 stdout/stderr 已有截断与 UTF-8，但完整长日志没有稳定落盘

位置：

- [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L69)
- [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L148)
- [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L169)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L715)
- [logger.py](../../src/tablecodeagent/tracing/logger.py#L121)
- [benchmark_runner.py](../../src/tablecodeagent/benchmark/benchmark_runner.py#L108)

证据：

- sandbox allowlist 已保留 `PYTHONIOENCODING` 和 `PYTHONUTF8`，见 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L29) 到 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L30)，并在 `_safe_env()` 默认设置 UTF-8，见 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L103) 到 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L111)。
- `subprocess.run()` 已使用 `encoding="utf-8", errors="replace"`，见 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L169) 到 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L176) 和 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L237) 到 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L244)。
- 长输出会通过 `_truncate()` 截断，见 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L69) 到 [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L76)；真实 API runner 对 `solve.py` 和 pytest 使用 `max_output_chars=40000`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L715) 和 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L727)。
- result 只暴露摘要字段，见 [logger.py](../../src/tablecodeagent/tracing/logger.py#L121) 到 [logger.py](../../src/tablecodeagent/tracing/logger.py#L127)；完整 stdout/stderr 超过上限后会在 trace 内被截断，当前没有稳定的 `stdout_path` / `stderr_path` artifact。
- 历史 v0.0.4 报告也把长日志输出列为仍需后续处理的边界，见 [fix-report-v0.0.4-20260608.md](fix-report-v0.0.4-20260608.md#L313) 到 [fix-report-v0.0.4-20260608.md](fix-report-v0.0.4-20260608.md#L327)。

影响：

目前 Windows 编码问题已明显缓解，本轮本地回归也通过；但如果后续真实 API 多轮稳定性测试出现长 traceback、长 JSON、长表格预览或大量 pytest 输出，超过截断上限的原文会丢失，复盘只能依赖摘要和尾部片段。PowerShell 控制台仍不适合作为完整证据层。

最小修复建议：

- sandbox 对 `run_python` 和 pytest 分别写入 `stdout.log`、`stderr.log` 或 `run_python.stdout.txt`、`pytest.stderr.txt`，trace/result 只记录摘要、截断标记和日志路径。
- 将 `output_truncated` 提升到 result 顶层或 `run_python` / `run_tests` 摘要中，避免审查时必须打开完整 trace 才知道日志是否被截断。
- README 或 runner help 后续补 Windows PowerShell 下的真实 API Python 入口命令，不只依赖 Bash 脚本。

验证建议：

- 增加 sandbox 长 stdout/stderr 测试：输出超过 `max_output_chars`，断言返回摘要被截断、完整日志文件存在、日志文件 UTF-8 可读。
- 增加 PowerShell 本地命令示例 smoke，确认不依赖 Bash。

是否阻断后续动作：

不影响 `missing_po` 本地修复；会影响多轮真实 API 稳定性测试的证据完整性。

### 中：`api_called` 归因仍可能覆盖 prompt 构造阶段失败

位置：

- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L531)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L678)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L769)

证据：

- `_task_prompt()` 会读取 task、枚举文件并构造公开输出契约，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L531) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L558)。
- `trace["api_called"] = True` 写在 `await agent.run_once(_task_prompt(workspace))` 之前，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L678) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L680)。Python 会先求值 `_task_prompt(workspace)`，如果 prompt 构造失败，trace 仍可能记录 `api_called=true`。
- 异常处理会根据 `api_called` 决定是否写 `api_error_type`，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L769) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L775)。

通俗解释：

`api_called` 这个字段本来应该回答一个很具体的问题：这次 run 到底有没有真的调用外部模型 API。它会影响后续判断：这是 API / 网络 / 模型调用失败，还是本地 runner 自己在准备阶段就失败了。

一次真实 API benchmark 大致有两个阶段。第一阶段是本地准备：复制 task workspace、读取 `task.json`、生成要发给模型的 prompt、注入公开 schema。第二阶段才是调用模型 API，让模型写代码。现在代码在调用 `agent.run_once(...)` 前就先把 `trace["api_called"]` 设成 `True`，但传给 `run_once` 的 `_task_prompt(workspace)` 还要先在本地执行。如果 `_task_prompt()` 因为 task 文件损坏、schema 构造失败或 workspace 异常而报错，实际 API 还没发出去，trace 却可能已经写成 `api_called=true`。

这会造成归因混乱。比如真正原因是“本地 prompt 构造失败”，结果报告却看起来像“已经调用了 API，然后 API 流程失败”。对真实 API benchmark 来说，这个差别很重要：前者应该修 runner 或 task，本地就能复现；后者才可能需要查 env、网络、provider 或模型响应。

影响：

当前 2026-06-12 run 已真实调用 API，因此不影响该 run 结论；但后续如果 workspace、task prompt 或 schema 注入阶段失败，结果可能误标为 API 已调用，影响成本归因、失败分类和真实 API 可用性判断。

最小修复建议：

- 先构造 `prompt = _task_prompt(workspace)`，成功后再进入 `agent.run_once(prompt)`。
- 将字段拆成 `api_request_started` 与 `api_called`，或在 provider request 真正发起处设置 `api_called=true`。
- 对 prompt 构造失败单独使用 `failure_type=prompt_construction_failed` 或 `runner_preflight_failed`。

验证建议：

- monkeypatch `_task_prompt()` 抛错，断言 `api_called=false` 且 `failure_type` 不写成 API 错误。
- monkeypatch `Agent.run_once()` 在请求前/请求后分别抛错，断言归因字段不同。

是否阻断后续动作：

不影响 `missing_po` 本地修复；会影响失败归因字段的长期可信度。

## 未发现明确问题的区域

- `finance_operations_001` 的公开合同已经直接写出 NaN-like 缺失值归一化、PO 缺失三处落点和 no-helper 禁止 helper，见 [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L52)、[task.json](../../benchmarks/tasks/finance_operations_001/task.json#L66) 和 [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L103)。
- pytest 对 `missing_po_invoice_ids`、`INV-1006.exception_tags` 和 `exceptions["missing_po"]` 都有断言，见 [test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L51)、[test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L85) 和 [test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L94)。
- runner 没有把历史真实 API 失败包装为通过；`failure_type=pytest_failed` 被保留在 [results.jsonl](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/results.jsonl)。
- no-helper prompt 不公开 `expected.json`、workflow helper 或 product workflow 工具，见 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L538) 到 [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L557)。
- 本轮本地 `tests/test_unit tests/test_integration` 回归通过；这只证明项目本地代码和回归测试当前稳定，不证明真实 LLM Agent 已通过 finance no-helper benchmark。

## 审查范围

本轮只进行 code review。唯一写入文件是本报告。未修改源码、测试、README、task contract、Pydantic schema、pytest、runner、sandbox、trace、validation、benchmark task 或历史报告。

已按要求先运行：

```powershell
rg --files .agents .codex docs benchmarks src tests scripts
```

重点阅读和审查：

- [.codex/AGENTS.md](../../.codex/AGENTS.md#L7)
- [README.md](../../README.md#L368)
- [tablecodeagent_architecture.md](tablecodeagent_architecture.md#L21)
- [why_table_code_agent.md](why_table_code_agent.md#L294)
- [code-review-v0.0.4-20260608.md](code-review-v0.0.4-20260608.md#L13)
- [code-review-v0.0.5-20260608.md](code-review-v0.0.5-20260608.md#L47)
- [fix-report-v0.0.4-20260608.md](fix-report-v0.0.4-20260608.md#L313)
- [fix-report-v0.0.5-20260608.md](fix-report-v0.0.5-20260608.md#L154)
- [fix-report-v0.0.5-20260612.md](fix-report-v0.0.5-20260612.md#L113)
- [task.json](../../benchmarks/tasks/finance_operations_001/task.json#L49)
- [test_solution.py](../../benchmarks/tasks/finance_operations_001/tests/test_solution.py#L26)
- [answer_models.py](../../src/tablecodeagent/benchmark/answer_models.py#L100)
- [real_api_code_agent.py](../../src/tablecodeagent/benchmark/real_api_code_agent.py#L561)
- [benchmark_runner.py](../../src/tablecodeagent/benchmark/benchmark_runner.py#L62)
- [sandbox.py](../../src/tablecodeagent/runtime/sandbox.py#L103)
- [dependency.py](../../src/tablecodeagent/runtime/dependency.py#L137)
- [logger.py](../../src/tablecodeagent/tracing/logger.py#L85)
- [finance_operations.py](../../tests/test_workflows/finance_operations.py#L716)
- [test_finance_operations_simulated_agent_outputs.py](../../tests/test_integration/test_finance_operations_simulated_agent_outputs.py#L37)
- [test_finance_operations_workflow_expected_check.py](../../tests/test_integration/test_finance_operations_workflow_expected_check.py#L5)
- [test_sandbox_runs_fixed_solve_py.py](../../tests/test_integration/test_sandbox_runs_fixed_solve_py.py#L90)
- [test_real_api_code_agent_contract.py](../../tests/test_unit/test_real_api_code_agent_contract.py#L138)

## 本轮风险地图

- `finance_operations_001` 公开合同：合同文本已经覆盖 NaN-like 缺失归一化、PO 缺失和 required exception types；当前主要风险不是合同完全缺失，而是 required exception coverage 不够机器可校验。
- Pydantic schema：能约束结构、字段类型、枚举大小写和 `due_date` NaN-like 字符串；不能保证 `missing_po` 三处落点一致。
- simulated Agent：覆盖了多类错误，但缺少 2026-06-12 精确失败形态。
- sandbox / Windows：UTF-8、`errors="replace"`、截断和摘要已有；完整长日志 artifact 仍不足。
- failure classification：2026-06-12 历史 run 保留 `pytest_failed`；但 `api_called` 前置阶段仍有漂移风险。
- no-helper 边界：prompt、tool denylist、AST 检查已有；运行期仍能接触项目 `src`，后续通过结果仍需更强隔离或审计。
- 文档当前性：README 当前最高优先级 TODO 与本轮审查任务一致；后续修复完成后应删除或改写该 TODO，本轮不修改 README。

## 外部依据

本轮调用了 `$web-search`。外部资料只用于校准评审标准，所有 finding 均落回本仓库证据。

- OpenAI Evaluation best practices：强调 task-specific eval、自动化评分和日志记录。用于支撑“真实 API 暴露的问题应先转成本地 regression，而不是反复用 API 发现同类问题”。来源：<https://developers.openai.com/api/docs/guides/evaluation-best-practices>
- OpenAI Structured Outputs：结构化输出保证模型遵守提供的 JSON Schema，但不等价于业务语义完整。用于支撑 schema 与 pytest/semantic validation 分层。来源：<https://developers.openai.com/api/docs/guides/structured-outputs>
- Python `subprocess` 官方文档：`subprocess` 管理 stdout/stderr pipe，`encoding` 和 `errors` 控制 text mode 解码。用于对照 Windows stdout/stderr 兼容性。来源：<https://docs.python.org/3/library/subprocess.html>
- pandas missing data / `isna` 官方文档：`NaN`、`None`、`NaT` 属于常见缺失值检测口径。用于支撑 `missing_value_normalization` 的必要性。来源：<https://pandas.pydata.org/docs/reference/api/pandas.isna.html>
- Pydantic validators 官方文档：validator 可用于对字段值执行条件检查。用于支撑后续用 Pydantic 或 semantic validation 表达跨字段业务约束。来源：<https://pydantic.dev/docs/validation/latest/concepts/validators/>
- Oracle Payables invoice matching 文档：invoice matching 是把 invoice 与 purchase order、receipt 等关联，确保支付对象符合已订购/已接收内容。用于支撑 `missing_po` 不是普通格式问题，而是财务/采购运营异常。来源：<https://docs.oracle.com/en/cloud/saas/financials/25c/fappp/matching-invoice-lines.html>

## 测试缺口

- 缺少“只漏 `missing_po` exception row”的 simulated Agent 失败用例。
- 缺少 `missing_po_invoice_ids`、invoice `exception_tags`、`exceptions.related_ids` 三者一致性的 schema 或 semantic validation 单测。
- 缺少 no-helper 运行期 import hook / 更复杂动态导入绕过测试。
- 缺少 sandbox 长 stdout/stderr 完整落盘测试。
- 缺少 `_task_prompt()` 前置失败时 `api_called=false` 的归因测试。

## 本轮验证方式

本轮运行了完整本地回归：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration -q
```

结果：

```text
40 passed in 14.05s
```

该结果不是 finance no-helper 真实 API 通过结论。

## 真实 API 测试记录

本轮真实 API 调用次数：0。

原因：

- 只读审查和本地回归已经足够形成严重 finding：2026-06-12 真实失败的精确形态缺少 simulated Agent 本地回归。
- README 最高优先级任务要求先补本地回归，再决定是否真实 API 复测，见 [README.md](../../README.md#L368)。
- 本轮没有修改任何代码或测试，直接运行真实 API 不能修复本地前置缺口。

历史真实 API 证据只作为历史证据引用，不写成本轮验证：

- `result_dir`：[20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612)
- `results.jsonl`：[results.jsonl](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/results.jsonl)
- `summary.json`：[summary.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/summary.json)
- `trace_path`：[finance_operations_001.real_api_code_agent.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/traces/finance_operations_001.real_api_code_agent.json)
- `workspace_path`：[finance_operations_001.real_api_code_agent](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent)
- `generated_code_path`：[solve.py](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/solve.py)
- `answer_path`：[answer.json](../../benchmarks/results/real_api_code_agent/20260612-065708__model-deepseek-v4-flash__tasks-v0.0.5-product-loop-boundary-20260612/workspaces/finance_operations_001.real_api_code_agent/answer.json)
- `api_called=true`
- `schema_check.passed=true`
- `run_python.exit_code=0`
- `pytest_exit_code=1`
- `failure_type=pytest_failed`
- `missing_po` 覆盖状态：`data_quality.missing_po_invoice_ids` 和 invoice `exception_tags` 已覆盖；`exceptions` 中缺少 `missing_po` row，未完整覆盖。

## 真实 API 后续边界

- 修复前不要运行新的真实 API。先补本地 simulated Agent 精确失败、schema/semantic validation 和 runner 归因测试。
- 修复后第 1 次真实 API 只用于确认当前 no-helper 公开契约下 `finance_operations_001` 是否仍暴露 `missing_po` 或相关 failure。
- 如果第 1 次结果已经足够支撑结论，不自动跑第 2 次。
- 如果需要第 2 次，只能用于确认不稳定或复现性；第 2 次后必须停止。

## 建议修复优先级

1. 严重：补 `missing_po` exception row 缺失的 simulated Agent 精确回归，并确认 pytest 能本地捕获。
2. 高：补 Pydantic semantic validation 或独立 semantic validation，覆盖 `missing_po` 三处一致性和 required exception coverage。
3. 高：收紧 no-helper 运行期 import 边界，减少未来通过结果的 helper 污染审计成本。
4. 中：为 sandbox 长 stdout/stderr 增加完整日志 artifact 与 result 截断标记。
5. 中：修正 `api_called` 前置失败归因边界。
6. 低：修复完成后更新 README Roadmap，删除或改写已完成的最高优先级 TODO；本轮不修改 README。

## 结论

当前仓库本地 unit/integration 回归通过，但 `finance_operations_001` 后续真实 API 复测仍被本地回归缺口挡住。最关键的问题不是 `task.json` 完全没有写 `missing_po`，而是 schema 和 simulated Agent 回归还没有覆盖 2026-06-12 真实 run 的精确失败形态：模型已写 `missing_po_invoice_ids` 和 invoice tag，但漏掉 `missing_po` exception row。下一步应先修本地回归与语义校验，再决定是否启动最多两次的受控真实 API 复测。
