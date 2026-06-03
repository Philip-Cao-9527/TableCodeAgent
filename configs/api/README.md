# API 配置说明

## 目标

本目录用于记录 TableCodeAgent 开发过程中使用的不同 LLM API 配置模板。

项目当前优先使用低成本 OpenAI-compatible API，例如 DeepSeek API。后续可以根据价格、稳定性、上下文长度、工具调用表现，继续尝试其他厂商。

本目录只记录 API 接入方式，不代表项目已经完成多模型评测。后续只有在 benchmark 跑完之后，才能记录不同 API 的真实成本、成功率和稳定性。

## 文件规则

* `*.env.example`：可以提交，只放模板，不放真实 key。
* `local/`：不能提交，用于存放真实 API Key。
* `.env` / `.env.local`：不能提交。
* 真实 API Key 只通过环境变量加载，不写进代码、不写进 README、不写进日志。

## 推荐目录结构

```text
configs/api/
├── README.md
├── deepseek.env.example
├── openai_compatible.env.example
└── local/
    └── deepseek.env
```

其中：

* `README.md`：记录 API 配置规则。
* `deepseek.env.example`：DeepSeek 配置模板，可以提交。
* `openai_compatible.env.example`：通用 OpenAI-compatible API 配置模板，可以提交。
* `local/deepseek.env`：真实 DeepSeek API Key，只在本地或服务器存在，不提交。

## DeepSeek 配置方式

复制模板：

```bash
cp configs/api/deepseek.env.example configs/api/local/deepseek.env
```

编辑真实配置：

```bash
vim configs/api/local/deepseek.env
```

配置内容示例：

```bash
export OPENAI_API_KEY="你的真实 DeepSeek API Key"
export MINI_CLAUDE_MODEL="deepseek-v4-flash"
export MINI_CLAUDE_API_BASE="https://api.deepseek.com"
```

加载环境变量：

```bash
source configs/api/local/deepseek.env
```

运行最小测试：

```bash
mini-claude-py \
  --api-base "$MINI_CLAUDE_API_BASE" \
  --model "$MINI_CLAUDE_MODEL" \
  --max-turns 3 \
  --plan "请用中文介绍当前项目目录，不要修改任何文件。"
```

## 通用 OpenAI-compatible API 配置方式

如果后续尝试其他便宜 API，可以复制通用模板：

```bash
cp configs/api/openai_compatible.env.example configs/api/local/provider_x.env
```

然后编辑：

```bash
vim configs/api/local/provider_x.env
```

配置内容示例：

```bash
export OPENAI_API_KEY="你的真实 API Key"
export MINI_CLAUDE_MODEL="你的模型名"
export MINI_CLAUDE_API_BASE="https://your-provider-base-url/v1"
```

加载后运行：

```bash
source configs/api/local/provider_x.env

mini-claude-py \
  --api-base "$MINI_CLAUDE_API_BASE" \
  --model "$MINI_CLAUDE_MODEL" \
  --max-turns 3 \
  --plan "请用中文介绍当前项目目录，不要修改任何文件。"
```

## 安全注意事项

1. 不要把真实 API Key 写进代码。
2. 不要把真实 API Key 写进 README。
3. 不要把真实 API Key 写进日志。
4. 不要提交 `configs/api/local/` 目录。
5. 不要提交 `.env`、`.env.local` 或其他真实环境配置文件。
6. 如果真实 Key 被误提交，需要立即删除 Git 追踪记录，并在 API 平台重置 Key。

## 当前阶段边界

当前阶段只做 API 接入和 baseline smoke test，不做多模型路由、不做自动选模、不做成本优化算法。

后续 benchmark 跑通后，才可以记录：

* 不同 API 的任务通过率
* 数值正确率
* 工具调用成功率
* 平均 token 消耗
* 平均耗时
* 平均调用成本
* 失败类型分布
