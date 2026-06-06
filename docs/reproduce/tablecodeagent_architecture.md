# TableCodeAgent 架构理解记录


本文档用于说明当前 TableCodeAgent 的真实代码结构、baseline 调用链、表格工具接入方式，以及后续最小 MVP 开发方向。这里不把未实现功能写成已完成能力。

## 1. 当前项目定位

TableCodeAgent 的目标不是直接做一个表格问答页面，也不是简单把 CSV 丢给 LLM 回答。它要做的是一个面向表格数据任务的 Coding Agent：

```text
读项目 -> 理解任务 -> 查看数据 -> 写或调用代码 -> 执行代码 -> 校验答案 -> 修复错误 -> 记录轨迹 -> 分析失败类型
```

第一阶段使用 `mini_claude` 作为通用 Coding Agent Runtime baseline，然后逐步加入表格场景能力。

当前准确状态：

- baseline CLI、Agent Loop、工具调用、OpenAI-compatible API 调用已经存在。
- 当前 Python 主实现目录为 `src/`，原 TypeScript 版顶层 `src/` 已移除。
- `tablecodeagent` 包已经包含 pandas backend、表格质量工具、答案校验、Agent 工具适配、trace logger、真实 API benchmark runner、runtime dependency 与 light sandbox。
- `load_table`、`profile_table`、`query_table`、`query_multi_table`、`validate_answer` 以及营销增长质量检查工具已接入 `mini_claude` 的工具 schema 与 `execute_tool()` 分发路径。
- 已有不调用 LLM 的 `tests/test_unit/` 与 `tests/test_integration/` 验证独立表格工具层、Agent 工具注册、固定 workflow、sandbox / pytest / validation 闭环。
- `growth_campaign_audit_001` 已作为测试 fixture 覆盖 L0 工具层、L1 workflow 层、固定 `solve.py` + sandbox + pytest 校验层。
- 新的真实 benchmark 入口是 `real_api_code_agent`，目标是调用真实 LLM API 生成 `solve.py`，再通过 sandbox、pytest / validator 和 trace 验证。

## 2. 顶层目录职责

```text
TableCodeAgent/
├── README.md
├── configs/api/
├── docs/reproduce/
├── benchmarks/tasks/
├── benchmarks/results/
├── src/
│   ├── mini_claude/
│   └── tablecodeagent/
├── tests/
└── scripts/
```

关键说明：

- `src/mini_claude/`：原 baseline 的 Python Coding Agent Runtime，是当前 Agent 主体。
- `src/tablecodeagent/`：本项目新增的表格任务能力层。
- `benchmarks/tasks/`：后续放表格任务样例、转换后的 benchmark 任务。
- `benchmarks/results/`：真实 API benchmark 输出目录。
- `tests/`：项目代码单元测试和集成测试，不代表真实 Agent benchmark。
- `docs/reproduce/`：保存环境、复现、架构理解、实验记录。
- 顶层 `src/`：当前 Python 主实现目录；原 baseline TypeScript 版顶层 `src/` 已移除。

## 3. baseline Python 架构

### 3.1 CLI 入口

文件：`src/mini_claude/__main__.py`

职责：

- 解析命令行参数。
- 处理 `--plan`、`--yolo`、`--api-base`、`--model`、`--max-turns`、`--resume` 等参数。
- 解析 API key 和 API base。
- 创建 `Agent` 实例。
- 进入一次性 prompt 模式或 REPL 模式。

关键调用链：

```text
main()
  -> parse_args()
  -> _resolve_permission_mode()
  -> Agent(...)
  -> agent.chat(prompt) 或 run_repl(agent)
```

小白版理解：

- `__main__.py` 不是 Agent 最核心的“思考逻辑”，它更像一个程序启动器。
- 你在终端输入 `mini-claude-py --plan "请介绍项目"`，最先进入的就是这里。
- 它负责把命令行参数和环境变量整理好，例如模型名、API 地址、权限模式、是否恢复 session。
- 整理好以后，它创建一个 `Agent` 对象，然后把用户输入交给 `Agent.chat()`。

一次性 prompt 模式：

```bash
mini-claude-py "请解释这个项目"
```

这种模式只执行一次用户输入。程序大致流程是：

```text
启动 CLI -> 创建 Agent -> agent.chat("请解释这个项目") -> 输出结果 -> 程序结束
```

