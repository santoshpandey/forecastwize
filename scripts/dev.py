"""Start the API and Next.js UI together. Ctrl+C stops both. Does not auto-approve."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    npm = shutil.which("npm")
    if npm is None:
        print("npm is required", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env.setdefault("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000")
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=BACKEND,
        env=env,
    )
    frontend = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=FRONTEND,
        env=env,
    )
    print("API  http://127.0.0.1:8000/health")
    print("UI   http://localhost:3000")
    print("Stop with Ctrl+C. Human checkpoints are not auto-approved.")

    def _handle_stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handle_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_stop)
    try:
        while True:
            if backend.poll() is not None:
                print("backend exited", backend.returncode, file=sys.stderr)
                _terminate(frontend)
                return backend.returncode or 1
            if frontend.poll() is not None:
                print("frontend exited", frontend.returncode, file=sys.stderr)
                _terminate(backend)
                return frontend.returncode or 1
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nstopping")
        _terminate(frontend)
        _terminate(backend)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
