<div align="center">

# TableCodeAgent

**复杂表格任务 · Coding Agent · 可执行验证 · 轨迹归因**

<p>
一个面向复杂表格任务的轻量级 Coding Agent 项目<br/>
把任务理解、表格工具、代码生成、受控执行、答案校验和轨迹归因串成闭环
</p>

<p>
  <img alt="version" src="https://img.shields.io/badge/version-v0.0.5-blue">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue">
</p>

<p>
  <a href="#features">功能亮点</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#local-validation">本地验证</a> ·
  <a href="#roadmap">后续开发计划</a> ·
  <a href="#api-config">API 配置</a>
</p>

</div>

<a id="overview" name="overview"></a>

## 项目定位

TableCodeAgent 是一个面向复杂表格任务的轻量级 Coding Agent 项目。它关注的不是一次性表格问答，而是当任务升级到**可复现、可验证、可审计、可迁移的表格数据处理与算法建模前置工作**时，如何把自然语言需求转化为一条结构化的程序化工作流。

在真实业务和算法场景中，表格往往不是最终答案本身，而是风险评分、增长建模、智能定价、财务推理、运营决策、因果分析和实验评估的样本载体。直接让通用 Coding Agent 依赖默认工具和默认提示处理这类任务，容易在数据口径、过滤条件、缺失值、异常值、重复样本、时间泄漏、重采样、混淆偏误、结果校验和过程复盘上失控。

TableCodeAgent 的目标，是把这些隐含步骤显式组织成可执行、可检查、可记录轨迹的代码工作流：

```text
理解任务 -> 查看表格 -> 分析结构与口径 -> 编写或调用代码
-> 执行计算 -> 校验答案 -> 记录轨迹 -> 分析失败原因
```

<a id="why-tablecodeagent" name="why-tablecodeagent"></a>

## 为什么需要 TableCodeAgent

通用 Coding Agent 可以读文件、写代码、执行命令，也可以临时写 pandas 脚本处理 CSV。但复杂表格任务的核心难点不只是“能不能写出代码”，而是“代码是否按正确口径读取了数据，是否完成必要的数据质量检查，是否能复现计算过程，是否能验证答案，失败后是否能定位原因”。

典型场景包括但不限于：

- 信贷风险评分：训练 XGBoost、LightGBM 或深度学习模型前，需要检查缺失值、异常值、重复值、样本不平衡、时间切分、标签窗口和目标泄漏。
- 营销增长与智能定价：使用 X-learner、T-learner、DRNet、VCNet 等方法前，需要处理处理组与对照组分布差异、倾向得分匹配、逆概率加权、混淆变量、样本重叠性假设和权重极端值。
- 财务与运营表格推理：多表、多口径、多指标计算需要稳定的过滤、聚合、排序、对账和数值校验。
- 表格问答与评测：WikiTQ、TabMWP、FinQA、TAT-QA 等任务需要把自然语言问题、表格结构、代码执行和答案验证串成闭环。

因此，TableCodeAgent 不只是让模型“看表回答”，而是让模型围绕表格任务执行一套可复盘的程序化流程：先理解字段和样本，再选择工具或生成代码，之后执行、校验、记录和归因。

<a id="features" name="features"></a>

## 功能亮点

### 表格工具与质量检查

- **结构化读表与字段画像**：支持 CSV / Excel 表格读取、字段类型识别、样本预览、缺失值统计和基础结构摘要，让 Agent 先理解数据而不是直接猜答案。
- **过滤、聚合与多表查询**：提供面向 Agent 调用的表格查询能力，覆盖条件过滤、聚合统计、排序、多表关联和结果返回。
- **数据质量检查**：覆盖唯一键、多表关联关系、关联后行数膨胀、处理组与对照组分布、标准化均值差、补贴极端值和时间窗口错配等复杂表格任务高风险点。

### 表格上下文与分析记忆

- **表格上下文压缩候选能力**：围绕字段含义、单位、主键、关联键、时间窗口、过滤条件和质量问题构造上下文包，目标是在压缩 token 前保留真正影响结果可信度的证据。
- **分析记忆候选桥接层**：支持把可复用经验、失败案例和“下次应如何处理”的分析结论整理成项目记忆，为后续多轮表格任务复盘和策略复用预留接口。
- **面向后续轨迹接入**：当前模块已具备上下文包和分析记忆的基础形态，后续可与轨迹日志打通，把失败归因沉淀为可检索的项目经验。

