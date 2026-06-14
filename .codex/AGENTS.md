# TableCodeAgent 项目级 Codex 指令

本文件只约束当前仓库 `TableCodeAgent`。

## 0. 执行环境前置规则

- 执行代码、测试或脚本前，必须先识别当前操作系统与 shell：Windows PowerShell 走 `.venv\Scripts\python.exe`、PowerShell 环境变量语法和 `.ps1` 脚本；Linux / AutoDL 走已激活的 conda/venv，或 `.venv/bin/python`、Bash 环境变量语法和 `.sh` 脚本。不要把 Bash heredoc、`source`、路径分隔符或 shell 语法直接复制到 PowerShell 命令中。
- 需要运行测试或项目代码时，先检查是否存在可用虚拟环境。Windows 优先使用仓库本地 `.venv\Scripts\python.exe`；Linux 优先使用已激活的 `tca`/conda/venv 环境，缺失时再按 README 或 setup 脚本创建 `.venv`。不得提交 `.venv/`、`venv/`、conda env 目录或本地生成的 packaging metadata。
- 跨平台代码中的文件读写必须显式指定 `encoding="utf-8"`，子进程和测试命令必须设置必要的 UTF-8 / BLAS 线程环境变量，例如 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`、`OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1`，避免 Windows GBK、Anaconda base 环境或第三方 pytest 插件污染测试结论。

## 1. 项目定位

- 本项目是面向复杂表格任务的轻量级 Coding Agent 项目。核心动机是：当任务从一次性小表问答升级到可复现、可验证、可审计、可迁移的表格数据处理、算法建模前置工作和业务决策推理时，仅靠通用 Coding Agent 的默认工具与默认提示容易失控；TableCodeAgent 要把这类任务显式组织成结构化、可执行、可校验、可记录轨迹的程序化工作流。
- 表格在本项目中不是狭义“数据分析报表”，而是风险评分、营销增长、智能定价、财务推理、运营决策、因果分析、实验评估和表格 benchmark 的样本与证据载体。回答或改文档时不要把项目缩窄成普通数据分析 Agent，也不要只说成机器学习agent项目。
- 当前工程主线是复用 `mini_claude` baseline，逐步加入表格工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。

## 2. 顶层代码生成约束

本项目优先追求可审查、可测试、职责清晰的增量实现。生成代码时必须先控制复杂度，再考虑功能堆叠。这里的“最小必要改动”不是“只改最少行数”，而是在满足工业场景业务口径、工程分层、可验证闭环和评测可信度的前提下，选择最小可落地方案；如果现有最小实现会公开解题 helper、弱化 benchmark 口径、放任输出契约漂移或掩盖真实失败，必须主动扩大到足以修正口径和调用链的范围。

- 不要一次性生成超长文件、超长函数或跨多个职责的大段代码；如果需求较大，先拆成小模块、小函数、小测试闭环。
- 面向工业场景设计代码时，必须优先保证业务语义、评测口径和工程边界正确，再谈改动规模。不能因为“少改一点”而保留会误导真实 Agent 能力、引入 helper-assisted benchmark的实现。
- 单个模块应只承载一个清晰职责。凡是同时包含工具协议、业务计算、执行调度、日志记录、评测统计、展示输出等多个方向的改动，必须先拆分边界，再接入调用链。
- 新增能力应优先放在对应领域模块中实现，再通过轻量 adapter 注册到 Agent Runtime；不要把核心计算、评测、trace、数据清洗、建模前处理等逻辑堆进通用入口或通用分发文件。
- 如果一个改动预计会显著放大已有文件体积，先说明拆分方案，并优先创建领域模块承接复杂逻辑。
- 大函数必须拆成可命名、可单测、可复用的小函数；每个函数应能用一句话说明输入、输出和失败方式。
- 生成 benchmark、runner、trace、validation 或 task 契约相关代码时，必须把“任务真实想测什么”写清楚并落到字段、目录、结果和报告口径中；真实 LLM Agent benchmark 必须采用 no-helper 口径，测评模型基于 task、数据、允许的通用库和公开输出契约自主生成 `solve.py` 的能力。
- 每一次新建或增量更新某个业务场景 workflow 时，必须同步检查公开契约是否精确：在 `src/tablecodeagent/benchmark/answer_models.py` 中明确 Pydantic schema，在对应 `benchmarks/tasks/<task_id>/task.json` 中明确 task 输出说明、字段语义、枚举、计数口径、warning 标签和 pytest / validator 会读取的关键业务规则。不得把语义要求只藏在 `expected.json` 或 pytest 断言里，也不得留下“duplicate_count”“invalid_age”“risk_band”“field_type_issues”这类容易产生多种解释的含糊字段。
- 严禁为了快速跑通而把 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion`、完整 workflow import 路径或 `build_*_report()` 这类解题入口公开给真实能力评测。此类 helper 提示不得出现在正式 benchmark task prompt、runner 注入 prompt、真实 benchmark result 口径或 README 能力描述中。
- 如果确实需要验证项目内 workflow helper 本身，只能作为 unit / integration / smoke / regression 测试放在项目代码测试体系中，不能命名或报告为 benchmark，不能计入真实 LLM Agent 通过率，也不能作为模型能力证据。
- Agent 输出 JSON、`answer.json`、tool input/output schema、task `output_contract` 等结构化契约不能只靠自然语言提示或顶层 key 列表。涉及可执行 benchmark 或业务报告时，至少要覆盖 pytest / validator 实际读取的关键嵌套字段和类型；更复杂场景应优先使用 JSON Schema、Pydantic model 或同等机器可校验契约，并把 parse/schema/semantic validation 分开记录。
- 如果仓库内规则、历史报告或当前实现与最新业务实践可能冲突，或涉及 structured output、Agent benchmark、风控/营销/定价等工业业务流程设计，可以调用 `.agents/skills/academic-web-search` 检索官方文档、论文、benchmark 或工程实践；外部结论只能作为设计依据，最终实现仍必须由本仓库代码、测试和 trace 验证。
- 生成代码时，新增文件、目录、测试文件、运行结果目录的命名必须清晰、可区分、好理解，名称本身应能直接说明用途、场景或内容；禁止只用纯时间戳、模糊缩写、内部黑话，或只有作者自己看得懂的名字。
- 命名优先级应为“职责语义”高于“实现身份”、高于“历史习惯”、高于“作者个人缩写”；如果一个名称不能让新读者快速判断“这是做什么的”，就说明名字不合格。
- 禁止使用过于宽泛、放到多个上下文都成立的名称作为核心文件名或目录名，例如 `runner.py`、`utils.py`、`common.py`、`temp.py` 这类名字；应优先改成直接体现职责边界的名字，例如 `benchmark_runner.py` 这类“领域 + 职责”结构。
- 文件名和目录名应优先体现“这是做什么的”，再体现“在哪个阶段/针对什么对象”；例如 benchmark 运行目录不能写成 `20260606-035402` 这种只有时间没有语义的名字，而应包含模式、模型、任务等关键信息。
- 测试目录与测试文件命名优先显式带上 `test` 前缀，例如优先使用 `test_unit/`、`test_integration/`、`test_smoke/`，避免单独写 `unit/`、`integration/` 这类一眼看不出是否为测试入口的名字。
- 命名应优先使用更直观的英文，不要滥用晦涩词、过度抽象词或上下文依赖很强的术语，例如 `dispatch` 优先换成 `routing`，`oracle` 优先换成 `expected_check`，`scaffold` 优先换成能直接说明用途的名字如 `fixed_solve_py`，如果必须在简短和易懂之间取舍，优先易懂。
- 对测试、脚本、固定工作流样例、校验器、分发器这类容易混淆的对象，命名必须直接暴露动作和对象，例如“谁执行谁”“谁检查谁”“谁路由谁”，不要让读者再去翻实现猜语义。
- 生成代码时同步考虑最小验证路径：smoke test、单元测试、可复现命令或最小样例。不要只生成实现而没有验证入口。
- 不允许为了快速完成而复制粘贴大段近似逻辑；出现重复分支时，应抽取明确 helper 或数据驱动结构。
- 工具代码优先调用 `pandas`、`numpy` 等成熟库接口，避免用脆弱的内置循环和手写解析重造常规表格能力。必要时可以使用 `$academic-web-search` 检索官方接口、工程实践或最新依赖用法，但检索结论必须能落到可验证实现。

