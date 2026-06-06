---
name: skill-creator
description: TableCodeAgent 项目内 skill 编写与审核规范。新增、修改或审核 .tca/skills/ 下的项目 skill 时使用；不用于修改 /root/.codex/skills/ 下的全局系统 skill，也不代表完整自动创建 skill 系统已经实现。
---

# TableCodeAgent Skill Creator

## 适用范围

本规范只约束 TableCodeAgent 仓库内 `.tca/skills/` 下的项目内 skill。它用于编写、更新和审核项目 skill 的结构、中文友好表达、边界、验证证据和失败处理。

本规范不等价于 `/root/.codex/skills/.system/skill-creator/SKILL.md`，也不授权修改全局系统 skill。

## 不适用范围

- 不用于创建 Codex 全局 skill。
- 不用于声明 Claude Code / Codex 已具备完整自动创建 skill 系统。
- 不用于把项目 skill 写成宣传页、泛泛教程或不可验证能力清单。

## 推荐目录结构

项目内 skill 推荐按如下结构组织：

```text
skill-name/                               # required：skill 根目录；目录名与 skill name 保持一致
├── SKILL.md                              # required：skill 入口与规范正文
├── agents/                               # required：存放 skill 配套 agent 元数据
│   └── agent.yaml                        # required：面向 Claude Code / Codex skill 界面的元数据
├── scripts/                              # optional：可执行脚本；只放可复用、确定性更强的逻辑
├── references/                           # optional：按需读取的参考资料，不把大段细节塞进 SKILL.md
└── assets/                               # optional：供输出复用的模板、示例、静态资源
```

- `SKILL.md` 是必填文件。
- `agents/agent.yaml` 是强制项；每个项目内 skill 都必须提供该文件，用于承接稳定的列表展示、默认提示和 UI 元数据。
- `scripts/`、`references/`、`assets/` 都是可选目录；没有真实内容时，本轮默认不强制创建空目录。
- `references/` 用于“按需读取”；不要把本应放在 `references/` 的大段 schema、示例或长说明重复写进 `SKILL.md`。
- `assets/` 只放给产物复用的文件，不放审核说明、变更记录或教程。

## `SKILL.md` 必填结构

每个项目 skill 的 `SKILL.md` 至少包含：

- YAML frontmatter。
- `name`。
- `description`。
- Markdown 标题。
- 适用范围。
- 不适用范围或边界。
- 执行步骤。
- 输入输出约定。
- 证据与验证要求。
- 注意事项或失败处理。

## frontmatter 要求

- frontmatter 必填，且必须位于文件开头。
- `name`、`description` 必填。
- `name` 使用稳定、可读、可检索的英文 id，优先小写加连字符，例如 `growth-campaign-audit`。
- `description` 必须说明 skill 做什么、什么时候触发、什么时候不该触发。
- 如需补充元数据，可额外增加字段，但不能削弱 `name` 与 `description` 的清晰度。
- 禁止空泛宣传语，例如“强大的智能分析专家”“万能数据助手”。
- 不要把未验证能力写成已实现能力。

## `agents/agent.yaml` 必须提供

- 每个项目内 skill 都必须提供 `agents/agent.yaml`。
- `SKILL.md` 负责正文规范，`agents/agent.yaml` 负责列表展示、默认提示和可复用的 agent 元数据，两者缺一不可。
- 新增 skill 时，应同时创建 `SKILL.md` 与 `agents/agent.yaml`；更新 skill 时，应同步检查两者是否仍匹配。

`agents/agent.yaml` 中的要求：

- 面向人阅读的说明字段优先中文友好，例如 `display_name`、`short_description`、`default_prompt`。
- 模型名、provider、tool id、schema 字段、路径保留英文原文。
- 必须写清用途、边界、依赖、是否需要真实 API、失败或 `SKIP` 如何暴露。
- 更新 `SKILL.md` 后，应同步检查 `agents/agent.yaml` 是否仍匹配。

## 目录用途与边界

### `scripts/`

- 只放可执行、可复用、重复出现时值得沉淀的脚本。
- 适合承载确定性更强、容易反复重写的逻辑。
- 不要把纯说明文案、随手实验代码或一次性草稿塞进 `scripts/`。

### `references/`

