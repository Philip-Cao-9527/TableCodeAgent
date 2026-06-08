# TableCodeAgent v0.0.4 Code Review 报告

## 审阅范围

本轮审阅基线未发现可用 git tag：`git tag --list` 输出为空。因此本报告不把 `v0.0.3` tag 作为可靠基线，而是以当前 `HEAD=d2e1075 feat: v0.0.4 落地 no-helper 评测与 Pydantic 输出规范`、上一提交 `a66dc3e feat: v0.0.3 增强真实 API benchmark 归因与信贷风控 workflow`、当前 git 状态、`docs/reproduce/fix-report-v0.0.4-20260608.md` 和相关源码交叉核对。

纳入审阅的主要范围：`benchmark_runner.py`、`real_api_code_agent.py`、`answer_models.py`、`tracing/logger.py`、`runtime/sandbox.py`、`runtime/dependency.py`、`mini_claude/tools.py`，两个 benchmark task 及其 pytest，`tests/test_unit` / `tests/test_integration` 中的契约、sandbox 和 workflow 回归测试，README、架构文档、v0.0.3/v0.0.4 fix report、JSON 输出契约诊断文档。

当前工作区存在未提交改动：`README.md`、`.codex/AGENTS.md` 已修改；本轮真实 API 复测新增了 `benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/`。未提交 README / AGENTS 改动单独作为文档风险审阅，不自动视为 v0.0.4 已提交事实。本轮未审阅 `docs/baseline/`，未做 growth 真实 API 复测，未做多轮稳定性测试。

## Findings first

### Finding 1：`no_helper` 的生成代码防护仍依赖字符串 denylist，存在 helper-assisted 污染风险

- 严重级别：中
- 文件路径：`src/tablecodeagent/benchmark/real_api_code_agent.py:30`、`src/tablecodeagent/benchmark/real_api_code_agent.py:302`、`src/tablecodeagent/benchmark/real_api_code_agent.py:617`
- 证据：`FORBIDDEN_HELPER_MARKERS` 只列出 `"tablecodeagent.workflows"`、`build_growth_campaign_audit_report`、`build_credit_risk_scoring_report`；`_generated_helper_usage_denial()` 只是读取 `solve.py` 做子串匹配；同时 sandbox 执行环境仍给 `solve.py` 设置 `PYTHONPATH` 指向仓库 `src`。本轮生成的 `solve.py` 经 `rg` 未发现 helper 标记，当前复测未污染；但防护机制本身可被动态 import、字符串拼接 import、间接导入等方式绕过。
- 影响：如果后续模型生成的 `solve.py` 绕过字符串检查并调用项目 workflow helper，`results.jsonl` 仍可能记录 `benchmark_profile=no_helper`、`helper_hints_exposed=false`、`passed=true`，从而把 helper-assisted 结果污染为 no-helper 能力证据。
- 最小修复建议：no-helper 模式下优先不要把仓库 `src` 加入生成代码的 `PYTHONPATH`；如 pytest 必须访问项目包，则对生成代码增加 AST/import hook 级别拦截，禁止任何 `tablecodeagent.workflows` 及等价动态导入。至少补一个使用 `importlib.import_module("tablecodeagent." + "workflows...")` 的回归用例，确认不能通过。
- 验证建议：构造一个只靠 workflow helper 生成 `answer.json` 的恶意 `solve.py`，分别测试显式 import、动态 import、字符串拼接 import，期望 runner 记录 `failure_type=helper_usage_forbidden` 或 sandbox import 失败。

### Finding 2：`api_called` 在实际 API 调用前置为 `true`，异常归因边界不够精确