## 3. 修改前必读

开始任何代码或文档修改前，至少先读与本轮任务相关的最小上下文：

- 项目总览：`README.md`
- 当前架构记录：`docs/reproduce/tablecodeagent_architecture.md`
- 项目动机说明：`docs/reproduce/why_table_code_agent.md`
- 历史修改记录：`docs/reproduce/` 下与本轮任务相关的 fix report、复现记录、实验记录。
- 核心代码：根据本轮任务读取真实调用链相关代码，例如 Agent Runtime、工具注册、表格工具、validation、tracing、benchmark、scripts 等相关模块；不要依赖过期文件清单替代理解代码。

原则：先理解入口、调用链、工具注册、数据路径和验证方式，再动手修改。

## 4. 文档目录规则

- `docs/baseline/`：保存原 `claude-code-from-scratch` 教程型文档，即原 `docs/00-introduction.md` 到 `docs/14-testing.md`。
- `docs/reproduce/`：保存 TableCodeAgent 自己的环境复现、架构理解、实验记录、修复报告。
- 新增与当前项目开发有关的记录，优先放入 `docs/reproduce/`，不要继续把新记录混进 baseline 教程文档目录。
- README 面向项目总览；`docs/reproduce/` 面向开发过程证据和可复现记录。

## 5. 修复报告规则

