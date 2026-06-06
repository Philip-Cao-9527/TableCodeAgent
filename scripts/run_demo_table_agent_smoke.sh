#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

ENV_FILE="${1:-configs/api/local/provider_chatanywhere.env}"
TASK_DIR="${2:-benchmarks/tasks/demo_table_001}"

python -m tablecodeagent.benchmark.runner \
  --task-dir "$TASK_DIR" \
  --mode optional_llm_agent \
  --env "$ENV_FILE"
