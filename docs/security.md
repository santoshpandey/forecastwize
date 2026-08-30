# Security

ForecastWize is a **local / single-operator** application. It is not a
multi-tenant SaaS. Authentication is **Planned**. Do not publish the API on a
shared network and assume IDs are secret.

This document matches **implemented** behavior. It does not invent scores or
claim features that are not in the repo.

## Verification checklist

| Check | Status |
|---|---|
| No secrets committed | **Pass.** `.env` is gitignored; `.env.example` has empty `OPENAI_API_KEY=`. Fixture strings like `sk-secretvalue…` exist only in tests to prove redaction. |
| `.env` ignored | **Pass.** `.gitignore` lists `.env` (and `.env.local`). `!.env.example` keeps the template. |
| Uploads cannot execute arbitrary files | **Pass.** `POST /datasets` parses CSV with `pandas.read_csv` only. No pickle, `eval`, shell, or execution of the upload. |
| Filenames cannot escape the upload directory | **Pass.** Client names are sanitized (`sanitize_upload_filename`); storage uses `{dataset_id}.csv` under the API store. `FileStore` resolves paths and refuses anything outside the store directory. Resource IDs are `ds\|fc\|run\|ev_` + 32 hex chars. |
| Sensitive data is not unnecessarily logged | **Pass.** Structured JSON logs redact secret-like **keys** and `sk-…` / `api_key=` substrings in messages and exception text. Trajectory JSONL omits raw training series and redacts the same secret patterns. Dataset logs record id, sanitized filename, and row counts — not CSV bodies. |
| API errors do not expose stack traces | **Pass.** Public body is `{error_code, message, request_id}`. Production 500s use a generic message. Development 500s may include exception type/message but still strip traceback markers. |

## Threat model

| Context | Assumption |
|---|---|
| Local demo / hackathon | Operator and browser on the same machine. Docker Compose publishes **127.0.0.1** only. |
| Shared LAN / cloud | **Out of scope** until authentication exists. Anyone who can reach the port can upload data, start runs, and accept checkpoints. |

## Implemented

### Secrets and configuration

- Load from the environment / optional `.env` (not required to boot).
- `OPENAI_API_KEY` is optional. The orchestrator does **not** call a vendor LLM today. Health reports `llm_configured` from whether the var is non-empty.
- Fail-fast for a required LLM secret is **Planned** (when an LLM-backed agent is wired).
- CORS: `CORS_ORIGINS` allowlist; `allow_credentials=False`.
- `APP_ENV=production` disables `/docs` and `/openapi.json`. Compose sets production. Local uvicorn defaults to development unless `APP_ENV` is set.

### File uploads (`POST /datasets`)

- `Content-Length` is **required** (`411 length_required` if missing).
- Size cap `MAX_UPLOAD_BYTES` (default 10 MiB) on the declared length, streamed JSON body, multipart file chunks, and decoded CSV bytes.
- JSON `csv_text` has a Pydantic `max_length` (32,000,000 characters) as a second ceiling.
- Multipart `Content-Type` allowlist: CSV / plain text / octet-stream / empty.
- Filename: basename only, `.csv` only, no `..`, no absolute paths. Stored name is the sanitized basename in metadata; bytes are written as `{id}.csv`.
- Invalid CSV is a typed `invalid_csv` failure, not a silent coerce.

### Path handling and storage

- API records live under `API_STORE_DIR` (default `data/api/` when the evaluation catalog is present).
- `FileStore.assert_under` / `contained_file` refuse resolved paths outside the intended directory.
- Tool artifacts (`app/evidence/artifacts.py`) reject unsafe ids and refuse reads that escape the artifact root.
- `GET /evaluations/changelog` reads only `docs/changelog.md` after resolving that it stays under `docs/`.

### API inputs

- Pydantic models with `extra=forbid` on request bodies.
- Resource IDs validated before disk access (`404 not_found` for malformed ids — no path probe).
- Checkpoint actions are an allowlist: `accept` \| `reject` \| `review`.
- Concurrent background **runs + evaluations** are capped (`MAX_INFLIGHT_JOBS`, default 4). Excess returns `429 too_many_jobs`. This is not a full HTTP rate limiter.

### Agent tools and LLM prompts

- Tools are **allowlisted** by name. Unknown names are rejected, not executed.
- Tool argument models use `extra=forbid`.
- There are **no live LLM prompts** in this repository. Agents are deterministic Python over structured state. Prompt-injection against a vendor model is **N/A** until an LLM is integrated.
- Agents must not emit yhat / metrics; numerical results come from Python tools only.