### 代码生成与受控执行

- **可执行代码闭环**：真实任务要求 Agent 生成 `solve.py`，再由评测运行器执行、收集输出、检查 `answer.json`，避免只停留在自然语言解释。
- **轻量受控运行环境**：提供进程级轻量沙箱、依赖检查、受控安装、安装日志和失败分类，用于隔离常见运行错误和依赖缺失。
- **项目代码测试闭环**：通过 `tests/test_unit/` 和 `tests/test_integration/` 验证表格函数、工具路由、固定工作流、沙箱与 pytest 基础设施。

### 评测与输出契约

- **真实 API 评测**：`real_api_code_agent` 采用“不公开项目内部解题函数”的口径，调用真实 LLM API 生成解题代码，再执行、校验并记录轨迹。
- **结构化答案契约**：任务通过 Pydantic 答案模型生成公开 JSON Schema，评测运行器记录结构检查是否通过和错误列表，并区分答案结构错误、代码执行错误、pytest 业务断言失败与显式答案校验失败。
- **pytest 型答案校验口径**：没有 `expected.answer` 时，`validation_pass_rate` 不再把“`answer.json` 存在”误写为任务通过；最终通过仍以 pytest 或显式校验器为准。
- **产品态主 Agent Loop**：`src/tablecodeagent/workflow/` 提供面向用户任务的主流程 vertical slice，并通过 `run_table_product_workflow` tool 接入 MiniClaude Agent Loop；该流程负责任务解析、表格发现、字段画像、上下文压缩、候选代码沙箱执行、schema/pytest/validator 反馈、repair history、trace 归因和 report-scoped analysis memory。
- **三层 workflow 边界**：`product workflow` 面向真实用户任务，`helper-assisted workflow` 位于 `tests/test_workflows/` 作为 fixture oracle 和回归资产，`no-helper capability evaluation` 由 `real_api_code_agent` 评估模型自主生成代码能力，禁止公开产品主 Loop 和 oracle helper。
- **项目级指令与 skill**：根目录 `CLAUDE.md` 已成为 MiniClaude 项目级长期规则入口，`.claude/rules/*.md` 保存主题补充规则，项目 skill 正式根目录为 `.claude/skills/`，并通过 `agents/agent.yaml` 元数据进入 system prompt。

### 业务场景工作流

- **营销增长数据审计**：围绕活动曝光、订单、奖励和用户表，检查多表关联后行数膨胀、处理组与对照组分布差异、标准化均值差、异常补贴和时间窗口错配。
- **信贷风险评分**：覆盖贷前/贷后字段隔离、时间窗与标签窗口、重复申请与客户唯一性、缺失/异常/字段类型、特征排除原因、风险分层、业务规则校验、解释和答案校验。
- **财务运营推理**：覆盖多表应收回款匹配、争议款保留、部分付款、超额付款、重复付款、未核销现金、账龄、授信额度、采购订单、账期和预期信用损失口径。

### 轨迹日志与失败归因

- **完整轨迹记录**：记录 API 调用、代码生成、沙箱执行、Pydantic 结构自检、测试校验、`run_python.exit_code`、stderr/stdout 摘要和结果路径。
- **失败类型拆分**：区分接口超时、环境缺失、依赖失败、代码执行失败、答案结构不满足、pytest 业务断言失败和显式答案校验失败，便于复盘 Agent 到底错在哪里。

注意：当前沙箱是进程级轻量受控执行环境，不是 Docker、Firecracker、gVisor 级强安全隔离。

<a id="architecture" name="architecture"></a>

## 架构概览

当前代码分为两层：

