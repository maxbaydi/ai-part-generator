#!/usr/bin/env sh
set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -n "${AI_PART_GENERATOR_PYTHON:-}" ]; then
  PYTHON="$AI_PART_GENERATOR_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Python не найден. Установите Python или задайте AI_PART_GENERATOR_PYTHON" >&2
  exit 1
fi

if ! "$PYTHON" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo "Не найдены зависимости bridge (fastapi/uvicorn)." >&2
  echo "Установите: $PYTHON -m pip install -r \"${SCRIPT_DIR}/requirements.txt\"" >&2
  exit 1
fi

exec "$PYTHON" "${SCRIPT_DIR}/app.py"

