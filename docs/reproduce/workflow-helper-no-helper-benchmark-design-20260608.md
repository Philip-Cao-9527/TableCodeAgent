# Workflow Helper 与 No-helper Benchmark 设计说明

本文解释 TableCodeAgent 中 `src/tablecodeagent/workflows/` 的定位、为什么真实评测禁止调用 workflow helper，以及如何区分“内部 deterministic workflow 通过”和“真实 Agent 自主完成任务”。本文面向项目复盘、面试口述和后续开发约束，不新增代码能力。

## 可直接口述回答（快速复习总结）

第一，TableCodeAgent 里的 workflow helper 不是错误设计，而是内部参考实现。比如 `run_growth_campaign_audit()`、`run_credit_risk_scoring()`、`run_finance_operations()` 这类函数，本质上是项目作者提前写好的确定性业务流程：它们会读取固定任务目录下的数据表，按人工定义的业务规则完成清洗、聚合、对账、评分、异常识别和结构化输出，然后再和 `expected.json` 或 pytest 规则做校验。它们的价值是让项目有一套可靠的标准答案生成路径，也就是常说的 deterministic oracle 或 fixture oracle。没有这类内部 workflow，很多任务 contract、pytest 断言和模拟 Agent 错误用例都很难设计，因为我们无法稳定知道一个合法答案应该长什么样。

第二，no-helper benchmark 要测的不是“模型会不会调用现成标准答案函数”，而是“模型能不能基于公开任务、数据文件和输出 schema 自己生成可执行代码”。真实评测入口 `real_api_code_agent` 的目标是让模型在 benchmark workspace 中生成 `solve.py`，运行后写出 `answer.json`，再由 Pydantic schema、外部 pytest 或显式 validator 校验。这里的关键是 no-helper：模型可以看到 `task.json`、数据文件和公开的 `output_contract`，但不能看到 `expected.json`，也不能 import `tablecodeagent.workflows` 或调用 `build_*_report()` 这类项目内部解题 helper。这样评测才是在测模型的实时决策、代码生成和表格处理能力。

第三，workflow helper 和 no-helper benchmark 的区别，可以用考试来记。内部 workflow 像老师手里的标准答案和评分细则；no-helper benchmark 像学生考试。老师当然需要标准答案来批改试卷，但学生不能直接拿标准答案函数来答题。如果模型在 `solve.py` 中写 `from tablecodeagent.workflows.finance_operations import run_finance_operations`，然后一行调用输出 `answer.json`，它可能能通过测试，但这证明的是“模型会复用项目 helper”，不是“模型会自主完成财务运营多表对账”。这种结果只能叫 helper-assisted，不能和 no-helper 真实能力混在一个 pass rate 里。

第四，主 Agent Loop 自动能力强调的是运行时自主决策。用户给 Agent 一个任务后，Agent 应该自己判断读哪些文件、调用哪些表格工具、如何写 pandas/numpy 代码、如何运行代码、如何生成 `answer.json`、失败后如何根据 stdout/stderr/pytest 信息修正。也就是说，能力来自模型在工具交互过程中的计划、行动和反馈闭环，而不是来自一个已经写好的业务函数。TableCodeAgent 现在的真实 API benchmark 正是围绕这个闭环设计：读 task、生成代码、沙箱执行、schema 检查、pytest 检查、trace 记录和 failure_type 归因。

第五，workflow helper 仍然非常重要，只是要放在正确位置。它适合用于本地 deterministic 回归、expected 设计、pytest 口径对齐、模拟 Agent 错误输出、业务规则回归测试和文档解释。比如财务运营场景里，本地 workflow 能帮助我们确认发票、回款、争议、调整、账龄、未核销现金、授信额度和 ECL 的计算口径；模拟 Agent 测试能提前暴露 missing value、枚举大小写、字段缺失、金额精度和路径读取问题。这样可以减少真实 API 被反复用来发现本地可提前捕获的问题。

第六，README、fix-report 和 code-review 报告必须把证据层级分清楚。`tests/test_integration/test_*_workflow_expected_check.py` 通过，只能说明内部 workflow 和 fixture 规则对齐；模拟 Agent 输出被 schema/pytest 捕获，只能说明本地防线有效；真实 no-helper benchmark 通过，才说明本轮模型在不暴露 helper 的条件下生成代码并通过评测。三类证据都重要，但不能互相替代。最容易犯的错误是把 deterministic workflow 通过写成“真实 LLM Agent 已通过”，或者把 helper-assisted smoke 写成 no-helper 能力。

