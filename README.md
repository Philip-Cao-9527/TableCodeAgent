<div align="center">

# TableCodeAgent

**复杂表格任务 · Coding Agent · 可执行验证 · trace 归因**

<p>
一个面向复杂表格任务的轻量级 Coding Agent 项目<br/>
把任务理解、表格工具、代码生成、受控执行、答案校验和 trace 归因串成闭环
</p>

<p>
  <img alt="version" src="https://img.shields.io/badge/version-v0.0.2-blue">
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

当前 `v0.0.2` 已完成以下可验证能力：

- 表格工具闭环：支持表格读取、结构 profile、过滤聚合查询和答案校验。
- 表格质量工具：覆盖缺失值、唯一键、join cardinality、row expansion、treatment/control 分布、SMD、补贴极端值和时间窗口错配。
- 受控执行环境：提供 process-level light sandbox、依赖检查、受控安装、安装日志和失败分类。
- 三层 benchmark：覆盖 L0 工具层、L1 workflow 层、L2 `solve.py` 代码生成与 sandbox + pytest 校验层。
- trace / validation 闭环：记录工具调用、答案校验、sandbox 执行、warning 覆盖率和失败类型。

注意：当前 sandbox 是 process-level light sandbox，不是 Docker、Firecracker、gVisor 级强安全隔离；当前营销增长任务聚焦数据审计和口径验证。

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
└── benchmarks/tasks           # 表格任务样例与 benchmark 数据
    ├── demo_table_001
    ├── excel_table_001
    ├── multi_table_001
    ├── multi_header_001
    ├── merged_cell_001
    └── growth_campaign_audit_001
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
├── benchmarks/tasks/                 # 表格任务样例与三层 benchmark 任务
├── docs/baseline/                    # baseline 教程型文档
├── docs/reproduce/                   # 环境、架构、实验和修复记录
├── src/
│   ├── pyproject.toml                # Python 包配置
│   ├── mini_claude/                  # 通用 Coding Agent Runtime
│   └── tablecodeagent/               # TableCodeAgent 表格任务能力层
├── scripts/                          # 本地运行与验证脚本
└── test/                             # baseline 手动测试资源
```

<a id="quick-start" name="quick-start"></a>

## 快速开始

进入项目：

```bash
cd ~/workspace/TableCodeAgent
```

激活环境：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
```

安装 Python 包：

```bash
cd ~/workspace/TableCodeAgent/src
python -m pip install -e .
```

查看 CLI：

```bash
mini-claude-py --help
```

运行只读计划模式示例：

```bash
cd ~/workspace/TableCodeAgent
source configs/api/local/provider_chatanywhere.env

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

benchmark runner smoke test：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_benchmark_smoke.sh
```

该脚本不调用 LLM。普通查询任务运行：

- `direct`：直接调用表格工具函数和答案校验，验证任务计算逻辑。
- `agent_tool_dispatch`：通过 `mini_claude.tools.execute_tool()` 调用表格工具，验证工具 schema 与分发路径。

营销增长任务 `growth_campaign_audit_001` 运行三层评测：

- `growth_l0_tools`：验证表格 backend 和 `quality.py` 中的确定性检查函数。
- `growth_workflow`：直接运行固定营销增长审计 workflow，生成结构化 audit report 并对照 `expected.json`。
- `sandbox_code_agent`：生成 `solve.py`，在 process-level light sandbox 中执行，再用 `pytest` / `expected.json` 校验 `answer.json`，并记录 code / test / validation 指标。

这些模式都会写入：

```text
benchmarks/runs/<run_id>/results.jsonl
benchmarks/runs/<run_id>/traces/
```

注意：非 API smoke 不验证真实模型是否会主动调用表格工具，也不等于完整 LLM Coding Agent 自主修复能力已验证。真实 LLM 行为只由 `optional_llm_agent` 或后续 LLM code generation 模式验证。

当前 `v0.0.2` 已有 6 个可验证任务：

- `demo_table_001`：CSV 单表基础聚合。
- `excel_table_001`：读取 `.xlsx` 的指定 sheet。
- `multi_table_001`：两表 inner join 后聚合。
- `multi_header_001`：两行 header 规范化后聚合。
- `merged_cell_001`：展开 Excel 合并单元格后聚合。
- `growth_campaign_audit_001`：营销增长建模前置数据审计，覆盖多表样本构造、join 膨胀、treatment/control 分布偏差、SMD、补贴极端值和时间窗口错配。