REPL 模式：

```bash
mini-claude-py
```

如果命令后面没有直接跟 prompt，就会进入 REPL。REPL 是 `Read-Eval-Print Loop` 的缩写，可以理解成“交互式命令行循环”：

```text
Read   读取你输入的一行内容
Eval   交给 Agent 处理
Print  打印模型回答或工具结果
Loop   回到输入提示符，等你继续输入下一句话
```

所以 REPL 模式不是一种新模型，也不是一种新算法，而是交互方式。你可以连续输入多轮：

```text
> 请先看一下 README
> 再解释 tools.py
> 现在帮我改一个小功能
```

`async` / `await` 的含义：

- `async def run_repl(...)` 表示这是一个异步函数。
- `await agent.chat(inp)` 表示“等待 Agent 完成这一轮处理，但等待期间事件循环可以管理其他异步任务”。
- 在这个项目里，异步主要是为了适配 LLM streaming、工具调用、memory 预取、子 Agent 等可能需要等待的操作。
- 普通函数是一条路走到底；异步函数更像“这一步要等网络或工具结果，我先把控制权交回事件循环，等结果来了再继续”。

在 `__main__.py` 里，真正启动异步代码的是：

```python
asyncio.run(agent.chat(prompt))
asyncio.run(run_repl(agent))
```

这两行的意思是：在普通 Python 程序入口里启动一个异步事件循环，然后运行对应的异步任务。

### 3.2 Agent Loop

文件：`src/mini_claude/agent.py`

职责：

- 保存模型、权限模式、token、turn、session 等状态。
- 根据 API 类型选择 Anthropic 或 OpenAI-compatible 后端。
- 构造 system prompt。
- 调用模型。
- 接收模型文本输出和工具调用。
- 执行工具并把结果写回消息历史。
- 根据 token 状态触发上下文压缩。
- 自动保存 session。

核心入口：

```text
Agent.chat(user_message)
  -> _chat_openai(user_message) 或 _chat_anthropic(user_message)
  -> 模型返回 assistant message
  -> 如果包含 tool call，则调用 execute_tool()
  -> tool result 回填消息历史
  -> 继续下一轮
```

小白版理解：

普通 LLM 问答通常是：

```text
用户问题 -> 模型回答 -> 结束
```

Coding Agent 不是这样。Coding Agent 的关键是“模型可以决定调用工具”，所以它更像：

```text
用户任务
  -> 模型先想下一步该干什么
  -> 如果需要看文件，模型请求 read_file
  -> 程序执行 read_file，把文件内容返回给模型
  -> 模型看完结果后继续决定下一步
  -> 如果需要改文件，模型请求 edit_file/write_file
  -> 程序执行工具，把结果返回给模型
  -> 如果需要跑测试，模型请求 run_shell
  -> 程序执行测试，把 stdout/stderr 返回给模型
  -> 模型根据结果继续修复或给最终回答
```

这个“模型 -> 工具 -> 工具结果 -> 模型 -> 工具 -> 工具结果”的循环，就叫 Agent Loop。

换句话说，Agent Loop 的核心不是某个神秘算法，而是一个反复执行的控制流程：

```text
while 任务还没结束:
    调用模型
    如果模型只输出最终文本:
        结束
    如果模型要求调用工具:
        执行工具
        把工具结果追加进消息历史
        继续下一轮
```

为什么 `agent.py` 里看不到 `execute_tool()` 的实现：

- `agent.py` 顶部有一行导入：

```python
from .tools import (
    tool_definitions,
    execute_tool,
    check_permission,
    ...
)
```

- 这表示 `execute_tool()` 的实际代码不在 `agent.py`，而是在 `src/mini_claude/tools.py`。
- `agent.py` 只负责“什么时候该执行工具”；`tools.py` 负责“具体怎么执行这个工具”。

当前代码里的调用关系是：

```text
agent.py
  -> Agent._execute_tool_call(name, inp)
  -> execute_tool(name, inp, self._read_file_state)
  -> tools.py 里的 execute_tool()
  -> 根据 name 找到具体 handler
  -> 执行 _read_file/_write_file/_run_shell 等函数
```

其中 `name` 是工具名，例如 `read_file`；`inp` 是模型传来的工具参数，例如：

```json
{
  "file_path": "README.md"
}
```

### 3.3 工具系统

