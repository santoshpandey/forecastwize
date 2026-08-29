# Reproduction

Exact commands from a clean machine. Scores live in generated JSON, not in this
page. Re-running evaluation writes a **new** `evaluation_run_id` and overwrites
`evaluation/results/*.json`. The cited official pair is the committed files
named below.

## Recorded versions

| Item | Pin / recorded value |
|---|---|
| Python | **3.12+** (`.python-version` is `3.12`). Official baseline JSON recorded `3.12.10` |
| Node.js | **22+** (`.nvmrc` is `22`). Lockfile installs Next **15.5.24** |
| npm | **10+** (`npm ci` from `frontend/package-lock.json`) |
| Backend packages | `backend/requirements.txt` (exact `==` pins) |
| Frontend packages | `frontend/package-lock.json` via `npm ci` |
| Evaluation catalog | `catalog_id`: `forecastwize-eval-v1`, `catalog_version`: **1** |
| Case registry | `evaluation/cases/case_registry.yaml` |
| Coverage / backtest | coverage `0.95`; expanding window; target 5 folds |
| Official baseline run | `evaluation_run_id` `baseline-20260829T125209Z` |
| Official agent run | `evaluation_run_id` `agent-20260829T125231Z` |
| Official comparison | `comparison_id` `comparison-20260829T125254Z` |

### Backend pins (`backend/requirements.txt`)

fastapi 0.116.1, uvicorn 0.35.0, pydantic 2.11.7, pydantic-settings 2.10.1,
httpx 0.28.1, python-multipart 0.0.20, pytest 8.4.1, ruff 0.12.10,
pandas 2.2.3, numpy 2.2.6, scipy 1.15.3, statsmodels 0.14.4, pyyaml 6.0.2.

### Case random seeds

Each case uses a fixed `random_seed` in the registry (also stored per row in
evaluation JSON):

| case_id | seed | CSV |
|---|---|---|
| 001 | 1001 | `data/evaluation/001_trend.csv` |
| 002 | 1002 | `data/evaluation/002_stable_seasonality.csv` |
| 003 | 1003 | `data/evaluation/003_trend_seasonality.csv` |
| 004 | 1004 | `data/evaluation/004_noisy_trend.csv` |
| 005 | 1005 | `data/evaluation/005_missing_values.csv` |
| 006 | 1006 | `data/evaluation/006_outliers.csv` |
| 007 | 1007 | `data/evaluation/007_structural_break.csv` |
| 008 | 1008 | `data/evaluation/008_event_context_change.csv` |
| 009 | 1009 | `data/evaluation/009_intermittent_demand.csv` |
| 010 | 1010 | `data/evaluation/010_short_history.csv` |
| 011 | 1011 | `data/evaluation/011_long_horizon.csv` |
| 012 | 1012 | `data/evaluation/012_adversarial_regime_change.csv` |

Do not hand-edit those CSVs. Regeneration must match committed bytes
(`python -m evaluation.cases.generators`).

## Make targets

These commands are implemented in `Makefile` (GNU Make) and `make.cmd` (Windows):

```text
make setup
make test
make dev
make evaluate-baseline
make evaluate-agent
make compare
```

If GNU Make is not on `PATH` (this is common on Windows PowerShell), run
`.\make.cmd test` from the repository root, or `cmd /c make test`.

---

## 1. Prerequisites

- **Git**
- **Python 3.12+** on `PATH` as `python` (Unix: `python3` is fine if you export `PYTHON=python3`)
- **Node.js 22+** and **npm 10+**
- **GNU Make** (for `make …` targets). Windows without Make: from the repo root,
  `.\make.cmd test` (same targets as the Makefile)
- Optional: **Docker Compose v2** for container startup

Confirm:

```bash
python --version
node -v
npm -v
```

Expect Python 3.12.x and Node v22.x (or newer major, still ≥ 22).

---

## 2. Clone the repository

```bash
git clone <repository-url> forecastwize
cd forecastwize
```

