#!/usr/bin/env bash
set -e

source configs/api/local/deepseek.env

mini-claude-py \
  --api-base "$MINI_CLAUDE_API_BASE" \
  --model "$MINI_CLAUDE_MODEL" \
  --max-turns 3 \
  --plan "请用中文介绍当前项目目录，不要修改任何文件。"