文件：`src/mini_claude/tools.py`

职责：

- 定义工具 schema：`tool_definitions`。
- 判断权限：`check_permission()`。
- 执行工具：`execute_tool()`。
- 实现 baseline 文件工具、搜索工具、shell 工具、web fetch。

当前已有工具包括：

- `read_file`
- `write_file`
- `edit_file`
- `list_files`
- `grep_search`
- `run_shell`
- `web_fetch`
- `skill`
- `agent`
- `enter_plan_mode`
- `exit_plan_mode`
- `tool_search`

对 TableCodeAgent 来说，第一阶段可以复用：

- 文件读取、写入、编辑。
- 目录和代码搜索。
- shell 执行。
- plan mode 和 session 保存。

后续需要新增或接入：

- `load_table`
- `profile_table`
- `query_table`
- `validate_answer`
- 结构化 `run_python`
- 结构化 `run_tests`

什么叫“工具注册”：

在这个项目里，一个工具想让 Agent 使用，通常要完成两步。

第一步：把工具的“说明书”加到 `tool_definitions`。

`tool_definitions` 是发给模型看的工具清单。它告诉模型：

- 工具叫什么名字。
- 工具能做什么。
- 工具需要哪些参数。
- 参数是什么类型。

例如一个极简版 `load_table` 工具 schema 大概长这样：

```python
{
    "name": "load_table",
    "description": "Read a CSV table and return columns, row count, and rows.",
    "input_schema": {
        "type": "object",
        "properties": {
            "csv_path": {"type": "string"}
        },
        "required": ["csv_path"],
    },
}
```

模型看不到 Python 函数本身。模型能看到的是这个 schema。只有 schema 写清楚了，模型才知道“我可以调用一个叫 `load_table` 的工具，并且要传 `csv_path` 参数”。

第二步：在 `execute_tool()` 里把工具名映射到实际 Python 函数。

当前 `tools.py` 里有一个 `handlers` 字典：

```python
handlers: dict = {
    "write_file": _write_file,
    "edit_file": _edit_file,
    "list_files": _list_files,
    "grep_search": _grep_search,
    "run_shell": _run_shell,
    "web_fetch": _web_fetch,
}
```

这个字典的意思是：

```text
如果模型请求 write_file，就调用 _write_file()
如果模型请求 grep_search，就调用 _grep_search()
如果模型请求 run_shell，就调用 _run_shell()
```

当前表格工具已经按轻量 adapter 方式注册，不再把表格核心逻辑堆进 `tools.py`。实际接入方式是：

```text
1. 在 src/tablecodeagent/agent_tools.py 中集中定义 TABLE_TOOL_DEFINITIONS。
2. 在 src/tablecodeagent/agent_tools.py 中用 execute_table_tool() 适配真实表格函数。
3. 在 src/mini_claude/tools.py 中合并 TABLE_TOOL_DEFINITIONS 到 tool_definitions。
4. 在 READ_TOOLS 和 CONCURRENCY_SAFE_TOOLS 中加入 TABLE_TOOL_NAMES。
5. 在 execute_tool() 中把表格工具名分发给 execute_table_tool()。
```

为什么需要“适配函数”：

`tablecodeagent.table_tools.core.query_table()` 的 Python 调用可能是：

```python
query_table(csv_path, metric="sum", column="revenue", filters={"region": "North"})
```

但是 Agent 工具系统收到的是统一的字典：

```python
{
    "csv_path": "...",
    "metric": "sum",
    "column": "revenue",
    "filters": {"region": "North"}
}
```

当前包装函数不直接写在 `tools.py`，而是集中放在 `src/tablecodeagent/agent_tools.py`，避免通用工具分发文件继续膨胀。适配层会把统一的工具输入字典转成具体函数参数，并把结果包装成统一 JSON：

```json
{
  "ok": true,
  "result": {}
}
```

失败时返回：

```json
{
  "ok": false,
  "error": "...",
  "error_type": "..."
}
```

这样 baseline 工具系统仍然只处理字符串结果，表格工具内部细节由领域适配层负责。

当前工具注册已经完成，但这不等于完整 TableCodeAgent 已完成。更准确地说：

- `tools.py` 是“把工具接入 Agent Loop”的轻量注册和分发位置。
- `src/tablecodeagent/` 是“工具真实能力”的实现位置。
- `benchmarks/` 是“任务和标准答案”的位置。
- 后续 `tracing/` 和 benchmark runner 是“证明项目有效”的位置。

