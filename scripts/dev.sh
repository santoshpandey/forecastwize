#!/usr/bin/env bash
# Start API (:8000) and Next.js (:3000). Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi
exec "$PYTHON" scripts/dev.py
