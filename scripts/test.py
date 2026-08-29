"""Run backend pytest and frontend typecheck (same as `make test`)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.check_call(command, cwd=cwd)


def main() -> int:
    _run([sys.executable, "-m", "pytest"], cwd=ROOT / "backend")
    npm = shutil.which("npm")
    if npm is None:
        print("npm is required for frontend typecheck", file=sys.stderr)
        return 1
    _run([npm, "run", "typecheck"], cwd=ROOT / "frontend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