第七，当前项目已经把 no-helper 约束写进多个位置。`real_api_code_agent.py` 中固定 `BENCHMARK_PROFILE = "no_helper"`，prompt 写明 `helper_hints_exposed: false`，并明确禁止 import 或调用 `tablecodeagent.workflows`、`build_*_report` 等 workflow helper。生成代码后 runner 还会扫描 `solve.py` 中的 forbidden helper markers。README 也写明真实评测不会向模型公开 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion` 或项目工作流辅助函数。部分 task contract 也写明禁止读取 `expected.json` 和禁止调用项目内部解题 helper。后续还可以加强 AST/import hook 级防护，防止动态 import 绕过字符串检查。

第八，一句话总结：**workflow helper 是内部标准答案和测试基准，no-helper benchmark 是模型自主解题能力评测；两者都需要，但必须分开统计、分开汇报、分开解释。** 这样项目既能保持工程可验证性，又不会夸大真实 Agent 能力。

## 详细原理讲解（通俗版）

### 1. 先从最基础的问题讲起：为什么表格 Agent 需要 workflow 和 benchmark

TableCodeAgent 要解决的是复杂表格任务，而不是简单的“读一张 CSV 回答一个数”。复杂表格任务通常包含多层要求：先要理解有哪些表，每张表有哪些字段，字段代表什么业务含义；再要判断哪些字段是主键、哪些字段可以 join，join 后会不会出现行数膨胀；还要检查缺失值、重复值、异常值、时间窗口、贷前贷后字段隔离、枚举值、金额精度、账龄分桶、风险分层等细节。最后，模型还必须把结果写成一个符合契约的 `answer.json`，让程序可以自动评分。

如果只让大模型直接读表并回答，它可能生成一段看起来很合理的解释，但里面的数字、口径和字段可能不对。表格任务最麻烦的地方在于：很多错误不是语法错误，代码能运行，JSON 也能生成，但业务含义错了。例如信贷风控里，模型可能把缺失年龄也算作非法年龄；财务运营里，模型可能把空 PO 读成字符串 `"nan"` 后没有当缺失处理；营销增长里，模型可能忘记检查 treatment/control 分布是否严重失衡。这些问题需要程序化校验，而不只是看自然语言解释。

因此 TableCodeAgent 需要两类东西。第一类是内部 workflow，也就是人工写好的确定性参考实现。第二类是真实 Agent benchmark，也就是让模型自己写代码、运行代码、通过测试。内部 workflow 让我们知道“正确口径应该是什么”；真实 benchmark 让我们知道“模型在不知道内部答案函数的情况下能不能自己做出来”。这两个东西相互配合，但不是同一个概念。

### 2. 什么是 deterministic workflow

Deterministic workflow 可以翻译成确定性工作流。确定性意味着：给它同样的输入，它总是按固定规则输出同样的结果。比如 `run_growth_campaign_audit(task_dir)` 会读取营销增长任务目录中的用户表、曝光表、订单表、奖励表，然后调用内部的 `build_growth_campaign_audit_report()`，生成行数统计、join cardinality、分组分布、SMD、补贴异常、时间窗口对齐、warnings 等结构化字段。然后它再读取 `expected.json` 做 validation，把 validation 放进 report。

这个流程像一台固定规则机器。它不会像 LLM 一样临场推理，也不会根据自然语言自由发挥。它的优点是稳定、可复现、容易调试、容易写测试；缺点是它不能证明模型能力，因为它本身就是人提前写好的答案路径。

财务运营 workflow 也是类似的。它会读取 invoices、payments、customers、disputes、adjustments、policy 多张表，然后按固定业务规则处理发票金额、付款匹配、争议款、调整单、账龄、未核销现金、客户信用额度、预期信用损失等。这个 workflow 对项目很关键，因为它能告诉我们一个高质量 `answer.json` 应该包含哪些字段、哪些异常类型必须被识别、哪些金额口径必须保留两位小数。

可以把 deterministic workflow 理解成“老师手里的参考答案生成器”。老师要出题、验题、写评分规则，就需要这套参考答案。但学生考试时不能直接调用参考答案生成器。

### 3. 什么是 no-helper benchmark

Benchmark 是评测。No-helper benchmark 是一种更严格的评测：模型不能调用项目内部已经写好的解题 helper，只能基于公开任务描述、数据文件和输出契约自己生成代码。

在 TableCodeAgent 当前设计里，真实 API benchmark 的固定流程大致是：

1. runner 读取任务目录中的 `task.json`。
2. runner 把 `expected.json` 从 workspace 中移走，只保留在 traces 目录作为外部评分依据。
3. runner 构造 prompt，把 workspace 路径、可用文件、公开 `output_contract` 和允许库告诉模型。
4. 模型必须生成 `solve.py`。
5. `solve.py` 在沙箱里执行，写出 `answer.json`。
6. runner 用 Pydantic JSON Schema 检查结构。
7. runner 用外部 pytest 或 validator 检查业务口径。
8. runner 写出 trace、results、workspace、failure_type 等证据。

这个流程的核心是：模型必须自己完成解题代码，而不是复用项目作者提前写好的完整 workflow helper。这里的“自己完成”不是说不能用 pandas、numpy、json、pathlib 这些通用库；恰恰相反，表格任务应该优先用成熟库处理。No-helper 禁止的是 `tablecodeagent.workflows`、`build_growth_campaign_audit_report()`、`build_finance_operations_report()` 这类项目内部答案函数。

如果允许调用 workflow helper，评测难度会大幅下降。模型本来需要自己写 join、groupby、字段检查、异常识别、输出结构组装；现在只要 import 一个现成函数再 json.dump 即可。这就像本来要考学生做完整证明题，结果直接把证明模板函数给了学生。这样通过了不代表学生掌握了证明过程，只代表学生会调用模板。

### 4. 为什么 helper-assisted 和 no-helper 不能混在一起

Helper-assisted 指模型可以看到或调用项目 helper。它不是没有价值。它可以验证真实 API 是否可达、Agent 是否会读任务、是否会写文件、沙箱能否运行、pytest 能否评分、trace 是否能记录。这对于早期 MVP smoke 很有用。

但 helper-assisted 不能证明模型自主完成了复杂表格推理。因为主要业务逻辑已经在 helper 里了。模型只是在调用项目已有 API。

No-helper 则更接近真实能力评测。模型要自己读 task 和数据，理解业务口径，写 `solve.py`，再通过 schema 和 pytest。它的失败更有诊断价值：如果失败在 schema，说明输出结构不对；如果失败在 pytest，说明业务口径理解不对；如果失败在 run_python，说明代码执行不稳定；如果失败在 dependency，说明环境不完整；如果失败在 api_env_missing，说明没有真正调用模型。这样 trace 和 failure_type 才能帮助我们判断下一步该改 task contract、改 runner、改测试，还是改模型提示。

两者不能混在同一个通过率里。假设 helper-assisted 通过率是 90%，no-helper 通过率是 30%，如果把它们混起来说“项目真实 Agent 通过率很高”，就是误导。正确做法是分开写：

- helper-assisted：证明工程链路和项目 helper 可复用。
- no-helper：证明模型自主代码生成和表格推理能力。
- deterministic workflow：证明内部参考实现和 fixture 规则正确。
- simulated Agent outputs：证明 schema/pytest 能提前捕获常见错误。

### 5. 主 Agent Loop 自动能力到底是什么

主 Agent Loop 自动能力不是“仓库里有一个能解决任务的函数”。它指的是 Agent 在运行时完成一个闭环。这个闭环包括：

1. 接收用户或 benchmark prompt。
2. 观察当前工作目录和可用文件。
3. 选择读取 `task.json`、CSV、测试文件或 schema。
4. 决定是否调用 `load_table`、`profile_table`、`query_table` 或其他表格质量工具。
5. 判断需要写什么 Python 代码。
6. 生成 `solve.py`。
7. 运行或让 runner 运行代码。
8. 根据 stdout、stderr、pytest 失败摘要或 schema errors 修正。
9. 最终生成满足契约的 `answer.json`。
10. trace 记录整个过程，便于复盘。

这个过程强调实时决策和工具交互。模型不是提前知道答案函数，而是在当前上下文里规划和行动。这也是为什么 no-helper benchmark 要禁止 workflow helper：只有去掉现成答案函数，才能观察 Agent 是否真的完成了上述闭环。

从工程角度看，主 Agent Loop 的价值不是“模型一次性说对答案”，而是“模型能在可控工具和反馈下逐步逼近正确执行结果”。表格任务尤其需要这种机制，因为表格错误往往需要程序运行和测试才能暴露。

### 6. Workflow helper 为什么仍然必须保留

虽然 no-helper benchmark 禁止模型调用 workflow helper，但这不意味着 workflow helper 没有价值。恰恰相反，它们是项目质量控制的核心。

第一，workflow helper 是 expected 和 pytest 的来源。没有内部参考实现，很难写出严谨的业务断言。比如财务运营任务要判断哪些 invoice 是重复、哪些 payment 是 future-dated、哪些 adjustment 是 unmatched、哪些客户超过 credit limit，这些都需要一个稳定口径。

第二，workflow helper 帮助设计 task contract。真实 API 反复失败时，经常不是模型完全不会做，而是公开契约没有把隐藏口径说清楚。例如 `invalid_age_count` 是否包含缺失年龄，`field_type_issues` 是否包含 target 列缺失，`duplicate_customer_count` 是统计重复组数还是涉及的申请行数。这些问题可以通过内部 workflow 和 pytest 对齐后，再写进公开 contract。

第三，workflow helper 能支持模拟 Agent 错误。比如把正确答案复制一份，故意改错枚举大小写、删掉字段、改错金额、把空值写成 `"nan"`，然后验证 Pydantic schema 或 pytest 能不能抓住。这种测试比直接跑真实 API 更便宜，也更可控。

第四，workflow helper 是回归保护。如果后续改了表格读取、缺失值归一化、金额精度、日期解析或业务规则，本地测试可以先发现内部 reference 是否漂移。这样可以避免每次都靠真实 API 暴露基础问题。

所以正确关系是：workflow helper 服务于测试和评分，no-helper benchmark 服务于能力证明。它们不是互斥关系，而是分工不同。

### 7. 项目里禁止调用 workflow helper 的落点

当前项目已经在多个层面写了 no-helper 约束。

第一，runner 层。`real_api_code_agent.py` 中有 `BENCHMARK_PROFILE = "no_helper"`。构造 prompt 时会写 `helper_hints_exposed: false`，并明确要求模型不要读取 `expected.json`，不要 import 或调用项目 workflow helper，例如 `tablecodeagent.workflows` 或 `build_*_report`。这说明评测目标是基于 task、数据和公开 schema 自主生成 `solve.py`。

第二，生成代码检查层。runner 有 `FORBIDDEN_HELPER_MARKERS`，会扫描生成的 `solve.py` 是否包含 `tablecodeagent.workflows`、`build_growth_campaign_audit_report`、`build_credit_risk_scoring_report` 等标记。如果命中，就应该归为 helper 使用违规。这一层是基础防线。

第三，README 层。README 写明真实 API 评测采用“不公开项目内部解题函数”的口径，runner 不向模型公开 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion` 或项目工作流辅助函数。这是对外口径。

