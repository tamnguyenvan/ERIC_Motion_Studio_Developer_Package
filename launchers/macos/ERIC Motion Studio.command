#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h}"
ENTRY_POINT="$PROJECT_ROOT/.venv/bin/eric-motion-studio"

if [[ ! -x "$ENTRY_POINT" ]]; then
  echo "ERIC Motion Studio is not installed in $PROJECT_ROOT/.venv" >&2
  echo "Run: python3.11 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
exec "$ENTRY_POINT" "$@"
