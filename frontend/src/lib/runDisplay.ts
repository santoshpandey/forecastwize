import type { ForecastResult, RunResponse, SeriesPoint } from "@/lib/types";

export const CHECKPOINT_TRIGGER_LABELS: Record<string, string> = {
  data_modification_proposed: "Data modification proposed",
  low_forecast_confidence: "Forecast confidence is low",
  verification_failed_repeatedly: "Verification failed repeatedly",
  material_uncertainty: "Material uncertainty remains",
};

export function collectEvidenceIds(run: RunResponse): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  function add(ids: string[] | undefined): void {
    for (const id of ids ?? []) {
      if (typeof id === "string" && id.length > 0 && !seen.has(id)) {
        seen.add(id);
        ordered.push(id);
      }
    }
  }
  add(run.evidence_ids);
  add(run.human_checkpoint?.evidence_ids);
  for (const risk of run.risks ?? []) {
    add(risk.evidence_ids);
  }
  return ordered;
}

export function lastHistoricalTimestamp(history: SeriesPoint[]): string | null {
  for (let i = history.length - 1; i >= 0; i -= 1) {
    const stamp = history[i]?.timestamp;
    if (stamp) {
      return stamp;
    }
  }
  return null;
}

export function forecastDirection(yhat: number[]): "Increasing" | "Decreasing" | "Mixed" {
  const nums = yhat.filter((value) => Number.isFinite(value));
  if (nums.length < 2) {
    return "Mixed";
  }
  const first = nums[0];
  const last = nums[nums.length - 1];
  if (first === undefined || last === undefined) {
    return "Mixed";
  }
  if (last > first) {
    return "Increasing";
  }
  if (last < first) {
    return "Decreasing";
  }
  return "Mixed";
}

export function chartInterpretation(
  history: SeriesPoint[],
  forecast: ForecastResult,
): string | null {
  const sentences: string[] = [];
  const direction = forecastDirection(forecast.yhat);
  const histNums = history
    .map((point) => point.value)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const histUp =
    histNums.length >= 2 && histNums[histNums.length - 1]! > histNums[0]!;
  const histDown =
    histNums.length >= 2 && histNums[histNums.length - 1]! < histNums[0]!;
  if (direction === "Increasing" && histUp) {
    sentences.push(
      "The backend point forecast ends higher than it starts, after a historical series that also ends above its start.",
    );
  } else if (direction === "Decreasing" && histDown) {
    sentences.push(
      "The backend point forecast ends lower than it starts, after a historical series that also ends below its start.",
    );
  } else if (direction === "Increasing") {
    sentences.push("The backend point forecast ends higher than it starts over the horizon.");
  } else if (direction === "Decreasing") {
    sentences.push("The backend point forecast ends lower than it starts over the horizon.");
  }
  if (forecast.lower.length > 0 && forecast.upper.length > 0) {
    sentences.push("The shaded band is the prediction interval returned by the API.");
  }
  if (sentences.length === 0) {
    return null;
  }
  return sentences.join(" ");
}

export function confidenceLabel(run: RunResponse): string {
  if (run.overall_uncertainty) {
    return titleCase(run.overall_uncertainty);
  }
  if (run.human_checkpoint?.triggers.includes("low_forecast_confidence")) {
    return "Low";
  }
  return "Not available";
}

export function uncertaintyLabel(run: RunResponse): string {
  if (run.human_checkpoint?.triggers.includes("material_uncertainty")) {
    return "Material";
  }
  if (run.overall_uncertainty) {
    return titleCase(run.overall_uncertainty);
  }
  return "Not available";
}

export function humanReviewLabel(run: RunResponse): string {
  const status = run.human_checkpoint?.status;
  if (status === "waiting_for_approval") {
    return "Waiting";
  }
  if (status === "approved") {
    return "Accepted";
  }
  if (status === "rejected") {
    return "Rejected";
  }
  if (status === "not_required") {
    return "Not required";
  }
  return "Not available";
}

export function verificationBadgeKind(
  overall: string | null | undefined,
): "ok" | "warning" | "error" | "muted" {
  if (overall === "PASS") {
    return "ok";
  }
  if (overall === "WARN") {
    return "warning";
  }
  if (overall === "FAIL") {
    return "error";
  }
  return "muted";
}

export type DecisionReadiness = {
  state: "REVIEW REQUIRED" | "CAUTION" | "READY" | "NOT AVAILABLE";
  reasons: string[];
};

export function decisionReadiness(run: RunResponse): DecisionReadiness {
  const reasons: string[] = [];
  const overall = run.verification_overall;
  const checkpoint = run.human_checkpoint;
  if (overall) {
    reasons.push(`Verification status: ${overall}`);
  }
  const confidence = confidenceLabel(run);
  if (confidence !== "Not available") {
    reasons.push(`Forecast confidence: ${confidence}`);
  }
  const uncertainty = uncertaintyLabel(run);
  if (uncertainty !== "Not available") {
    reasons.push(`Uncertainty: ${uncertainty}`);
  }
  reasons.push(`Human checkpoint: ${humanReviewLabel(run)}`);
  if (run.status === "waiting_for_approval" || checkpoint?.status === "waiting_for_approval") {
    return { state: "REVIEW REQUIRED", reasons };
  }
  if (overall === "FAIL") {
    return { state: "REVIEW REQUIRED", reasons };
  }
  if (overall === "WARN") {
    return { state: "CAUTION", reasons };
  }
  if (overall === "PASS") {
    return { state: "READY", reasons };
  }
  return { state: "NOT AVAILABLE", reasons };
}

function titleCase(value: string): string {
  if (!value) {
    return value;
  }
  return value.slice(0, 1).toUpperCase() + value.slice(1).toLowerCase();
}