所以 A 级 MVP 的推进顺序应该是：

```text
表格工具已接入 Agent 工具系统
  -> 实现最小 trace logger
  -> 写 demo benchmark runner
  -> 记录工具调用、答案、校验结果和失败类型
  -> 跑 Direct 工具执行 / Agent 工具分发 / 可选 LLM demo 对比
  -> 输出结果表和失败分析
```

### 3.4 System Prompt

文件：`src/mini_claude/prompt.py`

职责：

- 内置 baseline system prompt。
- 注入当前工作目录、日期、平台、shell。
- 注入 Git 分支、最近 commit、工作区状态。
- 向上查找并加载 `CLAUDE.md`。
- 加载当前目录 `.claude/rules/*.md`。
- 注入 memory、skills、agents、deferred tools 信息。

注意：

- Linux 文件名大小写敏感，代码查找的是 `CLAUDE.md`，不是 `Claude.md`。
- 如果项目根目录没有 `CLAUDE.md`，Agent 仍然能运行，只是不会自动获得项目级补充指令。

### 3.4.1 Memory 系统如何发挥作用

你观察到 `prompt.py` 里出现了 memory，这是对的，但 memory 不是只靠 `prompt.py` 发挥作用。当前 baseline 的 memory 机制分成两层：

```text
第一层：启动时把 memory 系统说明和 memory 索引注入 system prompt
第二层：每轮用户输入时，异步检索相关 memory，并把相关 memory 注入当前消息
```

第一层发生在 `prompt.py`：

```text
build_system_prompt()
  -> build_memory_prompt_section()
  -> 把 memory 目录、memory 类型、保存方法、MEMORY.md 索引写进 system prompt
```

这一步的作用是告诉模型：

- 你有一个文件型 memory 系统。
- memory 存在哪里。
- memory 分几类。
- 如果需要保存长期信息，可以用 `write_file` 写 memory 文件。
- 当前有哪些 memory 条目索引。

memory 默认保存目录不是项目目录，而是：

```text
~/.mini-claude/projects/<项目路径哈希>/memory/
```

这样不同项目的 memory 会分开存储。

第二层发生在 `agent.py` 和 `memory.py`：

```text
Agent._chat_openai() 或 Agent._chat_anthropic()
  -> _build_side_query()
  -> start_memory_prefetch(user_message, side_query, ...)
  -> select_relevant_memories()
  -> format_memories_for_injection()
  -> 把相关 memory 追加到当前 user message
```

这里的 `side_query` 可以理解为“一次很小的模型调用”。它不是主 Agent 回答用户，而是让模型帮忙从 memory 索引里挑选相关记忆。

流程更直观地写成：

```text
用户输入：“继续做 TableCodeAgent 的表格工具”
  -> Agent 扫描 memory 文件头部，得到 memory 候选列表
  -> side_query 问模型：哪些 memory 和这个问题相关？
  -> 模型返回最多 5 个 memory 文件名
  -> 程序读取这些 memory 文件内容
  -> 用 <system-reminder> 包起来
  -> 追加到当前 user message 后面
  -> 主 Agent 调用模型时就能看到这些记忆
```

为什么叫 `prefetch`：

- `prefetch` 是“预取”的意思。
- 当前代码会在每轮用户输入开始后，异步启动 memory 选择任务。
- Agent 同时继续准备调用主模型。
- 如果 memory 选择任务及时完成，就把 memory 注入本轮消息。
- 如果没完成，就不阻塞主流程。

这就是为什么代码里会出现 `asyncio.create_task(...)`、`memory_prefetch.settled`、`memory_prefetch.consumed` 这些概念。

memory 和 session 的区别：

```text
session:
  保存一次对话过程里的消息历史。
  主要用于 --resume 恢复上次聊天。

memory:
  保存跨会话、跨多次运行仍然有用的信息。
  例如用户偏好、项目长期目标、重要决策、踩坑记录。
```

memory 和 `CLAUDE.md` 的区别：

```text
CLAUDE.md:
  项目级固定规则，通常提交到仓库。
  适合写“这个项目长期遵守什么规范”。

memory:
  当前用户/当前机器上的长期记忆，默认不提交到仓库。
  适合写“这个用户喜欢什么风格”“上次做到哪里了”“某个环境坑怎么解决”。
```