- 严重级别：中
- 文件路径：`src/tablecodeagent/benchmark/real_api_code_agent.py:593`、`src/tablecodeagent/benchmark/real_api_code_agent.py:595`
- 证据：代码在 `await agent.run_once(_task_prompt(workspace))` 之前设置 `trace["api_called"] = True`。Python 会先求值 `_task_prompt(workspace)`，再进入 `run_once()`；如果 prompt 构造、workspace/task 文件读取、上下文切换等前置逻辑抛错，trace 仍会显示 `api_called=true`，但真实 API 未必已经发起。
- 影响：失败归因中“API 未调用 / API 已调用但失败”的边界可能被污染，尤其是 task 文件损坏、workspace 异常或 prompt 构造异常时，报告会更像 API/模型失败，而不是 runner 前置失败。
- 最小修复建议：把 prompt 文本先构造完成，再设置更精确的字段；或拆分为 `api_attempted`、`api_called`、`api_completed`。更稳的做法是在 Agent 的实际 provider 请求入口处设置 `api_called=true`。
- 验证建议：增加一个不触发真实网络的单测或 mock：让 `_task_prompt()` 或 `Agent.run_once()` 前置阶段抛错，断言 `api_called=false`、`failure_type` 指向 runner/prompt/workspace 前置失败；另测真实 API 请求发起后再置 `api_called=true`。

### Finding 3：当前未提交 README 把开发过程长日志写入 Roadmap，存在用户文档误导

- 严重级别：中
- 文件路径：`README.md:343`、`README.md:357`、`README.md:371`、`README.md:436`
- 证据：`git status --short` 显示 `README.md` 未提交修改；`git diff -- README.md` 显示 Roadmap 中嵌入了多段 Codex 进度播报、`Edited 1 file`、历史真实 API 命令和“确保代码万无一失之后，再调用真实api测试”等表述。
- 影响：README 是用户入口文档，这段内容会把开发过程日志、历史复测命令和后续计划混在一起，容易误导读者把历史调试过程当成当前推荐流程或当前验证结论；“确保代码万无一失”也不是可验证工程结论。
- 最小修复建议：后续单独清理 README Roadmap：保留可执行的后续事项，删除进度播报和历史命令长段；如需记录“先做模拟/单测再跑真实 API”的经验，应移入 `docs/reproduce/` 的短条目，并用可验证措辞。
- 验证建议：清理后运行 `git diff -- README.md`，确认 Roadmap 只剩简洁计划项；检查 README 中没有把非 API pytest、历史 API rerun 或开发日志写成当前真实 LLM benchmark 结论。

### Finding 4：当前未提交 `.codex/AGENTS.md` 文案弱化了“报告不得夸大业务能力”的约束

- 严重级别：低
- 文件路径：`.codex/AGENTS.md:23`
- 证据：最终复核时 `git diff -- .codex/AGENTS.md` 显示该行从“不能因为少改一点而保留会误导真实 Agent 能力、引入 helper-assisted benchmark、或让报告夸大业务能力的实现”改成“不能因为少改一点而保留会误导真实 Agent 能力、引入 helper-assisted benchmark的实现”。该 diff 当前未提交，且不是本轮报告写入造成的改动。
- 影响：这会削弱项目级评测/报告边界，尤其是“不要把非 API smoke、单次通过、helper-assisted 结果写成真实 Agent 能力”的文档约束不如原文明确。
- 最小修复建议：后续单独恢复或重写该句，保留三类约束：不误导真实 Agent 能力、不引入 helper-assisted benchmark、不让报告夸大业务能力。
- 验证建议：清理后运行 `git diff -- .codex/AGENTS.md`，确认该约束语义完整且中文通顺。

## 外部实践对照

本轮按 `$academic-web-search` 补充检索了 agent eval / benchmark 的一手来源，用于核对“业务语义、评测口径和工程边界优先于少改动”的约束是否合理。

核心结论：