```text
TableCodeAgent
├── mini_claude                # 通用 Coding Agent Runtime
│   ├── __main__.py            # CLI 入口：参数解析、REPL、API 配置
│   ├── agent.py               # Agent Loop：调用模型、接收工具调用、执行工具、保存会话
│   ├── tools.py               # baseline 工具定义与执行：文件、搜索、shell、权限
│   ├── prompt.py              # System Prompt：工作目录、Git 状态、CLAUDE.md、skills、agents
│   ├── session.py             # 会话保存
│   ├── memory.py              # baseline 记忆系统
│   ├── skills.py              # skills 发现与解析
│   └── subagent.py            # 内置和自定义子 Agent
│
├── tablecodeagent             # 表格任务能力层
│   ├── agent_tools.py         # 表格工具 schema 与 Agent 适配
│   ├── runtime/               # 依赖检查、受控安装、进程级轻量沙箱
│   ├── table_tools/core.py    # 表格读取、字段画像、查询
│   ├── table_tools/quality.py # 缺失值、唯一键、关联膨胀、均衡性、异常值、时间窗口检查
│   ├── workflow/               # 产品态主 Agent Loop：上下文、执行、验证、repair feedback
│   ├── validation/answer.py   # 数值/字符串答案校验
│   ├── context/               # 表格上下文压缩候选能力
│   ├── memory/                # 分析记忆候选桥接层
│   └── tracing/               # 轨迹记录模块
│
├── tests                      # 项目代码测试；不证明真实 Agent 能力
│   └── test_workflows/        # helper-assisted fixture oracle，不属于产品主流程
└── benchmarks
    ├── tasks                  # 评测输入任务
    └── results                # 真实 API 评测输出结果；关键证据可人工确认后提交
    ├── demo_table_001
    ├── excel_table_001
    ├── multi_table_001
    ├── multi_header_001
    ├── merged_cell_001
    ├── growth_campaign_audit_001
    ├── credit_risk_scoring_001
    └── finance_operations_001
```

核心调用链：

```text
用户命令
  -> mini_claude.__main__.main()
  -> Agent.chat()
  -> _chat_openai() 或 _chat_anthropic()
  -> 模型返回文本或 tool call
  -> tools.execute_tool()
  -> 工具结果回填消息历史
  -> 继续下一轮，直到模型给出最终回答
```

<a id="directory" name="directory"></a>

## 目录说明

```text
.
├── README.md                         # 项目总览
├── configs/api/                      # API 配置模板；local/ 下为本地密钥，禁止提交
├── benchmarks/tasks/                 # 真实 API 评测输入任务
├── benchmarks/results/               # 真实 API 评测输出结果；关键证据可人工确认后提交
├── docs/baseline/                    # baseline 教程型文档
├── docs/reproduce/                   # 环境、架构、实验和修复记录
├── src/
│   ├── pyproject.toml                # Python 包配置
│   ├── mini_claude/                  # 通用 Coding Agent Runtime
│   └── tablecodeagent/               # TableCodeAgent 表格任务能力层
├── scripts/                          # 本地运行与验证脚本
├── tests/                            # pytest 单元测试和集成测试
```

<a id="quick-start" name="quick-start"></a>

## 快速开始

进入项目。下面所有命令里的项目路径都只是示例；Windows PowerShell 手动环境、Linux / AutoDL 已有 `tca` conda 环境、Linux 首次 clone 后创建 `.venv` 时，都请按自己的实际 clone 路径修改：

```bash
cd /path/to/your/TableCodeAgent
```

Windows PowerShell 手动环境：

```powershell
# 如果当前目录已经是项目根目录，可以跳过 Set-Location
Set-Location .\TableCodeAgent
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
```

Windows 也可以使用最小 setup 脚本：

```powershell
.\scripts\setup_windows.ps1
```

Linux / AutoDL 已有 `tca` conda 环境时：

```bash
cd /path/to/your/TableCodeAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
python -m pip install -r requirements-dev.txt
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
```

Linux 首次 clone 后创建 `.venv`：

```bash
cd /path/to/your/TableCodeAgent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Linux 也可以使用最小 setup 脚本：

```bash
bash scripts/setup_linux.sh
```

查看 CLI：

```bash
mini-claude-py --help
```

运行只读计划模式示例：

```bash
cd ~/workspace/TableCodeAgent
source configs/api/local/deepseek.env

mini-claude-py \
  --api-base "$MINI_CLAUDE_API_BASE" \
  --model "$MINI_CLAUDE_MODEL" \
  --max-turns 3 \
  --plan "请用中文介绍当前项目目录，不要修改任何文件。"
```

<a id="local-validation" name="local-validation"></a>

## 本地验证

表格工具的独立冒烟测试：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_table_tools_smoke.sh
```

该脚本不调用 LLM，只验证演示表格任务可以完成读取、字段画像、结构化聚合查询和答案校验。脚本会设置 `PYTHONPATH=src`，不强依赖先执行可编辑安装。脚本会先做运行依赖预检，缺少强依赖时会尝试受控安装并暴露失败原因。

