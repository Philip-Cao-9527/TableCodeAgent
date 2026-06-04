#!/usr/bin/env bash
set -e

API_ENV_FILE="${1:-provider_chatanywhere.env}"

# 这里用正则表达式限制 env 文件名：
# ^provider[A-Za-z0-9_-]*\.env$ 表示必须以 provider 开头，
# 后面只能接“字母/数字/下划线/短横线”，最后必须是 .env。
# 例如 provider_chatanywhere.env 合法，deepseek.env、../secret.env 或 provider.txt 不合法。
if [[ ! "$API_ENV_FILE" =~ ^provider[A-Za-z0-9_-]*\.env$ ]]; then
  echo "Invalid env file name: $API_ENV_FILE" >&2
  echo "Usage: bash scripts/run_openai_compatible_smoke.sh provider_chatanywhere.env" >&2
  exit 1
fi

source "configs/api/local/$API_ENV_FILE"

mini-claude-py \
  --api-base "$MINI_CLAUDE_API_BASE" \
  --model "$MINI_CLAUDE_MODEL" \
  --max-turns 3 \
  --plan "请用中文介绍当前项目目录，不要修改任何文件。"
