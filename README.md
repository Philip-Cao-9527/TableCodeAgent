<div align="center">

# TableCodeAgent

**复杂表格任务 · Coding Agent · 可执行验证 · trace 归因**

<p>
一个面向复杂表格任务的轻量级 Coding Agent 项目<br/>
把任务理解、表格工具、代码生成、受控执行、答案校验和 trace 归因串成闭环
</p>

<p>
  <img alt="version" src="https://img.shields.io/badge/version-v0.0.4-blue">
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
- 营销增长与智能定价：使用 X-learner、T-learner、DRNet、VCNet 等方法前，需要处理 treatment/control 分布差异、PSM、IPW、混淆变量、重叠性假设和权重极端值。
- 财务与运营表格推理：多表、多口径、多指标计算需要稳定的过滤、聚合、排序、对账和数值校验。
- 表格问答与 benchmark：WikiTQ、TabMWP、FinQA、TAT-QA 等任务需要把自然语言问题、表格结构、代码执行和答案验证串成闭环。

因此，TableCodeAgent 不只是让模型“看表回答”，而是让模型围绕表格任务执行一套可复盘的程序化流程：先理解字段和样本，再选择工具或生成代码，之后执行、校验、记录和归因。

<a id="features" name="features"></a>

## 功能亮点

当前 `v0.0.4` 已完成以下可验证能力：

- 表格工具闭环：支持表格读取、结构 profile、过滤聚合查询和答案校验。
- 表格质量工具：覆盖缺失值、唯一键、join cardinality、row expansion、treatment/control 分布、SMD、补贴极端值和时间窗口错配。
- 受控执行环境：提供 process-level light sandbox、依赖检查、受控安装、安装日志和失败分类。
- 项目代码测试闭环：通过 `tests/test_unit/` 和 `tests/test_integration/` 验证表格函数、工具 routing、固定 workflow、sandbox 与 pytest 基础设施。
- 真实 API benchmark：`real_api_code_agent` 采用 no-helper 口径，调用真实 LLM API 生成 `solve.py`，再执行、校验并记录 trace。
- benchmark 输出契约：任务通过 Pydantic answer model 生成公开 JSON Schema，runner 会记录 `schema_check.passed` 与 `schema_check.errors`，并区分结构校验、代码执行、pytest 和 validation 失败。
- pytest 型 validation 口径：没有 `expected.answer` 时，`validation_pass_rate` 不再把“`answer.json` 存在”误写为任务通过；最终通过仍以 pytest 或显式 validator 为准。
- 信贷风险评分 workflow：增强 `credit_risk_scoring_001` fixture 与内部 workflow，覆盖贷前/贷后字段隔离、时间窗与标签窗口、重复申请与客户唯一性、缺失/异常/字段类型、特征排除原因、风险分层、业务规则校验、解释和 validation。
- trace / validation 闭环：记录 API 调用、代码生成、sandbox 执行、Pydantic schema 自检、测试校验、`run_python.exit_code`、stderr/stdout 摘要、结果路径和失败类型；API timeout 单独记为 `api_timeout`。

注意：当前 sandbox 是 process-level light sandbox，不是 Docker、Firecracker、gVisor 级强安全隔离；当前 benchmark 任务覆盖营销增长数据审计与信贷风险评分 workflow。

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
│   ├── runtime/               # 依赖检查、受控安装、process-level light sandbox
│   ├── table_tools/core.py    # 表格读取、profile、查询
│   ├── table_tools/quality.py # 缺失值、唯一键、join 膨胀、SMD、异常值、时间窗口检查
│   ├── workflows/             # 可执行表格工作流
│   ├── validation/answer.py   # 数值/字符串答案校验
│   ├── context/               # 表格上下文压缩候选能力
│   ├── memory/                # analysis memory 候选桥接层
│   └── tracing/               # 轨迹记录模块
│
├── tests                      # 项目代码测试；不证明真实 Agent 能力
└── benchmarks
    ├── tasks                  # benchmark 输入任务
    └── results                # 真实 API benchmark 输出结果；关键证据可人工确认后提交
    ├── demo_table_001
    ├── excel_table_001
    ├── multi_table_001
    ├── multi_header_001
    ├── merged_cell_001
    ├── growth_campaign_audit_001
    └── credit_risk_scoring_001
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
├── benchmarks/tasks/                 # 真实 API benchmark 输入任务
├── benchmarks/results/               # 真实 API benchmark 输出结果；关键证据可人工确认后提交
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

进入项目：

```bash
cd ~/workspace/TableCodeAgent
```