对 TableCodeAgent 来说，memory 目前不是主贡献。它是 baseline 的一个可复用能力。你可以理解它，但第一阶段不要把它包装成自己的核心创新。你真正能写进项目主线的是：

```text
表格工具 -> 任务转换 -> Agent 执行 -> 答案校验 -> trace -> benchmark -> 失败分析
```

后续如果要利用 memory，更合理的方式是：

- 保存项目长期开发规则。
- 保存 API/环境踩坑。
- 保存 benchmark 失败类型分析结论。
- 保存“哪些表格 profile 对 Agent 有帮助”的经验。

### 3.5 上下文压缩

文件：`src/mini_claude/agent.py`

相关函数：

- `_check_and_compact()`
- `_compact_conversation()`
- `_compact_openai()`
- `_compact_anthropic()`
- `_run_compression_pipeline()`
- `_budget_tool_results_openai()`
- `_snip_stale_results_openai()`
- `_microcompact_openai()`

当前压缩对象是 prompt/context 中的消息历史和工具结果，不是模型底层 KV cache。

### 3.6 session 保存

文件：`src/mini_claude/session.py`

默认目录：

```text
~/.mini-claude/sessions/
```

保存内容包括：

- session metadata
- Anthropic 消息历史
- OpenAI-compatible 消息历史

这属于 baseline 会话保存，不等于 TableCodeAgent 后续要做的 benchmark trace logger。后续 trace logger 需要记录任务级轨迹、工具调用、耗时、token、答案正确性和失败类型。

## 4. 上一轮新增表格层做了什么

新增目录：

```text
src/tablecodeagent/
├── __init__.py
├── agent_tools.py
├── table_tools/
│   ├── __init__.py
│   └── core.py
├── validation/
│   ├── __init__.py
│   └── answer.py
└── tracing/
    └── __init__.py
```

新增 demo 任务：

```text
benchmarks/tasks/demo_table_001/
├── data.csv
├── task.json
└── expected.json
```

修改：

```text
src/pyproject.toml
```

修改作用：

- `pyproject.toml` 的包发现包含了 `tablecodeagent*`。
- 这样 `python -m pip install -e .` 后，可以在任意项目目录 import `tablecodeagent`。

## 5. 表格工具的当前能力

文件：`src/tablecodeagent/table_tools/core.py`

Agent 适配文件：`src/tablecodeagent/agent_tools.py`

当前已经注册给 `mini_claude` 的工具：

- `load_table`
- `profile_table`
- `query_table`
- `validate_answer`

这些工具通过 `src/mini_claude/tools.py` 暴露给 Agent。`tools.py` 只负责 schema 合并和分发，真实表格能力仍在 `src/tablecodeagent/` 里。

### 5.1 `load_table`

输入：

```text
csv_path
preview_rows
```

输出：

```text
{
  "path": "...",
  "columns": [...],
  "row_count": 5,
  "preview_row_count": 5,
  "preview_rows": [...]
}
```

作用：

- 读取 CSV。
- 返回列名、行数和受控 preview。
- 避免 Agent 默认把全量表格行吞进上下文。

当前限制：

- 只支持 CSV。
- 字段都先按字符串读入。
- 没有处理 Excel、多表、多 header、合并单元格。

### 5.2 `profile_table`

输入：

```text
csv_path
```

输出：

```text
{
  "row_count": ...,
  "column_count": ...,
  "columns": [...],
  "missing_values": {...},
  "numeric_stats": {...},
  "column_profiles": {...},
  "duplicate_row_count": 0,
  "quality_flags": []
}
```

作用：

- 给 Agent 一个表格概览。
- 减少 Agent 一上来就读完整大表的上下文压力。
- 输出数值列的 count、min、max、mean、sum。
- 输出字段级缺失率、唯一值数量、推断类型、列级 flags。
- 输出重复行数量和基础质量 flags。

### 5.3 `query_table`

输入示例：

```json
{
  "metric": "sum",
  "column": "revenue",
  "filters": {
    "region": "North"
  }
}
```

作用：

- 对 CSV 做轻量结构化聚合查询。
- 支持 `count`、`sum`、`mean`、`max`、`min`。
- 支持旧版 dict 等值过滤，也支持列表式结构化过滤。
- 支持 `eq`、`ne`、`gt`、`gte`、`lt`、`lte`、`contains`。