- 只放按需读取的参考资料，例如 schema、接口约束、任务示例、领域规则。
- `SKILL.md` 中要写清“什么时候需要读 `references/`”，避免每次都把全部参考资料读入上下文。
- 参考资料较大时，优先在 `SKILL.md` 给出文件名和定位提示，而不是把大段内容复制进正文。

### `assets/`

- 只放产物复用资源，例如模板、图片、静态文件、示例输入。
- 不要把 README、CHANGELOG、review note、fix-report 之类的说明文件放进 skill 目录。

## 中文友好要求

- 项目内 skill 默认优先使用简体中文，便于用户审核。
- 工具名、路径、API 字段名、模型名、库名、命令、代码块保留英文原文。
- 不因为中文化而破坏 frontmatter、文件路径、工具 id、字段名、schema 或调用约定。
- 不要写“整句英文规则 + 下一句中文补充”或“纯英文短句后直接接中文说明”这类混排；必须保留的英文术语应用反引号包住，并嵌入中文句子中。

## 输入输出约定

- 输入至少写清触发条件、必要前置文件、依赖环境和允许读取的关键路径。
- 输出至少写清预期产物是什么，例如报告、代码、修改建议、结果文件路径或 `SKIP` 结论。
- 若 skill 会生成代码、调用 benchmark、读取 trace 或分析 workspace，必须写清关键证据文件路径应该落到什么粒度。
- 若 skill 只产出建议或 prompt，也要写明不直接修改哪些文件。

## 证据与验证要求

- skill 应突出可执行规则、边界、验证证据和失败处理。
- 不要写成泛泛教程。
- 不要把 `SKIP`、依赖缺失、env 缺失、未实际调用 API 写成通过。
- 如果 skill 包含脚本或外部依赖，必须说明安全边界、依赖安装方式和验证方式。
- 涉及 benchmark 或真实 API 时，必须明确 `api_called`、`skipped`、`failure_type`、`result_dir`、`trace_path` 等证据字段。
- fix-report、trace、workspace、测试和结果说明要优先给“具体文件名 + 可跳转路径”，不要只给目录名。

## 失败处理与 `SKIP`

- 无法验证时必须显式写明 `SKIP` 或“未验证”，并说明原因。
- 失败处理应暴露真实阻塞点，例如 env 缺失、依赖缺失、测试失败、路径不存在、结果结构不符。
- 不要把“没有跑”“没有 API”“没有 trace”“没有 answer.json”包装成通过。

## 编写 / 审核清单

1. 适用范围是否清楚，能判断这个 skill 什么时候该用、什么时候不该用。
2. 目录结构是否清楚，`SKILL.md` 是否存在，是否只在有真实内容时才引入 `scripts/`、`references/`、`assets/`、`agents/`。
3. frontmatter 是否合法，且至少包含 `name` 与 `description`。
4. 中文友好是否达标，且没有误改路径、字段名、工具 id、命令。
5. 输入输出约定是否可执行，是否说明前置条件、预期产物和不可越界的内容。
6. 证据与验证要求是否具体，是否说明应查看哪些文件、哪些命令或哪些结果字段。
7. 失败处理与 `SKIP` 是否明确，是否避免把未验证写成通过。
8. 与 `/root/workspace/TableCodeAgent/.codex/AGENTS.md` 的关系是否清楚，是否遵守仓库级约束但未重复堆砌模板。
9. 与 `/root/.codex/skills/...` 的边界是否清楚，是否避免把项目内规范误写成全局系统 skill 改造。
10. 若引用 `references/`，是否写清读取时机；`agents/agent.yaml` 是否存在且与 `SKILL.md` 内容一致。

## 与仓库级 AGENTS 的关系

`/root/workspace/TableCodeAgent/.codex/AGENTS.md` 只保留简洁索引规则：新增、修改或审核 `.tca/skills/` 必须遵守本规范。

不要在仓库级 AGENTS 中复制完整 skill 模板。后续新增或修改 `.tca/skills/` 时，以本规范为准。

## 与全局 `/root/.codex/skills/...` 的边界

- `/root/.codex/skills/.system/skill-creator/SKILL.md` 只作为组织方式参考，不是本仓库可直接修改的目标文件。
- 本仓库任务默认只修改 `.tca/skills/` 下的项目内 skill 资产。
- 不要把项目内 skill 规范写成“全局系统 skill 已同步升级”。