- OpenAI eval best practices 强调 eval 应做 task-specific 设计、记录日志、自动化评分，并持续评估；这支持当前 runner 必须把 `schema_check`、`pytest_exit_code`、`validation`、`trace` 和失败类型分开记录，而不能把 `answer.json` 存在或单次 smoke 写成真实 Agent 通过。来源：<https://developers.openai.com/api/docs/guides/evaluation-best-practices>
- Anthropic agent eval 实践把 agent eval 拆成 task、trial、grader、trace / trajectory、outcome、evaluation harness；其中 outcome 是环境最终状态，trace 是完整工具调用与中间结果记录。这支持 TableCodeAgent 当前以 `answer.json`、pytest、trace、workspace 为证据，而不是只看模型最终文本。来源：<https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>
- OpenAI SWE-bench Verified 说明 benchmark 目标不是抬高分数，而是让结果忠实代表能力，并且需要理解 benchmark、样本难度与 scaffold 的影响。这直接对应本报告 Finding 1：如果 no-helper 结果混入 helper-assisted scaffold，分数会失真。来源：<https://openai.com/index/introducing-swe-bench-verified/>
- AgentBench 把 LLM 作为 agent 放入多种交互环境中评估，并提供集成评测包；这说明 agent benchmark 应评估多轮决策、工具交互和环境反馈，不是普通文本生成题。来源：<https://arxiv.org/abs/2308.03688>
- SWE-agent 论文强调 Agent-Computer Interface 会显著影响 agent 行为与性能，且 agent 可导航仓库、编辑代码、执行测试；这支持本报告把 `tool_calls`、workspace、generated code、pytest 和 scaffold/helper 边界作为 code review 重点。来源：<https://arxiv.org/abs/2405.15793>

对当前仓库的落点：

1. v0.0.4 当前 no-helper 任务、Pydantic schema、pytest 型 validation、trace/result 字段总体方向符合上述实践。
2. 当前真实 API 单次复测通过只能写成“本次通过”，不能写成稳定性结论；多 trial 才适合支撑稳定性。
3. Finding 1 的 helper denylist 风险不是风格问题，而是会改变 scaffold 难度和 benchmark 口径的实质风险，应优先于“少改几行”处理。
4. Finding 3 的 README 长日志污染会把开发过程、历史 run 和当前验证口径混在一起，也违背 eval 报告应清晰区分 task、trial、grader、outcome 和 evidence 的实践。

## 可能解决方案

### 方案 A：收紧 no-helper sandbox 与 import 边界

适用 finding：Finding 1。

最小方案：真实 no-helper benchmark 执行生成的 `solve.py` 时，不再默认把仓库 `src` 放入 `PYTHONPATH`；只保留 workspace、标准库和 task `output_contract.allowed_libraries` 中明确允许的第三方库。当前 `credit_risk_scoring_001` 的 pytest 不依赖项目包，理论上可以先在该任务上试行。

增强方案：保留 `PYTHONPATH=src` 的同时增加两层防护。第一层用 AST 检查 `Import`、`ImportFrom`、`__import__`、`importlib.import_module` 等显式动态导入；第二层在 sandbox 启动时注入 import hook，运行期禁止导入 `tablecodeagent.workflows` 和其他 helper-only 模块。这样即使模型用字符串拼接绕过静态 denylist，也会在执行期失败。

验证闭环：

- 新增单测：显式 `from tablecodeagent.workflows... import ...` 应失败。
- 新增单测：`importlib.import_module("tablecodeagent." + "workflows.credit_risk_scoring")` 应失败。
- 新增集成测试：合法 no-helper `solve.py` 使用 `csv/json/pathlib` 能通过，且 `failure_type=null`。
- 新增真实 API 审计项：每次通过结果都记录 `helper_usage_checked=true` 和检查策略版本。

### 方案 B：拆分 API 调用状态字段

适用 finding：Finding 2。

最小方案：把 `_task_prompt(workspace)` 提前到 `trace["api_called"] = True` 之前执行；只有成功进入 `Agent.run_once()` 后才设置 `api_attempted=true`。这能避免 prompt 构造失败被误写成 API 已调用。