修复报告只用于记录核心代码、可执行能力、评测闭环或项目行为的实质变化。**纯文档修改、README 更新、说明文字修正、技能/指令文件调整、格式整理、注释修正，不触发修复报告，也不触发版本号变更。**

只有本次改动涉及以下任一类型，完成后才必须在 `docs/reproduce/` 下新增一份修复报告：

- 功能修复
- 行为变更
- Agent 工具注册或工具行为调整
- benchmark、trace、validation、runner 等测试闭环变化
- 表格工具、代码执行、答案校验、trace logger、benchmark runner、数据集转换等核心能力变化
- 影响项目运行方式、架构分层、任务格式、工具协议或评测口径的目录结构调整
- 用户明确要求生成修复报告

如果项目架构发生变化，必须同步检查并更新：

- `README.md` 中的架构概览、目录说明、验证命令。
- `docs/reproduce/tablecodeagent_architecture.md`；如果原文已经容易造成历史状态和最新状态混淆，优先更新为最新状态，必要时新建一份带日期的架构记录，并在旧文档中显式指向新文档。
- 对应 fix report 中的改动文件、验证证据、风险与当前限制。

报告文件命名统一为：

```text
fix-report-vX.Y.Z-YYYYMMDD.md
```

示例：

```text
docs/reproduce/fix-report-v0.0.1-20260603.md
docs/reproduce/fix-report-v0.0.2-20260604.md
docs/reproduce/fix-report-v0.1.0-20260605.md
```

报告至少覆盖：

1. 本轮问题 / 目标与范围
2. 改动文件清单
3. 关键修复内容
4. 验收方式 / 手测步骤 / 自动化测试情况
5. 版本同步清单
6. 风险与备注
7. 结论

生成 fix-report 时必须附可跳转的文件路径交叉引用，写清相关代码、测试、结果、trace、workspace、文档分别在哪里，便于直接打开查看。交叉引用必须优先落到具体文件名，不能只给文件夹名代替关键证据；benchmark、trace、workspace、generated code、answer、tests、docs 至少应给出可直接打开的文件级链接，目录链接只能作为辅助手段。链接格式必须使用标准 Markdown 相对路径，且相对当前 fix-report 文件书写；例如 `docs/reproduce/` 下的报告应写成 `[solve.py](../../benchmarks/.../solve.py)`、`[benchmark_runner.py](../../src/tablecodeagent/benchmark/benchmark_runner.py)`、`[README.md](../../README.md)`。不要写当前 IDE / Markdown 预览中无法直接跳转的绝对文件系统路径，例如 `/root/workspace/TableCodeAgent/...`。涉及 benchmark 或测试生成代码时，必须写清是否生成代码文件、生成代码文件路径、代码来源、代码文件用途、质量结论及依据。

