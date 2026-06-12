# 产品态主 Agent Loop 设计与外部调研结论（2026-06-12）

## 一手来源

- Anthropic: Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic: Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic: Writing effective tools for AI agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Anthropic: Multi-agent research system lessons: https://www.anthropic.com/engineering/multi-agent-research-system
- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents
- OpenAI function calling: https://developers.openai.com/api/docs/guides/function-calling
- OpenAI tools: https://developers.openai.com/api/docs/guides/tools
- OpenAI reasoning models: https://developers.openai.com/api/docs/guides/reasoning
- LangGraph workflows and agents: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- ReAct: https://arxiv.org/abs/2210.03629
- SWE-agent: https://arxiv.org/abs/2405.15793

## 调研转化出的工程约束

1. 产品态主 Loop 不能等于 deterministic oracle。Anthropic 和 LangGraph 都把固定路径 workflow 与动态 agent 决策分开：workflow 适合稳定步骤，agent 适合根据上下文和工具反馈决定下一步。TableCodeAgent 因此把 fixture oracle 放到 `tests/test_workflows/`，只服务回归和校验，不再放在 `src/` 伪装成产品主流程。
2. workflow / agent / orchestrator-worker 要分层。表格任务中，任务解析、表格发现、字段画像、schema 校验、sandbox 执行适合固定 workflow；工具选择、代码生成、基于失败反馈的修复更适合 agent 动态决策。本轮先实现单 agent 产品 Loop vertical slice，暂不引入多 worker；多表拆分、并行 profiling、候选代码多版本评估后续可扩展为 orchestrator-worker。
3. context engineering 不能只是堆 prompt。上下文必须按任务、表格画像、字段语义、质量 flags、输出契约和 repair feedback 分层进入模型。产品 Loop 使用 `build_table_context_package()` 保留字段、主键、join、缺失、重复、异常和时间窗证据，并把 `analysis_memory` 限定为 report-scoped，避免把未实现的跨线程 memory 写成已完成。
4. tool 设计、tool 返回结构和 tool 评测必须协同。OpenAI function calling / tools 与 Anthropic tool design 都强调工具 schema 是 agent-computer interface 的一部分。本轮新增 `run_table_product_workflow`，第一次调用返回上下文、工具策略和代码生成 brief，后续调用执行候选 `solve.py` 并返回 schema/pytest/validator/sandbox feedback，返回结构直接服务 repair loop。
5. Coding Agent 需要重视 ACI。ReAct 强调 reasoning 与 action 交替，SWE-agent 强调 agent-computer interface 会影响模型行为。本轮不只给大 prompt，而是提供表格 profiling、受控 workspace、sandbox 执行、pytest/validator 反馈和 trace 字段，让模型能从环境反馈修复代码。

## 本仓库落地结构

```text
src/tablecodeagent/workflow/
├── __init__.py
├── state.py
└── loop.py
```

- `state.py`：显式状态对象，记录 task、tables、context package、tool strategy、candidate attempts、repair history、validation、trace 和 report-scoped analysis memory。
- `loop.py`：产品态 vertical slice。无候选代码时返回上下文和代码生成 brief；有候选代码时创建受控 workspace，写入 `solve.py`，运行 sandbox，执行 schema/pytest/validator，并把失败归因转成 repair feedback。
- `src/tablecodeagent/agent_tools.py`：新增 `run_table_product_workflow` tool schema 与 handler，使产品 Loop 真实进入 MiniClaude tool calling 路径。
- `src/tablecodeagent/benchmark/real_api_code_agent.py`：no-helper benchmark 显式禁用 `run_table_product_workflow`，并禁止 `tablecodeagent.workflow`、`tablecodeagent.product_agent`、`tests.test_workflows` 和旧 `tablecodeagent.workflows` helper 路径。

## 固定 workflow 与动态决策边界

- 固定 workflow：任务目录解析、表格文件发现、表格画像、上下文包构建、workspace 创建、sandbox 执行、schema 检查、pytest、validator、failure type 分类。
- 动态 agent 决策：是否先调用 profiling 或 query tools、如何生成 `solve.py`、如何根据 repair history 改代码、如何解释剩余风险。
- 暂不引入 orchestrator-worker：当前 vertical slice 任务规模小，单 agent + 显式状态对象已足够；多表并行 profiling、按表 worker、候选代码竞赛和长期 memory 需要新的测试闭环后再扩展。

## 与三层 workflow 的关系

- `product workflow`：`src/tablecodeagent/workflow/`，面向用户真实任务。
- `helper-assisted workflow`：`tests/test_workflows/`，只作为 oracle / fixture / regression。
- `no-helper capability evaluation`：`real_api_code_agent`，只评估模型基于公开 task、数据和 schema 自主生成代码的能力，禁止产品 Loop 和 oracle helper。

## 本轮验证策略

真实 API 前必须先跑：

- prompt / `CLAUDE.md` / `.claude/rules` / skill metadata 注入回归。
- 产品 Loop unit tests：上下文准备、sandbox、validator、repair loop 失败后修复、仍未修复失败、空上下文错误可观测。
- no-helper 合约测试：旧 helper、新 `tests.test_workflows`、产品模块 import、动态 import 和产品工具禁用。
- simulated Agent outputs：枚举大小写、缺失值、字段类型、嵌套 JSON、重复计数口径、业务边界、warning/action 标签等。
- integration / sandbox / pytest / validator 回归。