Agent 工具注册冒烟测试：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_agent_table_tools_smoke.sh
```

该脚本不调用 LLM，直接验证 `load_table`、`profile_table`、`query_table`、`validate_answer` 已出现在工具结构定义中，并且能通过 `mini_claude.tools.execute_tool()` 执行。

项目代码测试：

Windows PowerShell：

```powershell
# 如果当前目录已经是项目根目录，可以跳过 Set-Location
Set-Location .\TableCodeAgent
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_unit tests/test_integration
```

Linux Bash：

```bash
cd ~/workspace/TableCodeAgent
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONIOENCODING=utf-8 PYTHONUTF8=1
python -m pytest tests/test_unit tests/test_integration
```

也可以使用脚本入口：

```bash
bash scripts/run_benchmark_smoke.sh
```

这些测试只证明项目代码本身没有明显回归，例如表格查询、工具注册路由、增长质量函数、固定工作流和沙箱基础设施；不能证明真实 LLM Agent 能力。

真实 API 代码生成评测：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_real_api_code_agent_benchmark.sh \
  configs/api/local/deepseek.env \
  benchmarks/tasks/credit_risk_scoring_001
```

也可以把任务目录替换为 `benchmarks/tasks/growth_campaign_audit_001`，用于营销增长审计任务；或替换为 `benchmarks/tasks/finance_operations_001`，用于财务运营任务。这些任务都采用“不公开项目内部解题函数”的真实能力评测口径。

该脚本会调用本地兼容 OpenAI 格式的 API 配置，运行 `real_api_code_agent`。真实模型必须在“不公开项目内部解题函数”的口径下生成 `solve.py`，沙箱执行后写出 `answer.json`，再由 Pydantic 结构契约、外部 pytest 或显式校验器对照 `expected.json` 校验。评测运行器不会向模型公开 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion` 或项目工作流辅助函数。

真实评测输出统一位于：

```text
benchmarks/results/real_api_code_agent/<YYYYMMDD-HHMMSS>__model-<model_name>__tasks-<task_id>/
├── results.jsonl
├── summary.json
├── traces/
└── workspaces/
```

结果目录名必须包含时间、模型和任务信息。轨迹和结果至少记录 `api_called`、`model_name`、`benchmark_profile=no_helper`、`helper_hints_exposed=false`、`generated_code_path`、`answer_path`、`code_generation_source`、`answer_file_saved`、`schema_check.passed`、`schema_check.errors`、`run_python.exit_code`、`run_python.stderr_summary`、`pytest_exit_code`、`pytest_failure_summary`、`tool_error_count`、`validation.passed`、`skipped` 和 `failure_type`。如果环境变量、依赖、网络或 API 缺失，会记录为 `SKIP` 或失败，不伪装成功。

`benchmarks/results/` 可以提交经过人工确认的关键结果证据，便于 Windows/Linux 交替开发和复核。提交前必须检查结果体积、是否包含 secret、是否为本轮开发必要证据；真实 key、`.env`、`configs/api/local/` 仍严禁提交。


基础 API 冒烟测试示例：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_deepseek_smoke.sh
```

