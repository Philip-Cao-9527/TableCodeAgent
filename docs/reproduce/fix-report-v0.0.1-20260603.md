# fix-report-v0.0.1-20260603

## 1. 本轮目标与范围

本轮目标版本为 `v0.0.1`，用于建立 TableCodeAgent 第一份项目级修复报告与 Codex 协作规范，并记录当前 MVP 第一阶段的表格工具闭环进展。

当前最新状态：已完成项目规范与文档结构整理，已新增并升级 `tablecodeagent` 表格工具层，已将 `load_table`、`profile_table`、`query_table`、`validate_answer` 接入 `mini_claude` 工具 schema 与 `execute_tool()` 分发路径。

仍未完成：trace logger、benchmark runner、`run_python`、`run_tests`、真实 LLM 端到端稳定性验证，以及 WikiTQ/TabMWP/FinQA/TAT-QA 等数据集转换。

目标范围：

1. 新增 TableCodeAgent 项目级 `.codex/AGENTS.md`，把修复报告、版本演进、防御性编程、超长代码拆分等规则项目化。
2. 将原 baseline 教程文档 `docs/00-introduction.md` 到 `docs/14-testing.md` 移入独立目录，避免与 TableCodeAgent 自己的复现记录混在一起。
3. 新增第一份 `docs/reproduce/fix-report-v0.0.1-20260603.md`，建立后续报告格式。
4. 新增并升级表格工具包与 demo 表格任务，验证 CSV 读取、profile、结构化查询与数值答案校验。
5. 将表格工具注册进 `mini_claude` 工具系统，验证不调用 LLM 的 Agent 工具分发闭环。

---

## 2. 改动文件清单

### 2.1 项目级协作规则

- `.codex/AGENTS.md`

### 2.2 文档目录整理

- `_coverpage.md`
- `_sidebar.md`
- `docs/baseline/00-introduction.md`
- `docs/baseline/01-agent-loop.md`
- `docs/baseline/02-tools.md`
- `docs/baseline/03-system-prompt.md`
- `docs/baseline/04-cli-session.md`
- `docs/baseline/05-streaming.md`
- `docs/baseline/06-permissions.md`
- `docs/baseline/07-context.md`
- `docs/baseline/08-memory.md`
- `docs/baseline/09-skills.md`
- `docs/baseline/10-plan-mode.md`
- `docs/baseline/11-multi-agent.md`
- `docs/baseline/12-mcp.md`
- `docs/baseline/13-whats-next.md`
- `docs/baseline/14-testing.md`

### 2.3 修复报告

- `docs/reproduce/fix-report-v0.0.1-20260603.md`

### 2.4 表格工具骨架与 demo benchmark

- `python/pyproject.toml`
- `python/tablecodeagent/__init__.py`
- `python/tablecodeagent/table_tools/__init__.py`
- `python/tablecodeagent/table_tools/core.py`
- `python/tablecodeagent/validation/__init__.py`
- `python/tablecodeagent/validation/answer.py`
- `python/tablecodeagent/tracing/__init__.py`
- `benchmarks/tasks/demo_table_001/data.csv`
- `benchmarks/tasks/demo_table_001/task.json`
- `benchmarks/tasks/demo_table_001/expected.json`

---

## 3. 关键修复内容

### 3.1 新增项目级 Codex 指令

新增 `.codex/AGENTS.md`，明确当前仓库与浏览器扩展项目不同：

- 当前主线是 Coding Agent / TableCodeAgent MVP。
- 不套用 Chrome Web Store、manifest、content script、DOM 注入等浏览器扩展规则。
- 修改前优先读取 `README.md` 与 `docs/reproduce/2026-06-03_tablecodeagent_architecture.md`。
- 修复报告统一放在 `docs/reproduce/`。
- 版本从 `v0.0.1` 开始，按 `PATCH / MINOR / MAJOR` 规则演进。

### 3.2 规范防御性编程边界

新增 Agent 项目语境下的防御性编程规则：

- 禁止无依据截断 prompt、工具输出、CSV、trace。
- 禁止静默吞异常并伪造成功结果。
- 禁止 API 失败后无记录地切换 provider 或模型。
- 禁止表格解析失败后伪造 schema、统计或答案。

这些规则服务于后续 benchmark 和失败分析：失败应被记录和分类，而不是被隐藏。

### 3.3 约束超长代码增长

针对后续容易膨胀的文件新增约束：

- `tools.py` 尽量只保留工具定义、权限、分发和轻量 adapter。
- 表格计算逻辑放入 `python/tablecodeagent/table_tools/`。
- 校验逻辑放入 `python/tablecodeagent/validation/`。
- 轨迹逻辑放入 `python/tablecodeagent/tracing/`。
- 后续 runner / benchmark 逻辑独立拆分，不堆入 `agent.py` 或 `tools.py`。

