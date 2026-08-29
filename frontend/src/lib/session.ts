const DATASET_KEY = "forecastwize.datasetId";
const RUN_KEY = "forecastwize.runId";
const BASELINE_EVAL_KEY = "forecastwize.baselineEvalId";
const AGENT_EVAL_KEY = "forecastwize.agentEvalId";

function read(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.sessionStorage.getItem(key);
}

function write(key: string, value: string): void {
  window.sessionStorage.setItem(key, value);
}

export function getStoredDatasetId(): string | null {
  return read(DATASET_KEY);
}

export function setStoredDatasetId(id: string): void {
  write(DATASET_KEY, id);
}

export function getStoredRunId(): string | null {
  return read(RUN_KEY);
}

export function setStoredRunId(id: string): void {
  write(RUN_KEY, id);
}

export function getStoredBaselineEvalId(): string | null {
  return read(BASELINE_EVAL_KEY);
}

export function setStoredBaselineEvalId(id: string): void {
  write(BASELINE_EVAL_KEY, id);
}

export function getStoredAgentEvalId(): string | null {
  return read(AGENT_EVAL_KEY);
}

export function setStoredAgentEvalId(id: string): void {
  write(AGENT_EVAL_KEY, id);
}