通用兼容 OpenAI 格式的 API 冒烟测试示例：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_openai_compatible_smoke.sh deepseek.env
```

说明：当前表格后端以 `pandas` 为强依赖，`numpy` 支持 `.npy/.npz`，`.xlsx` 由 pandas 通过兼容 Excel 的读取引擎处理，`.feather` 需要 `pyarrow`。

<a id="roadmap" name="roadmap"></a>

## 后续开发计划

本节记录后续可继续推进的开发计划。

### 最高优先级

- [ ] 针对 0.0.4 八次测试原因分析暴露的问题、Windows 兼容性问题（尤其是长日志输出兼容性）、0.0.5 既有两次真实 API 测试失败，以及docs\reproduce\fix-report-v0.0.5-20260612.md中 `finance_operations_001` 真实 API 复测失败（`pytest_failed`，核心缺口是业务异常类型 `missing_po` 未被模型输出覆盖）进行一次集中 code review，然后修复。修复顺序必须先补本地回归：合同文本、Pydantic schema、pytest 业务断言、simulated Agent 错误输出、sandbox 执行和失败归因全部稳定后，才允许决定是否再做真实 API 复测。
- [ ] 为 `src/tablecodeagent/workflow/` 设计独立的 product workflow 真实 API 验证入口或任务组，例如 `product_workflow_agent`。该验证要明确允许模型调用 `run_table_product_workflow`，并单独记录是否调用 workflow、候选代码版本数、repair history、schema/pytest/validator 结果、trace、workspace 和失败归因；结果只能归为 product workflow / workflow-assisted 产品链路验证，不得并入 no-helper benchmark pass rate。

### 高优先级

- [ ] 补充多维度聚合分析工具，特别是营销增长场景中按渠道、周中周末、地区、活动类型、用户分层等维度拆解效果。
- [ ] 将 `src/tablecodeagent/context/table_context.py` 的表格上下文压缩候选能力接入真实 Agent / benchmark 调用链：用字段语义、主键/关联键、时间窗口、质量标记、代表性样本预览和 trace 证据替代大表原文，并确保压缩时不丢失重复键、join 膨胀、缺失值、异常值和时间窗口错配等关键证据。当前 `load_table(path, preview_rows=5)` 只看前 5 行，无法代表全表分布，后续应改为结合分层/随机/首尾样本、字段统计、分位数、类别频次、缺失率、异常值和 group/join 分布摘要的上下文包，这里尽可能检索网络，学习业界实践。
- [ ] 将 `src/tablecodeagent/memory/analysis.py` 的 analysis memory 候选桥接层接入失败归因闭环：把可复用经验、失败案例、how-to-do-differently、适用范围、证据路径和失效条件写入项目级 memory，并在后续同类表格任务中可控召回。
- [x] 已将原 `src/tablecodeagent/workflows/` 的确定性参考实现迁移到 `tests/test_workflows/`，并同步更新 integration tests、simulated Agent tests、fixture oracle 引用和 no-helper denylist；它们现在只作为 helper-assisted oracle / regression 资产，不属于产品态主 Agent workflow。
- [x] 已新增 `src/tablecodeagent/workflow/` 产品态主 Agent Loop vertical slice，并通过 `run_table_product_workflow` tool 接入 MiniClaude 主链路；当前覆盖任务解析、表格发现、字段画像、上下文压缩、工具策略、候选代码沙箱执行、schema/pytest/validation 反馈、repair history、trace 归因和 report-scoped analysis memory。
- [x] 已将项目 skill 正式根目录收敛到 `.claude/skills/` 并删除 `.tca/skills/`；`agents/agent.yaml` 元数据已进入 `skills.py` 的 system prompt 注入，场景 skill 文案改为区分当前已实现 / 已接入能力、工业场景目标和尚未接入 / 未验证能力。
- [x] 已新增根目录 `CLAUDE.md`，并同步 `.claude/rules/workflow-boundaries.md`；MiniClaude 项目级长期规则现在覆盖 no-helper benchmark、真实 API 成本边界、本地验证优先、三层 workflow 边界和 `.claude/skills/` skill 根目录。

### 低优先级

- [ ] 设计容器化Docker sandbox
- [ ] 后续进行 Linux 系统下的真实 API 测试，确保兼容性。
- [ ] 现在随着任务数量增加，测试时间（营销增长和信贷风控）一轮需要四分钟左右，需要考虑工程优化，docs\reproduce\fix-report-v0.0.4-20260608.md中也提到了长日志输出的问题
- [ ] 补充表格问答与评测场景下的工作流。



<a id="api-config" name="api-config"></a>

## API 配置

项目使用 OpenAI-compatible API 接口。真实密钥放在：

```text
configs/api/local/
```

该目录被 `.gitignore` 忽略，不应提交到 GitHub。可提交的是：

```text
configs/api/*.env.example
configs/api/README.md
```

配置文件中可以使用 `OPENAI_API_KEY` 作为 OpenAI-compatible 接口约定变量名

benchmark 结果目录不存放密钥；如果需要把 `benchmarks/results/` 中的关键 run 作为证据提交，必须先人工确认 `results.jsonl`、trace、workspace、generated code 和 answer 中没有 key/token/secret，且结果体积适合进入仓库。

<a id="acknowledgements" name="acknowledgements"></a>

## 致谢

本项目基于 `claude-code-from-scratch` 的 MiniClaudeCode 思路搭建通用 Coding Agent baseline，并在此基础上探索表格任务工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。

感谢原项目提供了清晰的 Coding Agent 学习参考：

- <https://github.com/Windy3f3f3f3f/claude-code-from-scratch>
