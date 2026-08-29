"""Install pinned dependencies and create .env from the example. No secrets."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 12)
MIN_NODE_MAJOR = 22


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.check_call(command, cwd=cwd)


def _python_ok() -> None:
    if sys.version_info < MIN_PYTHON:
        _fail(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required (found {sys.version.split()[0]})."
        )


def _node_ok() -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node is None or npm is None:
        _fail("Node.js 22+ and npm are required (install Node 22 LTS).")
    raw = subprocess.check_output([node, "-v"], text=True).strip().lstrip("v")
    major = int(raw.split(".", 1)[0])
    if major < MIN_NODE_MAJOR:
        _fail(f"Node.js {MIN_NODE_MAJOR}+ is required (found v{raw}).")


def _ensure_env() -> None:
    example = ROOT / ".env.example"
    dest = ROOT / ".env"
    if not example.is_file():
        _fail("Missing .env.example")
    if dest.is_file():
        print(f"keeping existing {dest}")
        return
    dest.write_bytes(example.read_bytes())
    print(f"wrote {dest} from .env.example (no secrets)")


def main() -> int:
    _python_ok()
    _node_ok()
    _ensure_env()
    _run([sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"], cwd=ROOT)
    npm = shutil.which("npm")
    if npm is None:
        _fail("npm is required")
    lock = ROOT / "frontend" / "package-lock.json"
    if not lock.is_file():
        _fail("frontend/package-lock.json is required for npm ci")
    _run([npm, "ci"], cwd=ROOT / "frontend")
    print("setup complete")
    print(f"python {sys.version.split()[0]}")
    node = shutil.which("node")
    if node:
        print("node", subprocess.check_output([node, "-v"], text=True).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
