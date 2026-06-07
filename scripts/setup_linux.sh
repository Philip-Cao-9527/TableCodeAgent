#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SKIP_TESTS=0
if [[ "${1:-}" == "--skip-tests" ]]; then
  SKIP_TESTS=1
fi

if [[ -n "${VIRTUAL_ENV:-}" || -n "${CONDA_PREFIX:-}" ]]; then
  PYTHON_BIN="${PYTHON:-python}"
else
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  PYTHON_BIN=".venv/bin/python"
fi

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements-dev.txt

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

echo "Python: $PYTHON_BIN"
echo "PYTHONPATH: $PYTHONPATH"
echo "Non-API test command: $PYTHON_BIN -m pytest tests/test_unit tests/test_integration"

if [[ "$SKIP_TESTS" != "1" ]]; then
  "$PYTHON_BIN" -m pytest tests/test_unit tests/test_integration
fi