### 3.4 整理 baseline 教程文档目录

将原 baseline 教程型文档移动到：

```text
docs/baseline/
```

这样 `docs/reproduce/` 可以专门保存 TableCodeAgent 自己的环境、架构、实验和修复报告。

同时更新了中文文档站入口：

- `_coverpage.md`
- `_sidebar.md`
- `docs/baseline/*.md` 内部中文链接

### 3.5 新增最小表格工具骨架

新增 `python/tablecodeagent/` 包，先把表格能力做成可独立测试的本地工具层：

- `load_table`：读取 CSV，返回列名、行数和原始行数据。
- `profile_table`：输出行列数、列名、缺失值统计和数值列统计。
- `query_table`：支持最小聚合查询，当前覆盖 `sum / mean / max / min / count`。
- `validate_answer`：支持数值容差校验和普通精确匹配。

本次只修改 `python/pyproject.toml` 的包发现规则：

```toml
include = ["mini_claude*", "tablecodeagent*"]
```

本次仍未修改：

- `python/mini_claude/agent.py`
- `python/mini_claude/tools.py`
- `python/mini_claude/__main__.py`

### 3.6 新增 demo 表格任务

新增 demo 任务目录：

```text
benchmarks/tasks/demo_table_001/
```

包含：

- `data.csv`：小型销售/订单表。
- `task.json`：问题为计算 `North` 区域的总 `revenue`。
- `expected.json`：标准答案为 `32.5`，容差为 `1e-6`。

---

## 4. 验收方式与结果

### 4.1 文件结构检查

执行：

```bash
find docs -maxdepth 2 -type f | sort
```

预期：

- baseline 教程文档位于 `docs/baseline/`
- TableCodeAgent 复现与报告位于 `docs/reproduce/`

实际结果：

- 已确认 `docs/baseline/00-introduction.md` 到 `docs/baseline/14-testing.md` 存在。
- 已确认 `docs/reproduce/fix-report-v0.0.1-20260603.md` 存在。

### 4.2 引用检查

执行：

```bash
grep -RIn "(docs/[0-9][0-9]-" _coverpage.md _sidebar.md docs/baseline
```

预期：

- 中文入口与中文 baseline 内部链接不再指向旧的 `docs/00` 到 `docs/14` 根目录路径。

实际结果：

- 命令无输出，说明中文入口与中文 baseline 内部链接未发现旧根目录相对链接。

### 4.3 运行时代码影响

本轮未修改：

- `python/mini_claude/agent.py`
- `python/mini_claude/tools.py`
- `python/mini_claude/prompt.py`
- `python/tablecodeagent/table_tools/core.py`
- `python/tablecodeagent/validation/answer.py`

因此本轮不改变 CLI、Agent Loop、工具执行或表格计算行为。

### 4.4 表格工具 smoke test

虽然本轮没有修改运行时代码，仍补跑了最小表格工具 smoke test：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
python - <<'PY'
import json
from pathlib import Path
from tablecodeagent.table_tools.core import load_table, profile_table, query_table
from tablecodeagent.validation.answer import validate_answer

task_dir = Path('benchmarks/tasks/demo_table_001')
task = json.loads((task_dir / 'task.json').read_text())
expected = json.loads((task_dir / 'expected.json').read_text())
table = load_table(task_dir / task['data_file'])
profile = profile_table(task_dir / task['data_file'])
actual = query_table(task_dir / task['data_file'], **task['query'])
result = validate_answer(actual, expected['answer'], expected['tolerance'])
print({'row_count': table['row_count'], 'column_count': profile['column_count'], 'actual': actual, 'passed': result['passed']})
assert table['row_count'] == 5
assert profile['column_count'] == 7
assert actual == 32.5
assert result['passed'] is True
PY
```

结果：

```text
{'row_count': 5, 'column_count': 7, 'actual': 32.5, 'passed': True}
```

### 4.5 表格工具骨架补充验证

新增 `tablecodeagent` 包后，重新执行 editable install：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate tca
cd /root/workspace/TableCodeAgent/python
python -m pip install -e .
```

结果：

```text
Successfully installed claude-code-from-scratch-1.0.0
```

随后执行本地 smoke test：

```bash
cd /root/workspace/TableCodeAgent
python - <<'PY'
import json
from pathlib import Path

from tablecodeagent.table_tools.core import load_table, profile_table, query_table
from tablecodeagent.validation.answer import validate_answer

task_dir = Path("benchmarks/tasks/demo_table_001")
data_path = task_dir / "data.csv"
task = json.loads((task_dir / "task.json").read_text())
expected = json.loads((task_dir / "expected.json").read_text())

table = load_table(data_path)
profile = profile_table(data_path)
actual = query_table(data_path, **task["query"])
result = validate_answer(actual, expected["answer"], expected["tolerance"])

print("table:", {"columns": table["columns"], "row_count": table["row_count"]})
print("profile:", profile)
print("actual:", actual)
print("validation:", result)

assert table["row_count"] == 5
assert profile["column_count"] == 7
assert actual == 32.5
assert result["passed"] is True
PY
```

