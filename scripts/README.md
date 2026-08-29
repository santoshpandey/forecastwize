# Scripts

Cross-platform Python entry points; POSIX wrappers for Unix/Git Bash.

| Command | When |
|---|---|
| `make setup` / `.\make.cmd setup` / `./scripts/setup.sh` / `python scripts/setup.py` | `.env` from example if missing; `pip` + `npm ci` |
| `make test` / `.\make.cmd test` / `./scripts/test.sh` / `python scripts/test.py` | Backend pytest + frontend typecheck |
| `make dev` / `.\make.cmd dev` / `./scripts/dev.sh` / `python scripts/dev.py` | API :8000 and UI :3000 |
| `make evaluate-baseline` / `.\make.cmd evaluate-baseline` | `python evaluation/run_baseline.py` |
| `make evaluate-agent` / `.\make.cmd evaluate-agent` | `python evaluation/run_agent.py` |
| `make compare` / `.\make.cmd compare` | `python evaluation/compare.py` |
| `.\scripts\check.ps1` | Windows: ruff, pytest, frontend typecheck, frontend build |
| GitHub Actions `CI` | Lint, pytest, API tests, typecheck, frontend build (no secrets, no catalog eval) |
| GitHub Actions `Evaluation` | Manual catalog harness; writes `evaluation/artifacts/ci-<run_id>/` |
| `make check` | Same checks if GNU Make is installed |
| `python -m evaluation.cases.generators` | Regenerate `data/evaluation/*.csv` from the case registry |

Keep this file in sync with the root README and `docs/reproduction.md`.