如果本轮改动不触发修复报告，也要在最终总结中明确说明“不触发报告”的原因。

## 6. 版本号演进规则

- 当前项目从 `v0.0.1` 开始记录版本。
- `PATCH`：文档修正、小范围 bug fix、小范围测试补充，不改变核心 Agent 行为。
- `MINOR`：新增可用能力，例如新增表格工具、注册新工具、加入 benchmark runner、加入 trace logger。
- `MAJOR`：明显改变 Agent Runtime 调用链、工具协议、任务格式或 benchmark 口径，导致旧用法需要迁移。
- 版本示例：`0.0.1 -> 0.0.2 -> 0.1.0 -> 1.0.0 -> 1.2.1`。
- 用户没有明确要求修改版本号时，默认在当前版本上继续修改，不主动 bump 版本。
- 只有核心代码、可执行能力、工具协议、benchmark/trace/validation/runner 等实质变化需要版本记录时，才考虑版本号演进。
- 纯文档修改、README 更新、说明文字修正、技能/指令文件调整、格式整理、注释修正，不修改版本号。
- 每次修改项目版本号时，必须同步更新 `src/pyproject.toml` 的 `[project].version`；如果 README 徽章、修复报告文件名、结果任务组名称或文档中也写了当前版本号，必须同步检查并说明是否需要更新。
- 不要为了显得进展大而随意升大版本；版本号必须能对应真实改动和必要的修复报告。

## 7. 禁止无依据的防御性编程

本项目允许必要的安全边界，但禁止为了“看起来更稳”而加入无证据的保护逻辑。

禁止新增以下无依据逻辑：

- 无明确依据的固定超时、轮次上限、重试上限。
- 无明确依据的 prompt、工具输出、CSV 内容、trace 内容截断。
- broad `except` 后静默返回空结果、默认成功、默认跳过。
- API 失败后偷偷切换模型或 provider，却不记录原因。
- 校验失败后把失败包装成“无数据”或“已通过”。
- 表格解析失败后伪造 schema、伪造统计、伪造答案。

如果确实需要新增限制，必须同时说明：

1. 依据是什么：协议限制、现有代码约束、真实错误证据、测试结果或用户明确要求。
2. 限制触发时用户或日志能看到什么。
3. 是否会误伤合法长表格、长输出或长 trace。
4. 对 benchmark 指标和失败类型统计有什么影响。

Agent 项目里的错误处理应优先暴露真实失败原因，便于后续失败分析，而不是隐藏错误。

## 8. 测试与验证