结果：

```text
table: {'columns': ['order_id', 'date', 'region', 'product', 'quantity', 'unit_price', 'revenue'], 'row_count': 5}
actual: 32.5
validation: {'passed': True, 'actual': 32.5, 'expected': 32.5, 'diff': 0.0}
```

说明：

- 已验证能读取 demo CSV。
- 已验证能输出 schema、行列数、缺失值和数值列统计。
- 已验证能按 `region=North` 过滤并计算 `revenue` 求和。
- 已验证 `validate_answer` 能通过数值容差校验。
- 本验证不依赖 LLM，也不依赖 ChatAnywhere API。

---

## 5. 版本同步清单

- 新增项目规范版本记录：`v0.0.1`
- 新增修复报告：`docs/reproduce/fix-report-v0.0.1-20260603.md`
- 新增 `tablecodeagent` Python 包骨架，但暂未新增代码包版本字段。
- 暂未修改 `python/pyproject.toml` 的项目版本。
- 已修改 `python/pyproject.toml` 的包发现规则，使 editable install 能识别 `tablecodeagent*`。
- 暂未修改 README 版本徽章。

说明：当前 `v0.0.1` 是 TableCodeAgent 开发记录版本，不是 Python package 发布版本。

---

## 6. 风险与备注

- 本轮移动了中文 baseline 教程文档位置；如果还有未检查到的旧链接，可能需要后续补链。
- 英文 `en/docs/` 目录本轮未移动，避免扩大改动面。
- `python -m pip install -e .` 会更新 `python/claude_code_from_scratch.egg-info/SOURCES.txt` 与 `top_level.txt`，这是 editable install 的元数据副作用。
- `__pycache__/` 属于 Python 运行缓存，不应纳入提交；远程仓库中已经跟踪过的 `python/mini_claude/__pycache__/` 已通过 `git rm --cached` 移出 Git 索引，后续 commit/push 后会从 GitHub 删除。
- 当前表格查询能力已升级为轻量结构化聚合，支持基础过滤与数值聚合，但仍不是 SQL 引擎，也不应包装为完整复杂表格推理能力。

---

## 7. 结论

`v0.0.1` 本轮目标已完成：

- 已建立 TableCodeAgent 项目级 Codex 协作规则。
- 已规定修复报告路径、命名格式、内容结构和版本号演进方式。
- 已将 baseline 教程文档移动到 `docs/baseline/`。
- 已生成第一份修复报告。
- 已新增并升级表格工具层与 demo benchmark，并通过本地 smoke test。
- 已将表格工具接入 `mini_claude` 工具 schema 和 `execute_tool()` 分发路径，并通过不调用 LLM 的 Agent 工具注册 smoke test。
- 后续可以继续推进 trace logger、benchmark runner、`run_python`、`run_tests` 和真实 LLM 端到端稳定性验证。

---

# v0.0.1 追加记录：表格工具设计升级与 Agent 注册闭环

记录时间：2026-06-03

## 1. 本轮问题 / 目标与范围

本轮目标是在不引入 `pandas` / `duckdb`、不修改版本号的前提下，把已有 demo 级表格工具升级为更适合 Agent 调用的结构化接口，并接入 `mini_claude` 工具注册与执行分发。

本轮明确不做：

- 不实现 trace logger。
- 不实现 benchmark runner。
- 不实现 `run_python` / `run_tests`。
- 不实现机器学习清洗模板、PSM/IPW/VCNet 专用工具。
- 不创建 `fix-report-v0.0.2-*`，继续在当前 `v0.0.1` 记录中追加。

## 2. 改动文件清单

- `python/tablecodeagent/table_tools/core.py`
- `python/tablecodeagent/validation/answer.py`
- `python/tablecodeagent/agent_tools.py`
- `python/mini_claude/tools.py`
- `scripts/run_table_tools_smoke.sh`
- `scripts/run_agent_table_tools_smoke.sh`
- `scripts/run_demo_table_agent_smoke.sh`
- `README.md`

## 3. 关键修复内容

### 3.1 表格工具层升级

- `load_table` 不再默认返回全量 rows，改为返回表路径、列名、行数和受控 preview。
- `profile_table` 增加字段级画像：
  - 缺失数量与缺失率
  - 唯一值数量
  - 推断类型：`empty`、`integer`、`number`、`date`、`string`
  - 数值统计
  - 列级 flags
- `profile_table` 增加表级质量信息：
  - `duplicate_row_count`
  - `quality_flags`