可选 LLM 端到端 demo：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_demo_table_agent_smoke.sh configs/api/local/provider_chatanywhere.env
```

也可以显式指定任务目录，例如验证 Excel 任务：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_demo_table_agent_smoke.sh \
  configs/api/local/provider_chatanywhere.env \
  benchmarks/tasks/excel_table_001
```

该脚本会调用本地 OpenAI-compatible API 配置，运行 `optional_llm_agent` 模式。只有真实模型发起表格工具调用，并最终通过 `validate_answer`，结果才会记录为 `passed=true`。

该模式会在 trace / result 中记录：

```text
mode
provider
model_name
api_called
skipped
llm_tool_call_observed
tool_call_count
final_answer
expected_answer
validation.passed
failure_type
elapsed_ms
```

如果 env 文件缺失会明确输出 `SKIP`，不伪装成功。


基础 API smoke 示例：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_deepseek_smoke.sh
```

通用 OpenAI-compatible API smoke 示例：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_openai_compatible_smoke.sh provider_x.env
```

说明：当前表格 backend 以 `pandas` 为强依赖，`numpy` 支持 `.npy/.npz`，`.xlsx` 由 pandas 通过兼容 Excel engine 读取，`.feather` 需要 `pyarrow`。

<a id="roadmap" name="roadmap"></a>

## 后续开发计划

本节记录后续可继续推进的后续开发计划

- [ ] 补充信贷风控、财务运营、表格问答与 benchmark 场景下的 workflow。
- [ ] 继续强化项目级开发规范，建议设置skills creator，增加.tca/skills/ 的格式内容规范要求 
- [ ] 将"工具代码优先调用pandas等更加方便的库而不是python内置库的接口，必要时可以调用 $ .codex/skills/academic-web-search检索最新的接口"写入agents.md。
- [ ] 将生成fix-report文档的时候写清楚测评结果, 特别是写清楚测评结果的文件路径、是否生成代码文件、代码文件是否符合质量写入agents.md。
- [ ] 每次开发的时候不需要将“当前 v0.0.2 已有 6 个可验证任务：

- demo_table_001：CSV 单表基础聚合。
- excel_table_001：读取 .xlsx 的指定 sheet。
- multi_table_001：两表 inner join 后聚合。
- multi_header_001：两行 header 规范化后聚合。
- merged_cell_001：展开 Excel 合并单元格后聚合。
- growth_campaign_audit_001：营销增长建模前置数据审计，覆盖多表样本构造、join 膨胀、treatment/control 分布偏差、SMD、补贴极端值和时间窗口错配。

最近一次非 API benchmark 验证：

    benchmarks/runs/20260606-041838/results.jsonl

其中 5 个历史任务的 direct 和 agent_tool_dispatch 均为 passed=true；growth_campaign_audit_001 的 growth_l0_tools、growth_workflow、sandbox_code_agent 均为 passed=true。
”这种内容写入readme文档写入agents.md，每次如果完成了readme.md中的某个## 后续开发计划中的开发计划，将对应的开发计划直接删除 
- [ ] 评测的时候又出现缺乏依赖导致评测偷偷没有调用api就结束的情况，这种情况要加以约束
- [ ] 我将docs文件夹里面的workspace/TableCodeAgent/docs/reproduce/why_table_code_agent.md以及workspace/TableCodeAgent/docs/reproduce/tablecodeagent_architecture.md去掉了日期，检查一下其他地方是否引用了这些文件，对应的修改一下
- [ ] 扩展更多 Coding Agent 层 benchmark，验证生成代码、sandbox 执行、pytest/expected.json 校验和 trace 归因闭环。

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

<a id="acknowledgements" name="acknowledgements"></a>

## 致谢

本项目基于 `claude-code-from-scratch` 的 MiniClaudeCode 思路搭建通用 Coding Agent baseline，并在此基础上探索表格任务工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。

感谢原项目提供了清晰的 Coding Agent 学习参考：

- <https://github.com/Windy3f3f3f3f/claude-code-from-scratch>