第四，task contract 层。比如 finance task 的 schema description 写明真实 benchmark 禁止读取 `expected.json`，禁止 import 项目内部 workflow 或调用项目内解题 helper。这让任务本身也带有评测边界。

第五，报告层。`docs/reproduce` 中多个 fix-report 和 code-review 都反复强调：内部 workflow helper 仅用于单元/集成测试，真实 benchmark 必须 no-helper，不能把 helper-assisted smoke 写成模型自主完成完整 workflow。

后续可以继续加强的是：当前 forbidden marker 更像字符串 denylist，如果模型用动态 import 或字符串拼接绕过，防护仍不够强。因此后续可以增加 AST 检查、import hook 或 no-helper sandbox 隔离，让生成代码运行时根本无法 import `tablecodeagent.workflows`。

### 8. 如何在 README 和报告里准确表达

推荐表达：

- “项目已实现内部 deterministic workflow，用于 fixture oracle、业务规则回归和 expected/pytest 对齐。”
- “真实 no-helper benchmark 不向模型公开 workflow helper，模型必须基于 task、数据和公开 schema 自主生成 `solve.py`。”
- “本地 workflow 测试通过不等于真实 LLM Agent 通过。”
- “模拟 Agent 错误测试通过说明本地 schema/pytest 防线有效，不等于真实模型已稳定通过。”
- “真实 API 单次通过只代表该 run 通过，不代表多轮稳定性。”