Windows PowerShell 手动环境：

```powershell
cd D:\桌面\TableCodeAgent
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
cd ~/workspace/TableCodeAgent
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

表格工具的独立 smoke test：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_table_tools_smoke.sh
```

该脚本不调用 LLM，只验证 demo 表格任务可以完成读取、profile、结构化聚合查询和答案校验。脚本会设置 `PYTHONPATH=src`，不强依赖先执行 editable install。脚本会先运行 runtime dependency preflight，缺少强依赖时会尝试受控安装并暴露失败原因。

Agent 工具注册 smoke test：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_agent_table_tools_smoke.sh
```

该脚本不调用 LLM，直接验证 `load_table`、`profile_table`、`query_table`、`validate_answer` 已出现在工具 schema 中，并且能通过 `mini_claude.tools.execute_tool()` 执行。

项目代码测试：

Windows PowerShell：

```powershell
cd D:\桌面\TableCodeAgent
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

这些测试只证明项目代码本身没有明显回归，例如表格查询、工具注册 routing、增长质量函数、固定 workflow 和 sandbox 基础设施；不能证明真实 LLM Agent 能力。

真实 API 代码生成 benchmark：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_real_api_code_agent_benchmark.sh \
  configs/api/local/deepseek.env \
  benchmarks/tasks/credit_risk_scoring_001
```

也可以把任务目录替换为 `benchmarks/tasks/growth_campaign_audit_001`，用于营销增长审计 no-helper 任务。

该脚本会调用本地 OpenAI-compatible API 配置，运行 `real_api_code_agent`。真实模型必须在 no-helper 口径下生成 `solve.py`，sandbox 执行后写出 `answer.json`，再由 Pydantic schema、外部 pytest 或 validator 对照 `expected.json` 校验。runner 不会向模型公开 `implementation_hints`、`allowed_project_helpers`、`solve_py_suggestion` 或项目 workflow helper。

真实 benchmark 输出统一位于：

```text
benchmarks/results/real_api_code_agent/<YYYYMMDD-HHMMSS>__model-<model_name>__tasks-<task_id>/
├── results.jsonl
├── summary.json
├── traces/
└── workspaces/
```

结果目录名必须包含时间、模型和任务信息。trace / result 至少记录 `api_called`、`model_name`、`benchmark_profile=no_helper`、`helper_hints_exposed=false`、`generated_code_path`、`answer_path`、`code_generation_source`、`answer_file_saved`、`schema_check.passed`、`schema_check.errors`、`run_python.exit_code`、`run_python.stderr_summary`、`pytest_exit_code`、`pytest_failure_summary`、`tool_error_count`、`validation.passed`、`skipped` 和 `failure_type`。如果 env、依赖、网络或 API 缺失，会记录为 `SKIP` 或失败，不伪装成功。

`benchmarks/results/` 可以提交经过人工确认的关键结果证据，便于 Windows/Linux 交替开发和复核。提交前必须检查结果体积、是否包含 secret、是否为本轮开发必要证据；真实 key、`.env`、`configs/api/local/` 仍严禁提交。


基础 API smoke 示例：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_deepseek_smoke.sh
```

通用 OpenAI-compatible API smoke 示例：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_openai_compatible_smoke.sh deepseek.env
```

说明：当前表格 backend 以 `pandas` 为强依赖，`numpy` 支持 `.npy/.npz`，`.xlsx` 由 pandas 通过兼容 Excel engine 读取，`.feather` 需要 `pyarrow`。

<a id="roadmap" name="roadmap"></a>

## 后续开发计划

本节记录后续可继续推进的后续开发计划

- [ ] 在进行表格分析的时候实际上要针对不同维度进行聚合，目前缺乏这种分析tools
- [ ] 补充财务运营场景下的 workflow。
- [ ] 补充表格问答与 benchmark 场景下的 workflow。
- [ ] .codex\AGENTS.md补充这个内容"在每一次新建或者是增量更新某个场景的workflow的时候确保公开契约精确，在answer_models.py明确 Pydantic schema 和 task 输出说明"
- [ ] 现在随着任务数量增加，测试时间（营销增长和信贷风控）一轮需要四分钟左右，需要考虑工程优化，docs\reproduce\fix-report-v0.0.4-20260608.md中也提到了长日志输出的问题
- [ ] 扩展更多 Coding Agent 层 benchmark，验证生成代码、sandbox 执行、pytest/expected.json 校验和 trace 归因闭环。
- [ ] 设计容器化Docker sandbox

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