### Trajectory storage

- Append-only JSONL under the API store `trajectories/` directory (`{run_id}.jsonl`).
- Secret-like keys and `sk-` patterns redacted; raw series keys omitted (`values`, `timestamps`, …).
- Failed tool calls are recorded, not dropped.

### Logging

- JSON lines to stdout. Keys containing `key` / `secret` / `token` / `password` / `authorization` are `[redacted]`.
- Exception text in logs is run through the same `sk-` / `api_key=` redaction as trajectories.
- Do not log Authorization headers, full CSV bodies, or API keys.

### Frontend

- `NEXT_PUBLIC_API_BASE_URL` is a public origin, not a secret. No API keys in the client bundle.
- Fetch helpers type-guard responses. They do not compute official WIS or other forecast metrics.
- Resource ids are checked against the same prefix+hex pattern before they are placed in URLs (`encodeURIComponent` as well).
- No `dangerouslySetInnerHTML` for changelog or evaluation markdown in a way that executes scripts (markdown is rendered as text / safe components as implemented).

### Docker

- Compose binds **127.0.0.1:8000** and **127.0.0.1:3000** (not `0.0.0.0` on the host).
- Compose `APP_ENV=production` so OpenAPI UI is off on the published port.
- Backend image runs **uvicorn as uid 10001** (`appuser`) via `gosu` after chown of `/app/data/api` (named volume is not writable by a non-root user otherwise).
- Frontend image runs as the `node` user.
- In-container listen address remains `0.0.0.0` so the Docker network and healthcheck can reach the process. Host exposure is the compose `ports` bind.

### Human checkpoints

- `POST /runs/{id}/checkpoint` does not rewrite dataset files. CSV bytes are compared before and after the decision (`source_data_modified` if they differ).
- The graph does not auto-approve. **Anyone who can call the API can accept a waiting run** until auth exists.

### CI

- `.github/workflows/ci.yml` does not use repository secrets. `OPENAI_API_KEY` is empty.
- Catalog evaluation is a separate manual workflow.

## Planned

- Authentication / authorization (and thus protection of checkpoint Accept).
- Fail-fast if a required LLM secret is missing, once LLM-backed agents exist.
- Request rate limits beyond the inflight job cap (per-IP, per-route).
- Network publication (TLS, reverse proxy auth) if the app is ever hosted.

## Residual risks (accepted for this hackathon)

- **No authentication.** Knowing or guessing an id (or calling list-less GET after creating a resource) is enough to read or act on it.
- **CPU-heavy evaluation/forecast jobs** can still load a core; the inflight cap only limits how many run at once.
- **Multipart without a trustworthy Content-Length** is rejected; clients that use chunked encoding without Content-Length cannot upload until that is supported.
- Uploaded series values appear in **API dataset/forecast JSON** for the operator UI. That is intentional. They are not sent to an LLM provider today.
- Catalog evaluation does **not** upload series to a third party. Persist is
  observational and still keeps holdout out of the graph
  (`holdout_passed_to_graph`: false). Trajectories redact secrets and omit
  raw series.

## Third-party APIs

| Dependency | Status | Purpose | Env var | Data leaving the app |
|---|---|---|---|---|
| OpenAI (or equivalent LLM) | **Not integrated** | Future agent reasoning only | `OPENAI_API_KEY` | None today |

If the vendor is down today, the health API still starts (`llm_configured: false`).

## Third-party data

Uploaded CSVs stay on local file storage (`data/api/` or `API_STORE_DIR`). They are not sent to an LLM provider.

## Environment variables

| Name | Role |
|---|---|
| `APP_ENV` | `development` \| `production` |
| `LOG_LEVEL` | Logging level |
| `CORS_ORIGINS` | Comma-separated browser origins |
| `API_HOST` / `API_PORT` | Local bind (scripts). Docker sets host `0.0.0.0` inside the container. |
| `OPENAI_API_KEY` | Optional; unused by the orchestrator today |
| `MAX_UPLOAD_BYTES` | Upload cap |
| `MAX_INFLIGHT_JOBS` | Background run + evaluation cap |
| `API_STORE_DIR` | File store root |
| `NEXT_PUBLIC_API_BASE_URL` | Browser API origin (not a secret) |

See `.env.example`. Never commit `.env`.

## Dependency versions

Backend pins: `backend/requirements.txt`. Frontend lockfile: `frontend/package-lock.json`.