当前限制：

- 不是 SQL 引擎。
- 不支持 join、group by、窗口函数和复杂表达式。
- 日期目前主要作为字符串/类型推断处理，尚未实现专门日期范围语义。

### 5.4 `validate_answer`

文件：`src/tablecodeagent/validation/answer.py`

作用：

- 对数值答案做容差校验。
- 对非数值答案做精确相等校验。
- 支持直接校验 `query_table` 返回的结构化结果中的 `value` 字段。

这是后续 benchmark runner 判断任务是否成功的最小基础。

## 6. demo 任务说明

文件：

```text
benchmarks/tasks/demo_table_001/data.csv
benchmarks/tasks/demo_table_001/task.json
benchmarks/tasks/demo_table_001/expected.json
```

任务问题：

```text
计算 North 区域的总 revenue。
```

标准答案：

```text
32.5
```

计算过程：

```text
North revenue = 16.5 + 6.0 + 10.0 = 32.5
```

这个 demo 的作用不是证明项目具备复杂表格推理能力，而是验证最小工具闭环：

```text
CSV 读取 -> 表格 profiling -> 简单查询 -> 答案校验
```

## 7. `.claude` 和 `CLAUDE.md` 删除影响

结论：删除原项目根目录的 `.claude/` 和 `CLAUDE.md` 不会破坏 baseline 主流程，但会移除一些可选的项目级 Agent 配置。

从当前代码看：

- `prompt.py` 会尝试向上查找 `CLAUDE.md`，不存在就返回空字符串。
- `prompt.py` 会尝试加载 `.claude/rules/*.md`，不存在就跳过。
- `skills.py` 会尝试加载 `.claude/skills/*/SKILL.md`，不存在就表示没有项目级 skills。
- `subagent.py` 会尝试加载 `.claude/agents/*.md`，不存在就只使用内置 `explore`、`plan`、`general`。
- `tools.py` 和 `mcp_client.py` 会尝试读取 `.claude/settings.json`，不存在就没有项目级权限和 MCP 配置。

因此，删除它们的实际影响是：

- 不影响 `mini-claude-py --help`。
- 不影响基础 Agent Loop。
- 不影响 API 调用。
- 不影响 baseline 内置工具。
- 会影响项目级规则、skills、自定义 agents、项目级 MCP/权限配置。

结合原始仓库当前页面，原项目确实包含 `.claude/` 和 `CLAUDE.md`；原始 `CLAUDE.md` 内容主要是测试项目规则和引用 `.claude/rules/chinese-greeting.md`，不是 TableCodeAgent 运行必需文件。

建议：

- 不需要恢复原作者的 `.claude/` 和 `CLAUDE.md`。
- 后续可以新增自己的 `CLAUDE.md`，用于写 TableCodeAgent 项目级开发规则。
- 如果新增，文件名必须是全大写 `CLAUDE.md`。
- 如果暂时不希望 Agent 自动受项目规则影响，也可以继续不放该文件。

## 8. 下一步最小开发方向

表格工具注册和测试架构已经完成，下一步不建议继续扩大表格解析范围，而是优先补齐真实 API code agent benchmark 闭环：

```text
已完成：表格工具注册进 mini_claude/tools.py
  -> 已完成：项目代码测试迁移到 tests/
  -> 已完成：真实 API benchmark 入口 benchmark_runner.py
  -> 下一步：持续扩展 real_api_code_agent 的任务覆盖和失败分析
  -> 形成更多可复现实验结果
```

优先级：

1. 扩展 `real_api_code_agent` 的真实 API 任务覆盖，记录 `generated_code_path`、`answer_path`、`trace_path`、`workspace_path` 和失败类型。
2. 继续把非 API 检查保留在 `tests/test_unit/` 与 `tests/test_integration/`，不要写成真实 benchmark 成果。
3. API 缺失、依赖缺失、网络不可用或模型未生成代码时必须明确 `SKIP` 或失败。
4. 再考虑 WikiTQ/TabMWP/FinQA/TAT-QA 转换脚本。

暂时不要做：

- SFT/RL。
- 大而全的多数据集适配。
- 复杂 SQL 引擎。
- Excel、多表、多 header、合并单元格的一次性大改。
- 生产级安全沙盒。
- 过度包装简历成果。
