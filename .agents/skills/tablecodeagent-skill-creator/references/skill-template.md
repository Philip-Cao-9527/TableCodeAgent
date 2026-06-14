# TableCodeAgent 项目本地 Skill 写作底稿

本文件是 `tablecodeagent-skill-creator` 的参考底稿。使用时按具体任务裁剪成真实 skill 内容，不原样输出，不保留空标题、占位字段或一次性任务残留。

## 推荐最小结构

只创建本轮真实需要的文件。常见结构如下：

```text
.agents/skills/项目化-skill-名称/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── references/
    └── 可复用底稿.md
```

如果没有可复用模板或长检查清单，不创建 `references/`。不要创建空目录、README、CHANGELOG 或未来占位文件。

## SKILL.md 应包含的真实内容

`SKILL.md` 的 frontmatter 只保留实际值：

```markdown
---
name: 使用小写字母数字和连字符的真实名称
description: 写清这个 skill 的用途、触发场景和边界
---
```

正文建议覆盖：

- 技能定位：唯一主职责、适用场景、不适用场景、最终产物。
- 与现有指令资产的边界：`.codex/AGENTS.md`、`$tablecodeagent-dev-prompt`、`$tablecodeagent-plan-mode-prompt`、`$tablecodeagent-code-review-prompt` 分别负责什么，当前 skill 不接管什么。
- 必读文件：`.codex/AGENTS.md`、`README.md`、`docs/reproduce/tablecodeagent_architecture.md`、`docs/reproduce/why_table_code_agent.md` 和目标流程直接相关文件。
- 使用流程：确认适用性、读取材料、整理输入、使用参考底稿、生成最终产物。
- 输出要求：最终回答或生成文件必须包含什么；若产物是 prompt，整体放入一个 Markdown 文本块。
- 验证要求：文件存在、UTF-8 可读、frontmatter、YAML、references 引用路径和职责边界。

## agents/openai.yaml 写法

`agents/openai.yaml` 只写真实 UI 字段：

```yaml
interface:
  display_name: "简短中文展示名"
  short_description: "说明这个 skill 的主要用途"
  default_prompt: "使用 $skill-name 形式的真实 skill 名称完成当前 TableCodeAgent 项目本地 skill 任务。"
```

## 质量标准

- skill 名称只使用小写字母、数字和连字符。
- `description` 必须写清触发场景和边界。
- 不把 TableCodeAgent 完整项目规则复制进每个 skill。
- 不把一次性任务、旧项目路径、旧版本号、浏览器扩展约束或旧测试命令写进 TableCodeAgent。
- 不把项目本地 `.agents/skills` 写成当前会话一定自动加载。
- 跨 skill 调用或路由写成 `$skill-name`；文件路径只用于说明源码位置、必读文件或验证证据。
- 修改仅限 `.agents/skills/` 下本轮目标 skill 文件。