不推荐表达：

- “Agent 已经自动掌握财务运营 workflow。”除非有 no-helper 真实评测证据支持。
- “workflow 通过，所以真实 Agent 通过。”这是把内部 reference 和模型能力混淆。
- “helper-assisted 和 no-helper 放在一个通过率里。”这会让评测含义失真。
- “没有调用 expected.json 就一定是 no-helper。”如果调用了项目 workflow helper，即使没读 expected，也仍然降低了任务难度。

### 9. 一个具体例子：growth workflow

`run_growth_campaign_audit()` 会调用 `build_growth_campaign_audit_report(task_path)`，再读取 `expected.json` 做 validation。这非常适合内部测试，因为它能稳定生成标准 report，并确认 report 与 expected 对齐。

但如果真实 benchmark 里的模型直接调用它，就会出现两个问题。第一，它调用了内部完整解题函数，模型不需要自己写 join、SMD、outlier、time window 检查。第二，它的 wrapper 还会读取 `expected.json`，而 expected 是评测侧信息，模型不应该访问。即使真实 workspace 中 expected 被移走，模型也不应该依赖这种路径。

所以 growth workflow 的正确身份是：内部 oracle、测试工具、业务规则参考。真实 no-helper 里，模型应自己读取 users、campaign_exposure、orders、rewards 等数据，自己实现审计逻辑，并输出满足 schema 和 pytest 的 answer。