Use the clone URL for this project. Work from the repository root for every
command in this file unless a `cd` is shown.

---

## 3. Environment setup

Copy the example env file. Never commit `.env`. Leave `OPENAI_API_KEY` empty;
the orchestrator does not call an LLM.

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
copy .env.example .env
```

`make setup` copies `.env.example` → `.env` only when `.env` is missing.

---

## 4. Dependency installation

Pinned install (preferred):

```bash
make setup
```

Equivalent:

```bash
chmod +x scripts/setup.sh scripts/test.sh scripts/dev.sh
./scripts/setup.sh
```

Manual:

```bash
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
cd ..
```

Windows PowerShell:

```powershell
python -m pip install -r backend/requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

`npm ci` uses `frontend/package-lock.json`. Do not use an un-locked `npm install`
if you need a bit-for-bit frontend install.

Print recorded interpreter versions:

```bash
make versions
```

---

## 5. Sample application startup

### Make / scripts

```bash
make dev
```

or:

```bash
./scripts/dev.sh
```

- API: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) — JSON `status: ok`
- UI: [http://localhost:3000](http://localhost:3000)

Stop with Ctrl+C. Checkpoints are **not** auto-approved.

Separate terminals (same as README):

```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev
```

### Docker

From the repository root (after `.env` exists or compose env vars below):

```bash
docker compose up --build
```

or `make docker-up`. Host ports bind to **127.0.0.1** (see `docker-compose.yml`).
The browser still calls `http://localhost:8000` (`NEXT_PUBLIC_API_BASE_URL`).
API file records persist in the `api-store` volume. Evaluation dashboard JSON is
copied into the backend image from `evaluation/results/` and `docs/changelog.md`.
Compose sets `APP_ENV=production` (no `/docs`). Override to `development` only
on a trusted machine if you need the OpenAPI UI.

---

## 6. Baseline evaluation

From the repository root. Same 12 cases, seeds, splits, and metric functions as
the agent path.

```bash
make evaluate-baseline
```

Equivalent:

```bash
python evaluation/run_baseline.py
```

Writes:

- `evaluation/results/baseline.json`
- `evaluation/results/baseline.md`

Stdout includes `case_list`, `official_wis`, and `n_failed`. Official aggregate
WIS is **null** when any case fails. The committed EXP-008 pair has
`n_failed` 0. Do not use completed-only WIS as the official number.

Optional paths (does not change Make defaults):

```bash
python evaluation/run_baseline.py --output-json /tmp/baseline.json --output-md /tmp/baseline.md
```

---

## 7. Advanced evaluation

**Identical** `case_list`, CSVs, horizons, frequencies, and seeds. Holdout is
not passed into the graph.

```bash
make evaluate-agent
```

Equivalent:

```bash
python evaluation/run_agent.py
```

Writes:

- `evaluation/results/agent.json`
- `evaluation/results/agent.md`

This run can take several minutes. It overwrites the agent JSON if you use the
default paths.

---

## 8. Comparison

Requires the two JSON files from steps 6–7 (or the committed pair).

```bash
make compare
```

Equivalent:

```bash
python evaluation/compare.py
```

Writes `evaluation/results/comparison.json`. Valid only when `case_lists_identical`
is true. Primary metric is WIS (`relative_improvement` in that file — not a
number typed into docs). Failed cases stay in the record.

Optional:

```bash
python evaluation/compare.py --baseline evaluation/results/baseline.json --agent evaluation/results/agent.json --output-json evaluation/results/comparison.json
```

---

## 9. Tests

```bash
make test
```

or:

```bash
./scripts/test.sh
```

This runs backend **pytest** and frontend **tsc** (`npm run typecheck`).

Full lint + pytest + frontend production build:

```bash
make check
```

Windows without Make:

```powershell
.\scripts\check.ps1
```

`check.ps1` also runs `npm run build`. Expect pytest **exit code 0**. Do not
treat a remembered test count as a pin.

CSV generators are asserted byte-identical to `data/evaluation/*.csv` in pytest.

## CI (GitHub Actions)

Ordinary CI (`.github/workflows/ci.yml`) runs on pull requests and on `main` /
`master`. It does **not** set `OPENAI_API_KEY` and does **not** run the catalog
evaluation harness.

Jobs (failures are isolated; JUnit XML is uploaded):

1. Python lint (Ruff check + format)
2. Python tests (`pytest -m "not api"`)
3. API tests (`pytest -m api`, FastAPI TestClient)
4. TypeScript typecheck (`npm run typecheck`)
5. Frontend build (`npm run build`)

Re-run from the Actions tab (workflow_dispatch) if needed.

Catalog evaluation is **manual only**: Actions → **Evaluation** → Run workflow.
Default is baseline only. Turn on `run_agent` for the slow agent harness (still
no LLM). Outputs go to `evaluation/artifacts/ci-<run_id>/` and a workflow
artifact; committed `evaluation/results/` is not overwritten.

---

## 10. Expected output files

| Path | What it is |
|---|---|
| `evaluation/results/baseline.json` | Baseline harness: `evaluation_run_id`, `git_commit`, `catalog_id`, `catalog_version`, per-case seeds/metrics, library pins |
| `evaluation/results/baseline.md` | Human-readable summary of that JSON |
| `evaluation/results/agent.json` | Agent harness on the same cases |
| `evaluation/results/agent.md` | Agent summary |
| `evaluation/results/comparison.json` | Computed deltas; `comparison_id`; cites the two `evaluation_run_id`s |
| `evaluation/artifacts/EXP-*/` | Isolated experiment pairs (006–008) |
| `evaluation/artifacts/exp-initial-comparison/` | Frozen first catalog pair (official WIS null) |
| `backend/tests/fixtures/trajectories/*.jsonl` | Checked-in agent trajectory examples |
| `data/evaluation/*.csv` | Shared synthetic cases (committed; regenerate only via the generator) |
| `GET /health` | `status: ok`, `service`, `version`, `environment`, `timestamp`, `llm_configured` |

**Cited official artifacts** (do not replace these IDs with remembered WIS):

- `baseline-20260829T125209Z`
- `agent-20260829T125231Z`
- `comparison-20260829T125254Z`

(EXP-008 pair, also under `evaluation/artifacts/EXP-008-full-candidates/`.)
The pre-iteration control is `evaluation/artifacts/exp-initial-comparison/`
(`baseline-20260829T123106Z` / `agent-20260829T123136Z` /
`comparison-20260829T123158Z`).

A fresh `make evaluate-baseline` produces a **new** `evaluation_run_id` (timestamp).
Baseline **point/interval metrics** for completed cases should match the committed
JSON when Python 3.12.x and the pinned numeric libraries match. `git_commit` and
`evaluation_run_id` will differ.

Copy existing `evaluation/results/*.json` aside before a new official run if you
need to keep the cited pair.

---

## 11. Agent trajectories

Schema and reviewer sequence: [trajectories/README.md](../trajectories/README.md).

| Path | What it is |
|---|---|
| `backend/tests/fixtures/trajectories/*.jsonl` | Checked-in examples (success, verification retry, tool failure) |
| `GET /runs/{id}/trajectory` | Live run JSONL after `POST /runs` |
| API store `trajectories/{run_id}.jsonl` | Same file on disk (`data/api/` default; gitignored) |
| Catalog `run_agent.py` | Default `persist_trajectory=False` (see `evaluation/results/agent.json`) |

Do not expect a JSONL file per catalog case in `trajectories/` from the default
eval command.

---

## Cited scores (do not invent)

From `evaluation/results/comparison.json` (`comparison-20260829T125254Z`):
WIS `relative_improvement` **0.0**; `n_cases_failed` 0 both sides;
`human_intervention_count` 12 on the agent. Full field table:
[evaluation.md](evaluation.md).

Frozen first catalog pair (official WIS **null**, 005 failed):
`evaluation/artifacts/exp-initial-comparison/`.

