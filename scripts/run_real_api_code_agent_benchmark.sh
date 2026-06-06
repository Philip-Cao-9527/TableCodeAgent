#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

ENV_FILE="${1:-configs/api/local/provider_chatanywhere.env}"
TASK_DIR="${2:-benchmarks/tasks/growth_campaign_audit_001}"
TASK_GROUP="${3:-}"

args=(
  python -m tablecodeagent.benchmark.benchmark_runner
  --env "$ENV_FILE"
  --task-dir "$TASK_DIR"
)

if [[ -n "$TASK_GROUP" ]]; then
  args+=(--task-group "$TASK_GROUP")
fi

"${args[@]}"