### 10. 一个具体例子：finance workflow

`finance_operations` 的内部 workflow 覆盖很多业务细节：发票金额、回款匹配、未核销现金、争议、调整、客户状态、信用额度、账龄、PO、账期、ECL 等。它非常适合作为复杂场景的 reference，因为财务任务比单表聚合更容易出现口径漂移。

但真实 finance no-helper benchmark 仍然要求模型自己处理这些表。模型可以使用 pandas 读 CSV、join、groupby、计算金额；可以读取 `task.json` 的公开 output contract；可以根据 schema 输出结构化 JSON。但不能 import `build_finance_operations_report()` 直接生成答案。否则评测就变成“模型是否知道调用内部财务 helper”，而不是“模型是否能自主理解和实现财务运营分析”。

这也是为什么 finance 任务需要本地模拟 Agent 错误测试。真实 API 很贵，而且失败原因复杂。通过模拟缺失字段、错误枚举、错误金额、`nan` 字符串、路径误读等问题，我们可以先把 schema 和 pytest 防线做牢，再消耗有限的 API 次数。

### 11. 最终记忆抓手

可以用一句话记住整个设计：

**workflow 是老师答案，no-helper 是学生考试，trace 是监考录像，schema/pytest 是评分器。**

老师答案必须存在，否则无法评分；学生考试不能直接抄老师答案，否则无法证明能力；监考录像必须保存，否则失败后无法复盘；评分器必须严格，否则看起来像答案的 JSON 也可能业务上是错的。

## 面试官可能追问与回答

### 追问 1：既然 workflow helper 不能给模型用，为什么还要写它？

因为它是内部参考实现和回归测试基础。复杂表格任务需要一个稳定 oracle 来设计 expected、pytest 和业务口径。没有 workflow helper，很多测试只能凭感觉写，后续模型失败也很难判断是模型错、contract 不清楚，还是测试自己错。它不用于 no-helper 解题，但用于出题、验题和本地回归。

### 追问 2：no-helper benchmark 和 helper-assisted benchmark 的区别是什么？

No-helper 只给模型 task、数据和公开 schema，要求模型自己生成 `solve.py`；helper-assisted 会暴露或允许调用项目内部 helper。前者测自主代码生成和表格推理能力，后者更适合 smoke 工程链路，比如 API 调用、写文件、沙箱执行和 trace 是否跑通。两者不能混成一个通过率。

### 追问 3：怎么保证模型没有调用 workflow helper？

当前有三层约束：prompt 明确禁止、task/README 文档明确 no-helper 口径、runner 扫描生成的 `solve.py` 中的 forbidden helper markers。后续还应加强 AST 检查和运行期 import hook，因为纯字符串 denylist 可能被动态 import 绕过。

### 追问 4：主 Agent Loop 自动能力到底看什么证据？

看真实 API run 的证据链：`api_called=true`、`benchmark_profile=no_helper`、`helper_hints_exposed=false`、生成了 `solve.py`、沙箱执行成功、`answer.json` 存在、Pydantic schema 通过、pytest 或 validator 通过、`failure_type=null`，并且人工或自动检查确认生成代码没有调用项目内部 helper。单元测试或 deterministic workflow 通过不是同一层证据。

### 追问 5：如果 no-helper 失败，应该优先改模型还是改 task contract？

要看失败类型。如果 schema 错，先检查 output_contract 是否清楚；如果 pytest 业务断言错，先判断业务口径是否在 prompt 可见信息里说清楚；如果代码执行错，检查 sandbox、依赖和路径；如果模型读取了不该读的路径或调用 helper，收紧 no-helper 防护。不能简单把所有失败归因成模型差。

### 追问 6：当前项目还存在什么限制？

当前已经有表格工具、固定 workflow、本地测试、真实 API runner、trace 和 no-helper 口径，但仍有边界：analysis memory 和表格上下文压缩还未接入主链路；no-helper 防护仍需增强 AST/import hook；真实 API 通过性需要更多任务和多轮稳定性统计；内部 workflow 只能作为 reference，不能直接证明模型自主业务能力。
