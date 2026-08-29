#!/usr/bin/env bash
# Install pinned Python and Node dependencies. Copy .env.example → .env if needed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi
exec "$PYTHON" scripts/setup.py