增强方案：在 `mini_claude.agent` 的 OpenAI / Anthropic provider 请求入口设置回调，精确写入：

- `api_config_resolved`
- `api_request_started`
- `api_response_received`
- `api_called`
- `api_error_type`

这样可以区分 env 缺失、配置缺失、请求未发起、请求已发起但网络/API 失败、模型返回但没有生成代码。

验证闭环：

- mock `_task_prompt()` 抛错：期望 `api_called=false`。
- mock provider 请求前抛错：期望 `api_request_started=false`。
- mock provider timeout：期望 `api_request_started=true`、`api_called=true`、`failure_type=api_timeout`。

### 方案 C：清理用户可见文档与项目级约束

适用 finding：Finding 3、Finding 4。

最小方案：单独做一轮文档清理，不碰业务代码。README Roadmap 只保留后续计划项，把进度日志、历史真实 API 命令和“确保代码万无一失”这类不可验证措辞删除；`.codex/AGENTS.md` 恢复“不要误导真实 Agent 能力、不要引入 helper-assisted benchmark、不要让报告夸大业务能力”三段完整约束。

增强方案：把“真实 API 前先做模拟/契约/本地回归”的经验整理成 `docs/reproduce/` 下的一页短文，例如 `real-api-benchmark-preflight-checklist.md`，但明确它是建议流程，不是当前已完成能力。

验证闭环：

- `git diff -- README.md` 只显示清晰文档改动，不再包含长日志。
- `git diff -- .codex/AGENTS.md` 保留完整约束语义。
- README 中所有验证结论都能追到 `results.jsonl`、trace、workspace 或 pytest 命令。

### 方案 D：后续稳定性评测单独成任务

适用风险：本轮真实 API 只跑 1 次，不能证明稳定。

建议方案：不要在 code review 里补跑多轮。后续单独设计 `v0.0.4-no-helper-stability` 任务，固定 env、模型、task、随机性参数和结果目录命名，一次性跑预设轮数，并在报告中分别统计：

- `api_called` / `skipped`
- `tool_call_count`
- `generated_code_saved`
- `schema_check.passed`
- `run_python.exit_code`
- `pytest_exit_code`
- `failure_type`
- `passed`

验证闭环：只有多轮结果均可追溯、无 SKIP 包装、无 helper-assisted 污染时，才写“稳定性初步通过”。单次通过继续只写“本次通过”。

## 真实 API 复测结果

本轮真实 API benchmark 实际只运行 1 次；没有因为结果通过或失败而修改代码，也没有再次运行真实 API benchmark。

命令：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m tablecodeagent.benchmark.benchmark_runner `
  --env configs/api/local/deepseek.env `
  --task-dir benchmarks/tasks/credit_risk_scoring_001 `
  --task-group v0.0.4-code-review-20260608
```

结果目录：`benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/`

关键字段：

- `api_called=true`
- `skipped=false`
- `benchmark_profile=no_helper`
- `helper_hints_exposed=false`
- `llm_tool_call_observed=true`
- `tool_call_count=10`
- `tool_error_count=0`
- `schema_check.passed=true`
- `schema_check.answer_model=credit_risk_scoring`
- `run_python.exit_code=0`
- `pytest_exit_code=0`
- `test_pass_rate=1.0`
- `validation_pass_rate=null`
- `failure_type=null`
- `passed=true`

补充核对：本轮生成的 `solve.py` 未命中 `tablecodeagent.workflows`、`build_*_report`、`expected.json`、`configs/api/local`、`OPENAI_API_KEY` 等敏感或 helper 标记；`answer.json` 中 `risk_band_counts={"low":4,"medium":1,"high":5}`，`invalid_age_count=1`，`field_type_issues` 仅包含 `loan_amount`。

结论：本轮这 1 次 no-helper 信贷任务真实 API 复测通过。该结论只代表本次单 run 通过，不代表多轮稳定性，不代表 growth 任务已在本轮复测通过，也不代表生产级风控模型能力。

