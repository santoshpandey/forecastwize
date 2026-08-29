import type {
  ChangelogDocument,
  DatasetResponse,
  EvaluationCompareResponse,
  EvaluationDashboardResponse,
  EvaluationResponse,
  HealthResponse,
  PublicError,
  RunResponse,
} from "./types";

export const defaultApiBaseUrl = "http://localhost:8000";

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? defaultApiBaseUrl;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly errorCode?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isPublicError(value: unknown): value is PublicError {
  return (
    isRecord(value) &&
    typeof value.error_code === "string" &&
    typeof value.message === "string"
  );
}

const RESOURCE_ID = /^(ds|fc|run|ev)_[0-9a-f]{32}$/;

function requireResourceId(id: string): string {
  if (!RESOURCE_ID.test(id)) {
    throw new ApiError("Resource was not found.", 404, "not_found");
  }
  return id;
}

async function readError(response: Response): Promise<never> {
  const payload: unknown = await response.json().catch(() => null);
  if (isPublicError(payload)) {
    throw new ApiError(payload.message, response.status, payload.error_code);
  }
  throw new ApiError(`Request failed (${response.status})`, response.status);
}

async function requestJson<T>(
  path: string,
  options: RequestInit,
  guard: (value: unknown) => value is T,
): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    await readError(response);
  }
  const payload: unknown = await response.json();
  if (!guard(payload)) {
    throw new ApiError("Response did not match the API contract", response.status);
  }
  return payload;
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    isRecord(value) &&
    value.status === "ok" &&
    typeof value.service === "string" &&
    typeof value.version === "string" &&
    (value.environment === "development" || value.environment === "production") &&
    typeof value.timestamp === "string" &&
    typeof value.llm_configured === "boolean"
  );
}

function isDatasetResponse(value: unknown): value is DatasetResponse {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.filename === "string" &&
    typeof value.n_rows === "number" &&
    Array.isArray(value.points) &&
    Array.isArray(value.warnings)
  );
}

function isRunResponse(value: unknown): value is RunResponse {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.dataset_id === "string" &&
    typeof value.status === "string" &&
    typeof value.horizon === "number" &&
    Array.isArray(value.nodes_visited)
  );
}

function isEvaluationResponse(value: unknown): value is EvaluationResponse {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    (value.system === "baseline" || value.system === "agent") &&
    typeof value.status === "string"
  );
}

function isEvaluationCompareResponse(value: unknown): value is EvaluationCompareResponse {
  return (
    isRecord(value) &&
    typeof value.comparison_id === "string" &&
    typeof value.case_lists_identical === "boolean" &&
    isRecord(value.aggregate)
  );
}

function isEvaluationDashboardResponse(value: unknown): value is EvaluationDashboardResponse {
  return (
    isRecord(value) &&
    typeof value.artifact_path === "string" &&
    isRecord(value.comparison) &&
    Array.isArray(value.comparison.per_case) &&
    Array.isArray(value.catalog)
  );
}

function isChangelogDocument(value: unknown): value is ChangelogDocument {
  return isRecord(value) && typeof value.path === "string" && typeof value.markdown === "string";
}

export async function getHealth(): Promise<HealthResponse> {
  return requestJson("/health", { method: "GET" }, isHealthResponse);
}

export async function uploadDataset(file: File): Promise<DatasetResponse> {
  const body = new FormData();
  body.append("file", file, file.name);
  return requestJson("/datasets", { method: "POST", body }, isDatasetResponse);
}

export async function getDataset(id: string): Promise<DatasetResponse> {
  const datasetId = requireResourceId(id);
  return requestJson(
    `/datasets/${encodeURIComponent(datasetId)}`,
    { method: "GET" },
    isDatasetResponse,
  );
}

export async function createRun(input: {
  dataset_id: string;
  horizon: number;
  frequency?: string;
  coverage: number;
  seed?: number;
  seasonal_period?: number;
}): Promise<RunResponse> {
  const datasetId = requireResourceId(input.dataset_id);
  const payload: Record<string, string | number> = {
    dataset_id: datasetId,
    horizon: input.horizon,
    coverage: input.coverage,
  };
  if (input.frequency) {
    payload.frequency = input.frequency;
  }
  if (input.seed !== undefined) {
    payload.seed = input.seed;
  }
  if (input.seasonal_period !== undefined) {
    payload.seasonal_period = input.seasonal_period;
  }
  return requestJson(
    "/runs",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    isRunResponse,
  );
}

export async function getRun(id: string): Promise<RunResponse> {
  const runId = requireResourceId(id);
  return requestJson(`/runs/${encodeURIComponent(runId)}`, { method: "GET" }, isRunResponse);
}

export async function decideRunCheckpoint(
  id: string,
  action: "accept" | "reject" | "review",
  note?: string,
): Promise<RunResponse> {
  const runId = requireResourceId(id);
  const payload: Record<string, string> = { action };
  if (note) {
    payload.note = note;
  }
  return requestJson(
    `/runs/${encodeURIComponent(runId)}/checkpoint`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    isRunResponse,
  );
}

export async function startEvaluation(system: "baseline" | "agent"): Promise<EvaluationResponse> {
  return requestJson(
    "/evaluations/run",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system }),
    },
    isEvaluationResponse,
  );
}

export async function getEvaluation(id: string): Promise<EvaluationResponse> {
  const evaluationId = requireResourceId(id);
  return requestJson(
    `/evaluations/${encodeURIComponent(evaluationId)}`,
    { method: "GET" },
    isEvaluationResponse,
  );
}

export async function compareEvaluations(
  baselineId: string,
  agentId: string,
): Promise<EvaluationCompareResponse> {
  const baseline = requireResourceId(baselineId);
  const agent = requireResourceId(agentId);
  return requestJson(
    "/evaluations/compare",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ baseline_id: baseline, agent_id: agent }),
    },
    isEvaluationCompareResponse,
  );
}

export async function getEvaluationDashboard(): Promise<EvaluationDashboardResponse> {
  return requestJson("/evaluations/dashboard", { method: "GET" }, isEvaluationDashboardResponse);
}

export async function getEvaluationChangelog(): Promise<ChangelogDocument> {
  return requestJson("/evaluations/changelog", { method: "GET" }, isChangelogDocument);
}