- 不要把“代码已写”当作“功能已完成”。
- 表格工具改动至少跑本地 smoke test，验证 CSV 读取、profile、query、validate。
- Agent 工具注册改动必须验证模型可见工具 schema，且本地执行路径能返回可读结果。
- 项目代码测试和真实 Agent benchmark 必须分开：`tests/` 以及相关测试脚本只用于验证项目本身的代码有没有 bug，例如表格函数、工具 routing、固定 workflow、sandbox / pytest 基础设施；benchmark 及相关运行脚本只用于验证真实 LLM Agent 能力，不能把两类入口、结果和结论混在一起。
- 非 API 的表格函数、工具 routing、固定 workflow、fixed solve.py sandbox 检查只能写成 unit / integration / smoke / regression，不能写成真实 Agent benchmark 成果。
- 新增或修改 workflow、task contract、answer schema、validator、runner prompt 或 pytest 业务断言后，必须先补齐极其严谨完善的本地验证闭环，再考虑真实 API 复测：至少覆盖相关 unit tests、integration tests、必要的 simulated Agent outputs / mocked Agent 回归和 edge case 回归。模拟 Agent 测试尤其重要，必须主动构造会触发契约歧义的错误输出、大小写漂移、缺失值归一化、重复计数、warning 标签、枚举值、字段类型、嵌套 JSON 和边界业务口径等失败样例，先用本地 schema / pytest / validator 捕获这些问题。
- 真实 API benchmark 不得作为发现普通本地质量问题的第一道防线。本地 deterministic workflow、Pydantic / JSON Schema、task contract 文本、simulated Agent regression、sandbox 执行和 pytest / validator 全部稳定后，才允许运行真实 API benchmark；如果真实 API 暴露了可由本地模拟测试提前覆盖的问题，例如契约歧义、schema 漏洞、validator 漏检、sandbox 接线错误、pytest 口径缺失、数据边界遗漏、提示注入不充分或失败分类不清，必须先补本地回归测试并说明覆盖点，再决定是否需要再次调用 API，避免反复用真实 API 和 token 成本纠正同一类可本地前置暴露的问题。
- 真实 benchmark 默认入口为 `python -m tablecodeagent.benchmark.benchmark_runner` 或 `scripts/run_real_api_code_agent_benchmark.sh`，核心模式为 `real_api_code_agent`。
- benchmark 结果目录必须使用 `benchmarks/results/<mode>/<YYYYMMDD-HHMMSS>__model-<model_name>__tasks-<task_id_or_group>/`，不能使用只有纯时间戳、看不出模型和任务的目录名。
- 每个真实 benchmark 结果目录至少包含 `results.jsonl`、`traces/`、`workspaces/`、`summary.json`。
- benchmark 任务必须采用 no-helper 口径：禁止公开 `allowed_project_helpers`、`solve_py_suggestion`、完整 workflow import 路径、`build_*_report()` 或任何等价解题 helper；只能给出任务说明、数据文件、允许的通用库、输出契约和必要的环境约束。任何公开项目 workflow helper 的运行都不能称为 benchmark。
- `output_contract` 必须和 pytest / validator 的真实读取路径对齐。禁止只检查顶层 key 后把 `schema_check.passed=true` 写成最终通过；`schema_check`、代码执行、pytest / validator 业务验证和最终 `passed` 口径必须分开记录。
- benchmark、trace、runner 改动必须留下可复现命令和输出证据。
- 如果用户要求运行真实 API benchmark，且用户已指定 env 文件，只允许读取该指定 env 文件用于本次 API 配置，不得打印 key/token/secret；如果用户没有指定 env 文件，默认使用 `configs/api/local/deepseek.env`。不能因为 prompt 没有逐字写“允许读取 env”就跳过真实 API benchmark；env 缺失、必要变量缺失、网络/API 失败或模型失败时，必须按真实 `SKIP` / `failure_type` 记录，不能伪装成功。
- 生成 fix-report 时必须写清：是否调用 API、是否生成 `solve.py`、`solve.py` 是 `llm_generated` 还是 `runner_fixed_solve_py`、是否读取 `expected.json`、`result_dir`、`trace_path`、`workspace_path`、`generated_code_path`、`answer_path`，以及本次结果能证明什么、不能证明什么。
- 如果因为 API、网络、依赖或 env 限制无法验证，必须明确写“未验证”或 `SKIP`，并保留 `failure_type`，不能包装成通过。
- 如果因为 API、网络或环境限制无法验证，必须明确写“未验证”和原因。

## 8.1 项目内 skill 规范索引

- 新增、修改或审核 `.claude/skills/` 下的项目内 skill 时，必须遵守 `.claude/skills/.system/skill-creator/SKILL.md`。
- 新增或实质增强业务场景 workflow 时，必须同步新增或更新对应 `.claude/skills/<scenario-name>/` 项目内 skill；skill 只记录场景边界、检查顺序、输入输出和验证要求，不能替代产品态 Agent Loop 或测试 oracle 实现。
- 真实 LLM Agent benchmark 必须采用 no-helper 口径；如果新增场景 task 仍公开 workflow helper、`build_*_report()` 或等价解题入口，必须先迁移 task / runner prompt，再运行真实 benchmark。
- 仓库级 `.codex/AGENTS.md` 只保留这条索引规则和少量项目级约束，不复制完整 skill 模板。
- 项目内 skill authoring 规范不等价于 `/root/.codex/skills/.system/skill-creator/SKILL.md`，也不能通过本仓库任务修改全局系统 skill。

