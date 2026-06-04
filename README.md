# TableCodeAgent

TableCodeAgent 是一个面向复杂表格任务的轻量级 Coding Agent 项目。它关注的不是一次性表格问答，而是当任务升级到**可复现、可验证、可审计、可迁移的表格数据处理与算法建模前置工作**时，如何把自然语言需求转化为一条结构化的程序化工作流。

在真实业务和算法场景中，表格往往不是最终答案本身，而是风险评分、增长建模、智能定价、财务推理、运营决策、因果分析和实验评估的样本载体。直接让通用 Coding Agent 依赖默认工具和默认提示处理这类任务，容易在数据口径、过滤条件、缺失值、异常值、重复样本、时间泄漏、重采样、混淆偏误、结果校验和过程复盘上失控。TableCodeAgent 的目标，是把这些隐含步骤显式组织成可执行、可检查、可记录轨迹的代码工作流：

```text
理解任务 -> 查看表格 -> 分析结构与口径 -> 编写或调用代码
-> 执行计算 -> 校验答案 -> 记录轨迹 -> 分析失败原因
```



## 为什么需要 TableCodeAgent

通用 Coding Agent 可以读文件、写代码、执行命令，也可以临时写 pandas 脚本处理 CSV。但复杂表格任务的核心难点不只是“能不能写出代码”，而是“代码是否按正确口径读取了数据，是否完成必要的数据质量检查，是否能复现计算过程，是否能验证答案，失败后是否能定位原因”。

典型场景包括：

- 信贷风险评分：训练 XGBoost、LightGBM 或深度学习模型前，需要检查缺失值、异常值、重复值、样本不平衡、时间切分、标签窗口和目标泄漏。
- 营销增长与智能定价：使用 X-learner、T-learner、DR learner、VCNet 等方法前，需要处理 treatment/control 分布差异、PSM、IPW、混淆变量、重叠性假设和权重极端值。
- 财务与运营表格推理：多表、多口径、多指标计算需要稳定的过滤、聚合、排序、对账和数值校验。
- 表格问答与 benchmark：WikiTQ、TabMWP、FinQA、TAT-QA 等任务需要把自然语言问题、表格结构、代码执行和答案验证串成闭环。

因此，TableCodeAgent 不只是让模型“看表回答”，而是让模型围绕表格任务执行一套可复盘的程序化流程：先理解字段和样本，再选择工具或生成代码，之后执行、校验、记录和归因。

## 架构概览

当前代码分为两层：

```text
TableCodeAgent
├── mini_claude              # 通用 Coding Agent Runtime
│   ├── __main__.py          # CLI 入口：参数解析、REPL、API 配置
│   ├── agent.py             # Agent Loop：调用模型、接收工具调用、执行工具、保存会话
│   ├── tools.py             # baseline 工具定义与执行：文件、搜索、shell、权限
│   ├── prompt.py            # System Prompt：工作目录、Git 状态、CLAUDE.md、skills、agents
│   ├── session.py           # 会话保存
│   ├── memory.py            # baseline 记忆系统
│   ├── skills.py            # skills 发现与解析
│   └── subagent.py          # 内置和自定义子 Agent
│
├── tablecodeagent           # 表格任务能力层
│   ├── agent_tools.py       # 表格工具 schema 与 Agent 适配
│   ├── table_tools/core.py  # CSV 读取、profile、结构化聚合查询
│   ├── validation/answer.py # 数值/字符串答案校验
│   └── tracing/             # 轨迹记录模块
│
└── benchmarks/tasks         # 表格任务样例与后续 benchmark 数据
    └── demo_table_001
        ├── data.csv
        ├── task.json
        └── expected.json
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



## 目录说明

```text
.
├── README.md                         # 项目总览
├── configs/api/                      # API 配置模板；local/ 下为本地密钥，禁止提交
├── benchmarks/tasks/demo_table_001/  # 最小表格任务样例
├── docs/baseline/                    # baseline 教程型文档
├── docs/reproduce/                   # 环境、架构、实验和修复记录
├── python/
│   ├── pyproject.toml                # Python 包配置
│   ├── mini_claude/                  # 通用 Coding Agent Runtime
│   └── tablecodeagent/               # TableCodeAgent 表格任务能力层
├── scripts/                          # 本地运行与验证脚本
├── src/                              # baseline TypeScript 版代码
└── test/                             # baseline 手动测试资源
```

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
cd ~/workspace/TableCodeAgent/python
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

## 本地验证

表格工具的独立 smoke test：

```bash
scripts/run_table_tools_smoke.sh
```

执行方式：

```bash
cd ~/workspace/TableCodeAgent
bash scripts/run_table_tools_smoke.sh
```

该脚本不调用 LLM，只验证 demo 表格任务可以完成读取、profile、结构化聚合查询和答案校验。脚本会设置 `PYTHONPATH=python`，不强依赖先执行 editable install。

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

该脚本不调用 LLM，运行两个模式：

- `direct`：直接调用表格工具函数和答案校验，验证任务计算逻辑。
- `agent_tool_dispatch`：通过 `mini_claude.tools.execute_tool()` 调用表格工具，验证工具 schema 与分发路径。

这两个模式都会写入：

```text
benchmarks/runs/<run_id>/results.jsonl
benchmarks/runs/<run_id>/traces/
```

注意：这两个模式不验证真实模型是否会主动调用表格工具，不能写成“真实 LLM Agent 行为已验证”。

当前 `v0.0.1` 已有 5 个可验证任务：

- `demo_table_001`：CSV 单表基础聚合。
- `excel_table_001`：读取 `.xlsx` 的指定 sheet。
- `multi_table_001`：两表 inner join 后聚合。
- `multi_header_001`：两行 header 规范化后聚合。
- `merged_cell_001`：展开 Excel 合并单元格后聚合。

最近一次非 API benchmark 验证：

```text
benchmarks/runs/20260603-170510/results.jsonl
```

其中 5 个任务的 `direct` 和 `agent_tool_dispatch` 均为 `passed=true`，答案均为 `32.5`。

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

如果 env 文件缺失会明确输出 `SKIP`，不伪装成功。需要调用模型的基础 API smoke 示例见：

最近一次真实 LLM Excel 任务验证结果：

```text
benchmarks/runs/20260603-170636/results.jsonl
benchmarks/runs/20260603-170636/traces/excel_table_001.optional_llm_agent.json
```

该结果中 `api_called=true`、`llm_tool_call_observed=true`、`tool_call_count=3`、`validation.passed=true`。

说明：`.xlsx` 支持依赖 `openpyxl`。当前没有引入 `pandas`、`duckdb` 或 `pyarrow`。

```bash
scripts/run_deepseek_smoke.sh
```

通用 OpenAI-compatible API smoke 示例见：

```bash
bash scripts/run_openai_compatible_smoke.sh provider_x.env
```

## API 配置

项目使用 OpenAI-compatible API 接口。真实密钥放在：

```text
configs/api/local/
```

该目录应被 `.gitignore` 忽略，不应提交到 GitHub。可提交的是：

```text
configs/api/*.env.example
configs/api/README.md
```

## 致谢

本项目基于 `claude-code-from-scratch` 的 MiniClaudeCode 思路搭建通用 Coding Agent baseline，并在此基础上探索表格任务工具、任务转换、执行验证、轨迹记录、benchmark 和失败分析。

感谢原项目提供了清晰的 Coding Agent 学习参考：

- <https://github.com/Windy3f3f3f3f/claude-code-from-scratch>