## 验证命令

已执行的只读或验证命令：

```powershell
git status --short
git log --oneline --decorate -n 20
git tag --list
git diff --stat
git show --stat --oneline HEAD
git show --name-status --oneline HEAD
git diff -- README.md
rg -n "TRACE_VERSION|helper_hints_exposed|implementation_hints|allowed_project_helpers|solve_py_suggestion|schema_check|failure_type|pytest_exit_code|api_called|skipped|tool_call_count|validation_pass_rate|test_pass_rate" README.md docs src benchmarks tests -S
```

非 API 回归测试：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration
```

结果：`16 passed in 5.59s`。该结果只证明项目代码的 unit / integration 回归通过，不证明真实 LLM Agent benchmark 多任务或多轮稳定通过。

真实 API benchmark：见上一节，执行 1 次，结果通过。

## 证据路径

- 本报告：`docs/reproduce/code-review-v0.0.4-20260608.md`
- v0.0.4 fix report：`docs/reproduce/fix-report-v0.0.4-20260608.md`
- 架构文档：`docs/reproduce/tablecodeagent_architecture.md`
- JSON 契约诊断：`docs/reproduce/agent-json-output-contract-and-helper-benchmark-20260607.md`
- runner：`src/tablecodeagent/benchmark/benchmark_runner.py`
- 真实 API agent：`src/tablecodeagent/benchmark/real_api_code_agent.py`
- Pydantic answer model：`src/tablecodeagent/benchmark/answer_models.py`
- trace logger：`src/tablecodeagent/tracing/logger.py`
- sandbox：`src/tablecodeagent/runtime/sandbox.py`
- 依赖链路：`src/tablecodeagent/runtime/dependency.py`
- 工具注册/执行：`src/mini_claude/tools.py`
- 信贷 task：`benchmarks/tasks/credit_risk_scoring_001/task.json`
- 信贷 pytest：`benchmarks/tasks/credit_risk_scoring_001/tests/test_solution.py`
- growth task：`benchmarks/tasks/growth_campaign_audit_001/task.json`
- growth pytest：`benchmarks/tasks/growth_campaign_audit_001/tests/test_solution.py`
- 本轮真实 API `results.jsonl`：`benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/results.jsonl`
- 本轮真实 API `summary.json`：`benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/summary.json`
- 本轮 trace：`benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/traces/credit_risk_scoring_001.real_api_code_agent.json`
- 本轮 generated code：`benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/workspaces/credit_risk_scoring_001.real_api_code_agent/solve.py`
- 本轮 answer：`benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/workspaces/credit_risk_scoring_001.real_api_code_agent/answer.json`

## 版本与文档策略

本轮是 code review，只新增本报告，不 bump 版本，不修改业务代码、测试代码、README、架构文档、benchmark task、历史 fix report 或历史 benchmark 结果。README 当前 dirty 内容需要后续单独清理，但本轮按要求只记录 finding，不直接修改。

## 风险与未验证项

- `git tag --list` 为空，无法用 tag 可靠定位 v0.0.3 基线；本报告改用提交历史、当前源码、fix report 和真实结果交叉核对。
- 当前 `README.md` 有未提交改动，未纳入“v0.0.4 已提交完成”结论。
- 本轮只运行了 `credit_risk_scoring_001` 真实 API benchmark 1 次；未运行 `growth_campaign_audit_001` 真实 API benchmark，未做多轮稳定性测试。
- Linux / AutoDL 路径和 setup 脚本文档未在本轮实际复测。
- `benchmarks/results/real_api_code_agent/20260607-210025__model-deepseek-v4-flash__tasks-v0.0.4-code-review-20260608/` 是本轮验证生成的新结果目录，提交前仍需检查体积、secret、缓存和是否确实需要纳入版本库。