## 8.2 README Roadmap 规则

- 完成 `README.md` 的某个“后续开发计划”后，直接删除对应计划项，不要机械打勾或把历史 benchmark 清单反复回填到 README。

## 9. 输出与验收格式

最终总结默认按以下顺序组织，除非用户明确要求其他格式。总结必须让用户能直接复核本轮改动、验证方式、证据路径和剩余风险；不要只写“已完成”“已修复”这类空泛结论。

1. 文件改动清单（逐文件）
   - 按文件列出本轮实际改动内容，优先使用可点击 Markdown 相对路径或当前环境可跳转的文件路径。
   - 不要只写目录名代替关键文件；能定位到具体文件就写具体文件，能定位到关键行号时补行号。
   - 如果某个文件是用户已有改动、本轮只是避开、读取或未触碰，必须明确区分，不要把用户已有改动算成本轮成果。
   - 涉及 benchmark、trace、workspace、generated code、answer、task contract、validator 或 schema 时，文件清单要分别说明它们各自的用途。

2. 运行方法 / 验证方式
   - 列出本轮实际运行过的命令、脚本、单元测试、集成测试、smoke test、simulated Agent regression、真实 API benchmark 或手工验证步骤。
   - 未运行的命令不能写成已运行；历史测试结果不能写成本轮验证结果。
   - 如果本轮没有运行 TableCodeAgent 测试或 benchmark，必须说明原因，例如“本轮只调整 `.codex/AGENTS.md` 协作规则，不涉及核心代码、工具协议、benchmark、trace、validation 或 runner 行为，因此未运行项目测试”。
   - 如果验证不可用，必须说明不可用原因、替代验证方式，以及仍未覆盖的边界；不能把 `SKIP`、网络失败、API 失败或 env 缺失包装成通过。

3. 证据路径（截图、日志、trace、报告等）
   - 证据可以是命令输出摘要、测试日志、benchmark `summary.json`、`results.jsonl`、trace、workspace、generated `solve.py`、`answer.json`、pytest / validator 输出、修复报告或关键文件路径。
   - 证据路径必须可复核；生成报告时使用可跳转 Markdown 相对路径交叉引用，优先落到具体文件名，能定位到行号时写到行号。
   - 不要只引用 `docs/reproduce/`、`benchmarks/results/`、`traces/`、`workspaces/` 这类目录级位置；benchmark 或 trace 证据至少要给出可直接打开的文件级路径。
   - 不要使用当前 IDE 或 Markdown 预览中无法跳转的绝对路径，例如 `/root/workspace/TableCodeAgent/...` 或本机临时绝对路径；跨平台报告中优先使用相对路径。

4. 问题与修复闭环
   - 说明本轮问题是什么、根因或直接触发点是什么、做了什么修复、如何复测。
   - 如果只是文档、规则、prompt、skill 或 validator 资产修改，也要说明修改前缺口、补强内容和验证方式。
   - 涉及 benchmark / validation / runner / task contract 时，必须说明本轮是否改变真实评测口径、是否仍保持 no-helper 口径、是否影响 `passed`、`schema_check`、pytest / validator 业务验证或 failure type 统计。
   - 如果发现新问题但本轮未修复，必须明确标为未闭环边界，不要混入“已完成”结论。

5. 版本同步清单
   - 明确本轮是否触发版本变更。
   - 如果触发版本变更，列出已同步检查的位置，包括 `src/pyproject.toml` 的 `[project].version`、README 徽章或版本说明、修复报告文件名、结果任务组名称和相关文档中的当前版本号。
   - 如果不触发版本变更，也要明确写出“不修改版本号”的原因；纯文档、README、说明文字、技能 / 指令文件、格式整理、注释修正默认不修改版本号。

