---
name: academic-web-search
description: 当任务需要联网检索论文、arXiv/OpenReview/会议页面、官方文档、GitHub 仓库、数据集主页、benchmark、Agent 框架、LLM API、表格推理、CodeAgent、业务实践或最新工程方案时使用；不仅用于深度学习八股，也用于 TableCodeAgent 项目设计、代码生成前的技术选型、工具实现、benchmark 方案和工程实践依据检索。用户明确要求不联网时不要使用。
---

# academic-web-search

## 技能定位

用于给算法面试、Agent 项目开发、代码生成和技术选型提供可追溯的外部依据。目标是避免“拍脑袋回答”，尤其是在以下场景：

- 深度学习/机器学习八股需要论文依据。
- TableCodeAgent 需要选择工具实现、benchmark、数据集转换、trace schema 或评测指标。
- 生成代码前需要确认官方 API、开源库、论文方法或业界实践是否有更新。
- 用户问“现在主流怎么做”“最新论文怎么说”“有没有官方实现”“这个 benchmark 怎么用”。

## 触发场景

- 用户明确要求联网、检索、查论文、查官方文档、查 GitHub、查数据集。
- 问题涉及近期可能变化的信息：LLM API、开源 Agent 框架、数据集下载方式、benchmark 规则、模型版本、库 API。
- 代码生成依赖外部规范或最佳实践，例如：
  - OpenAI-compatible tool calling schema
  - pandas / pyarrow / duckdb / pytest 最新用法
  - WikiTQ、TabMWP、FinQA、TAT-QA 数据格式
  - Agent trace / ReAct / Toolformer / CodeAct / SWE-agent 等论文或实现
- bagu-explain 需要外部依据来支撑面试回答。

## 不触发场景

- 纯本地文件移动、格式整理、已有代码解释。
- 用户明确要求“不联网”。
- 本地 README、源码、实验日志已经足够回答，且问题不依赖最新外部信息。

## 检索源优先级

1. 论文与官方学术页面：arXiv、OpenReview、ACL Anthology、NeurIPS、ICML、ICLR、KDD、AAAI、EMNLP、COLING 等。
2. 官方文档：OpenAI / Anthropic / PyTorch / pandas / pytest / duckdb / Hugging Face / 数据集主页。
3. 官方或作者 GitHub：论文代码、数据集转换脚本、benchmark runner。
4. 工程实践：高质量技术博客、项目 issue、release notes。
5. 社区问答：知乎、Stack Overflow、论坛，只能作补充，不作为唯一依据。

## 最小检索流程

1. 明确任务类型：
   - 面试八股
   - 论文依据
   - 代码实现前技术选型
   - API / 官方文档确认
   - 数据集 / benchmark 调研
   - 业务实践对照
2. 拆关键词：
   - 中文问题
   - 英文关键词
   - 同义词或论文术语
   - 当前项目关键词，如 `table question answering`、`coding agent`、`tool use`、`trace logging`、`benchmark runner`
3. 至少优先查一手来源：
   - 论文任务：至少 2 个论文/会议/作者来源。
   - API/库任务：至少 1 个官方文档来源。
   - 代码生成任务：至少 1 个官方文档或作者仓库来源。
4. 只把可靠来源纳入最终结论。若只能找到二手来源，必须明确写“证据不足”。

## 输出结构

按任务需要输出，但默认包含：

1. 问题重述：这次检索要解决什么决策。
2. 检索关键词：列出中文和英文关键词。
3. 核心发现：按论文共识、官方规范、工程实践分组。
4. 对 TableCodeAgent 的落地点：
   - 应改哪个模块
   - 是否适合当前 MVP
   - 是否只是后续扩展
   - 对 benchmark / trace / validation 有什么影响
5. 风险与边界：哪些结论不确定、哪些依赖外部版本变化。
6. 来源清单：给出可点击链接，并标注来源类型和年份或更新时间。

## 代码生成前的特别要求

当检索服务于代码生成时，必须把结论转成工程约束：

- 推荐使用哪个库或官方 API。
- 不推荐什么做法，原因是什么。
- 当前项目最小可行实现是什么。
- 哪些内容不能现在包装为已完成能力。
- 是否需要新增测试或 smoke test。
- 是否需要在 `docs/reproduce/` 留下依据和复现记录。

## 质量要求

- 不允许只给二手转述。
- 不允许把论文结论直接夸大成项目已实现。
- 不允许用过期 API 生成代码；涉及现代库/API 时必须核对官方文档。
- 若不同来源冲突，必须说明冲突点和取舍理由。
- 若网页无法访问，说明访问限制，并改用可访问的一手或高质量来源。