- `query_table` 改为结构化返回：
  - `value`
  - `metric`
  - `column`
  - `matched_row_count`
  - `total_row_count`
  - `filters`
  - `basis`
- `query_table` 保留旧的 dict 等值过滤写法，同时支持列表式结构化过滤：
  - `eq` / `ne`
  - `gt` / `gte`
  - `lt` / `lte`
  - `contains`

### 3.2 Agent 工具注册

新增 `python/tablecodeagent/agent_tools.py`，集中维护：

- `TABLE_TOOL_DEFINITIONS`
- `TABLE_TOOL_NAMES`
- `execute_table_tool`

`python/mini_claude/tools.py` 只做轻量接入：

- 合并表格工具 schema 到 `tool_definitions`。
- 将表格工具加入 `READ_TOOLS` 和 `CONCURRENCY_SAFE_TOOLS`。
- 在 `execute_tool()` 中把表格工具分发给 `execute_table_tool()`。

表格工具返回统一 JSON 字符串：

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

### 3.3 验证脚本

- `scripts/run_table_tools_smoke.sh` 增加 `PYTHONPATH="$ROOT_DIR/python"`，不再强依赖用户先执行 editable install。
- 新增 `scripts/run_agent_table_tools_smoke.sh`，不调用 LLM，直接验证工具 schema 与 `execute_tool()` 分发路径。
- 新增 `scripts/run_demo_table_agent_smoke.sh`，作为可选 LLM 端到端 demo。env 文件或必要 API 变量缺失时输出 `SKIP`，不伪装为已验证。

## 4. 验收方式 / 手测步骤 / 自动化测试情况

### 4.1 独立表格工具 smoke test

命令：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_table_tools_smoke.sh
```

结果要点：

```text
actual: {'value': 32.5, 'metric': 'sum', 'column': 'revenue', 'matched_row_count': 3, ...}
validation: {'passed': True, 'actual': 32.5, 'expected': 32.5, 'diff': 0.0}
```

### 4.2 Agent 工具注册 smoke test

命令：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_agent_table_tools_smoke.sh
```

结果：

```text
table tool schemas: ['load_table', 'profile_table', 'query_table', 'validate_answer']
query: {'value': 32.5, 'metric': 'sum', 'column': 'revenue', 'matched_row_count': 3, ...}
validation: {'passed': True, 'actual': 32.5, 'expected': 32.5, 'diff': 0.0}
```

### 4.3 Python 编译检查

命令：

```bash
cd /root/workspace/TableCodeAgent
python -m compileall -q python/tablecodeagent python/mini_claude/tools.py
```

结果：

```text
通过，无输出。
```

### 4.4 LLM 端到端 demo

新增命令：

```bash
cd /root/workspace/TableCodeAgent
bash scripts/run_demo_table_agent_smoke.sh configs/api/local/deepseek.env
```

说明：

- 这是可选验证，依赖本地 API 配置和模型稳定性。
- 本轮必过验收基于不调用 LLM 的工具层与工具分发 smoke test。
- 已验证 env 缺失时的 skip 分支：

```bash
bash scripts/run_demo_table_agent_smoke.sh /tmp/nonexistent-tablecodeagent.env
```

结果：

```text
SKIP: API env file not found: /tmp/nonexistent-tablecodeagent.env
```

- 本轮未运行真实 LLM 调用，不把端到端模型调用包装为已验证。

## 5. 版本同步清单

- 不修改 `python/pyproject.toml` 的 package version。
- 不新增 `fix-report-v0.0.2-*`。
- 继续在当前 `v0.0.1` 开发记录中追加核心工具闭环进展。
- README 已同步新增工具能力和验证脚本。

## 6. 风险与备注

- 当前仍只支持 CSV，不支持 Excel、多表、多 header、合并单元格。
- 当前查询仍是轻量结构化聚合，不是 SQL 引擎。
- 当前类型推断是标准库启发式规则，不应包装为生产级 schema inference。
- 最新状态是表格工具已接入 Agent 工具注册，但尚未实现 trace logger 和 benchmark runner，因此还不能宣称已完成完整 TableCodeAgent 评测闭环。

## 7. 结论

本轮完成了 TableCodeAgent MVP 的关键推进：

- 表格工具从简单 demo 函数升级为结构化接口。
- 表格工具已接入 `mini_claude` 工具 schema 和 `execute_tool()` 分发路径。
- 已通过独立工具 smoke test、Agent 工具注册 smoke test 和 Python 编译检查。
- 后续可以继续推进 trace logger、benchmark runner、`run_python` 和更真实的表格任务集。

---

第二次追加记录已拆分到独立文件：

```text
docs/reproduce/fix-report-v0.0.1-trace-benchmark-llm-20260604.md
```