6. docs 修复报告路径
   - 如果本轮触发修复报告，给出具体报告文件路径，例如 `docs/reproduce/fix-report-vX.Y.Z-YYYYMMDD-<topic>.md`；不要只写 `docs/reproduce/` 目录。
   - 修复报告至少覆盖：
     1. 本轮问题 / 目标与范围。
     2. 改动文件清单。
     3. 关键修复内容。
     4. 验收方式 / 手测步骤 / 自动化测试情况。
     5. 版本同步清单。
     6. 风险与备注。
     7. 结论。
   - 如果本轮不触发修复报告，最终总结必须明确说明原因，例如“本轮只调整 `.codex/AGENTS.md` 协作规则，不涉及核心代码、可执行能力、工具协议、benchmark、trace、validation、runner 或项目行为变化，因此未新增 docs/reproduce 修复报告”。

7. 最终结论（是否达标、还有什么边界风险）
   - 明确说明是否达到用户目标。
   - 明确列出仍未验证、无法验证或需要用户手动确认的边界。
   - 不要把推测写成事实，不要把“未验证”写成“已验证”。

新增文件、目录、测试和报告命名要体现职责与场景，避免只有时间戳、缩写或模糊命名。命名应让后续维护者从文件名看出用途、影响范围或问题场景；TableCodeAgent 中尤其要避免只有纯时间戳的 benchmark 结果目录、只有 `temp` / `utils` / `common` 的名称、只有内部缩写的测试文件或只有版本日期但没有主题的修复报告。

## 10. 进度播报格式

在执行命令、读写文件、测试页面、查看日志、运行测试、查看 benchmark 结果、检查 trace / workspace / generated code 时，必须输出简洁中文进度块。进度块用于让用户知道当前正在做什么、为什么做、执行对象是什么、证据在哪里；不要只输出“处理中”“继续查看”这类不可复核的状态。

必须完整包含以下 6 行，字段名和顺序保持一致：

> 🧩 步骤：{一句话描述正在做什么}
> 🎯 目的：{为什么要做}
> ▶️ 执行：{命令、页面、文件路径或操作}
> ✅ 结果：{当前状态}
> 🧾 证据：{可验证证据路径}
> 📝 备注：{可选；最多一句}

使用要求：

- `步骤` 写当前动作，不写宽泛计划；例如“读取 benchmark runner 调用链”，不要写“继续处理”。
- `目的` 写清楚为什么需要这一步，例如确认 no-helper 口径、核对 schema / pytest 读取路径、检查 trace 证据、验证文档规则是否生效。
- `执行` 写真实命令、文件路径、页面或操作；如果还没有执行，不能伪造成已执行。
- `结果` 写当前可确认状态；失败、部分完成、等待用户、人机验证、API/env 缺失、网络失败或 benchmark `SKIP` 都要如实说明。
- `证据` 写可复核的位置，例如文件路径、命令输出摘要、日志路径、`summary.json`、`results.jsonl`、trace 路径、workspace 路径、generated code 路径、answer 路径或报告路径。
- `备注` 可省略具体内容但不能省略这一行；如无额外说明，可写“无”或一句边界说明。
- 长任务中每次执行命令、批量读写文件、运行测试、调用真实 API benchmark、查看日志、检查 trace / workspace 或完成阶段性验证时，都要继续使用这个进度块，而不是只在开头使用一次。
- 进度块不能替代最终总结；最终总结仍必须按“输出与验收格式”给出完整收口。

## 11. Git 与提交节奏

- 不要每一步都 commit/push。
- 完成一组相关功能、一个小闭环或一份明确报告后，再由用户决定是否提交。
- 不要提交真实 API key、`configs/api/local/`、`.env`、`__pycache__` 或无关生成文件。
- 不要自动把 `benchmarks/results/` 加入 `.gitignore`，也不要把“结果目录默认禁止提交”写成仓库规则。`benchmarks/results/` 可以保留并提交经过人工确认的关键 benchmark 证据；提交前必须检查体积、secret、`.env`、`configs/api/local/` 和不必要缓存。
- 不要回滚用户已有改动；遇到不相关 dirty 文件，只记录并避开。
