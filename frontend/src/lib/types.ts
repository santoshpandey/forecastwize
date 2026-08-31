export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: "development" | "production";
  timestamp: string;
  llm_configured: boolean;
};

export type PublicError = {
  error_code: string;
  message: string;
  request_id: string | null;
};

export type ValidationIssue = {
  severity: "error" | "warning";
  code: string;
  message: string;
  series_id: string | null;
  timestamp: string | null;
  row_number: number | null;
};

export type SeriesPoint = {
  timestamp: string;
  value: number | null;
};

export type MissingPeriod = {
  start: string;
  end: string;
  n_steps: number;
  series_id: string | null;
};

export type DiagnosticSummary = {
  name: string;
  detected: boolean;
  confidence: string;
  strength: string;
  summary: string;
  n_flagged: number;
  limitations: string[];
};

export type DatasetResponse = {
  id: string;
  filename: string;
  created_at: string;
  n_rows: number;
  n_missing_values: number;
  frequency: string | null;
  frequency_confidence: "high" | "medium" | "low" | null;
  timestamp_start: string | null;
  timestamp_end: string | null;
  has_series_id: boolean;
  has_context: boolean;
  has_event: boolean;
  extra_columns: string[];
  warnings: ValidationIssue[];
  points: SeriesPoint[];
  missing_periods: MissingPeriod[];
  anomalies: DiagnosticSummary | null;
  seasonality: DiagnosticSummary | null;
  structural_break: DiagnosticSummary | null;
};

export type ForecastResult = {
  timestamps: string[];
  yhat: number[];
  lower: number[];
  upper: number[];
  model: string;
  training_range: { start: string; end: string };
  forecast_horizon: number;
  frequency: string;
  configuration: Record<string, string | number | boolean | null>;
  random_seed: number | null;
  generated_at: string;
  interval_coverage_nominal: number;
};

export type RunStatus =
  | "queued"
  | "running"
  | "retrying"
  | "completed"
  | "failed"
  | "waiting_for_approval";

export type HumanCheckpoint = {
  required: boolean;
  status: "not_required" | "waiting_for_approval" | "approved" | "rejected";
  reason: string;
  evidence_ids: string[];
  triggers: string[];
  proposed_transforms: {
    name: string;
    policy: string;
    reason: string;
    applied: boolean;
  }[];
  source_data_unmodified: boolean;
  decision_note: string | null;
  checkpoint_id?: string | null;
};

export type CandidateRow = {
  model_id: string;
  official_wis: number | null;
  wis_completed_only: number | null;
  n_folds_planned: number;
  n_folds_completed: number;
  n_folds_failed: number;
  rank: number | null;
  error_message: string | null;
  eligible?: boolean | null;
  vetoed?: boolean | null;
  veto_reason?: string | null;
  selectable?: boolean | null;
  recent_vs_earlier_ratio?: number | null;
};

export type VerificationCheck = {
  check_id: string;
  name: string;
  result: string;
  severity: string;
  explanation: string;
  applicable: boolean;
};

export type Claim = {
  kind: string;
  topic: string;
  statement: string;
  evidence_ids: string[];
  uncertainty: string;
};

export type RunResponse = {
  id: string;
  dataset_id: string;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  horizon: number;
  frequency: string;
  coverage: number;
  seed: number | null;
  seasonal_period: number | null;
  retry_number: number;
  max_retries: number;
  selected_strategy_id: string | null;
  verification_overall: string | null;
  accepted: boolean;
  review_required: boolean;
  nodes_visited: string[];
  human_checkpoint: HumanCheckpoint | null;
  forecast: ForecastResult | null;
  error: { error_code: string; message: string } | null;
  trajectory_available: boolean;
  candidates: CandidateRow[];
  verification_checks: VerificationCheck[];
  risks: Claim[];
  evidence_ids: string[];
  overall_uncertainty: string | null;
  analysis_markdown: string | null;
};

export type EvaluationStatus = "queued" | "running" | "completed" | "failed";

export type EvaluationAggregate = {
  n_cases: number;
  n_cases_completed: number;
  n_cases_failed: number;
  wis: number | null;
  smape: number | null;
  wmape: number | null;
  mase: number | null;
  interval_coverage: number | null;
  interval_width: number | null;
  human_intervention_count: number;
  wis_completed_only: number | null;
};

export type EvaluationResponse = {
  id: string;
  status: EvaluationStatus;
  system: "baseline" | "agent";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  evaluation_run_id: string | null;
  case_list: string[] | null;
  aggregate: EvaluationAggregate | null;
  errors: { case_id: string; error_type: string | null; error_message: string | null }[];
  error: { error_code: string; message: string } | null;
};

export type MetricComparison = {
  name: string;
  direction: string;
  baseline: number | null;
  agent: number | null;
  delta_agent_minus_baseline: number | null;
  relative_improvement: number | null;
};

export type EvaluationCompareResponse = {
  comparison_id: string;
  baseline_evaluation_run_id: string;
  agent_evaluation_run_id: string;
  case_list: string[];
  case_lists_identical: boolean;
  primary_metric: string;
  aggregate: Record<string, MetricComparison>;
  n_cases_failed: MetricComparison;
  human_intervention_count: MetricComparison;
  notes: string[];
  errors: Record<string, { case_id: string; error_type: string | null; error_message: string | null }[]>;
};

export type CaseComparison = {
  case_id: string;
  baseline_status: string;
  agent_status: string;
  baseline_error_type: string | null;
  agent_error_type: string | null;
  baseline_error_message: string | null;
  agent_error_message: string | null;
  review_required: boolean;
  retry_number: number;
  metrics: Record<string, MetricComparison>;
  runtime_seconds: MetricComparison;
};

export type CatalogCase = {
  case_id: string;
  name: string;
  expected_challenge: string;
  description: string;
  challenging: boolean;
};

export type EvaluationDashboardResponse = {
  artifact_path: string;
  baseline_artifact_path: string | null;
  agent_artifact_path: string | null;
  changelog_path: string;
  comparison: {
    comparison_id: string;
    timestamp: string;
    git_commit: string | null;
    baseline_evaluation_run_id: string;
    agent_evaluation_run_id: string;
    case_list: string[];
    case_lists_identical: boolean;
    primary_metric: string;
    per_case: CaseComparison[];
    aggregate: {
      n_cases: number;
      metrics: Record<string, MetricComparison>;
      n_cases_failed: MetricComparison;
      human_intervention_count: MetricComparison;
      wall_seconds: MetricComparison;
      cases_seconds: MetricComparison;
    };
    errors: Record<string, { case_id: string; error_type: string | null; error_message: string | null }[]>;
    notes: string[];
  };
  catalog: CatalogCase[];
};

export type ChangelogDocument = {
  path: string;
  markdown: string;
};

export const PIPELINE_STEPS = [
  { id: "data", label: "Data", nodes: ["PROFILE"] },
  { id: "detective", label: "Data Detective", nodes: ["DIAGNOSE"] },
  { id: "context", label: "Context Analysis", nodes: ["CONTEXT"] },
  { id: "strategy", label: "Forecast Strategy", nodes: ["STRATEGY"] },
  {
    id: "backtest",
    label: "Backtest · robustness · model selection",
    nodes: ["BACKTEST"],
  },
  { id: "forecast", label: "Forecast", nodes: ["FORECAST"] },
  { id: "verify", label: "Verification", nodes: ["VERIFY"] },
  { id: "checkpoint", label: "Human checkpoint when required", nodes: ["RETRY_OR_ACCEPT"] },
  { id: "analysis", label: "Final analysis", nodes: ["ANALYZE", "FINALIZE"] },
] as const;
