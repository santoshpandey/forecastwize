"use client";

import { useEffect, useMemo, useState, Fragment } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { ForecastChart } from "@/components/ForecastChart";
import { HumanCheckpointPanel } from "@/components/HumanCheckpointPanel";
import { WorkspaceJourneyNav } from "@/components/WorkspaceJourneyNav";
import { ApiError, getDataset, getRun } from "@/lib/api";
import {
  formatCoveragePercent,
  formatDisplayDate,
  formatForecastNumber,
  formatFrequencyLabel,
  formatTimestamp,
} from "@/lib/format";
import { asId } from "@/lib/route";
import {
  CHECKPOINT_TRIGGER_LABELS,
  chartInterpretation,
  collectEvidenceIds,
  confidenceLabel,
  decisionReadiness,
  forecastDirection,
  humanReviewLabel,
  lastHistoricalTimestamp,
  uncertaintyLabel,
  verificationBadgeKind,
} from "@/lib/runDisplay";
import { setStoredDatasetId, setStoredRunId } from "@/lib/session";
import type { DatasetResponse, RunResponse } from "@/lib/types";

export default function ForecastResultPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<RunResponse | null>(null);
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const [techOpen, setTechOpen] = useState(false);

  useEffect(() => {
    const id = asId(params.id);
    if (!id) {
      return;
    }
    let cancelled = false;
    void getRun(id)
      .then(async (value) => {
        if (cancelled) {
          return;
        }
        setRun(value);
        setStoredRunId(value.id);
        const ds = await getDataset(value.dataset_id);
        if (cancelled) {
          return;
        }
        setDataset(ds);
        setStoredDatasetId(ds.id);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Could not load the forecast.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const forecast = run?.forecast ?? null;
  const verify = run?.verification_overall ?? null;
  const evidenceIds = run ? collectEvidenceIds(run) : [];
  const history = dataset?.points ?? [];
  const lastHist = lastHistoricalTimestamp(history);
  const forecastStart = forecast?.timestamps[0] ?? null;
  const forecastEnd = forecast?.timestamps.at(-1) ?? null;
  const modelName = run?.selected_strategy_id ?? forecast?.model ?? "Not available";
  const horizon = forecast?.forecast_horizon ?? run?.horizon ?? null;
  const frequency = formatFrequencyLabel(forecast?.frequency ?? run?.frequency);
  const interpretation = forecast && dataset ? chartInterpretation(history, forecast) : null;
  const direction = forecast ? forecastDirection(forecast.yhat) : "Mixed";
  const readiness = run ? decisionReadiness(run) : null;
  const warnChecks =
    run?.verification_checks?.filter((check) => check.result === "WARN" || check.result === "FAIL") ??
    [];
  const tableRows = forecast?.timestamps ?? [];
  const visibleRows = showAllRows || tableRows.length <= 14 ? tableRows : tableRows.slice(0, 14);
  const configEntries = useMemo(() => {
    if (!forecast) {
      return [];
    }
    return Object.entries(forecast.configuration);
  }, [forecast]);

  return (
    <AppShell current="workspace">
      <WorkspaceJourneyNav
        current="result"
        datasetId={dataset?.id ?? run?.dataset_id ?? null}
        runId={run?.id ?? null}
      />
      <h1 className="page-title">Forecast result</h1>
      <p className="lede">
        Historical values, point forecast, and intervals are taken from the API. This page does not
        recalculate WIS or invent missing fields.
      </p>
      {!run && !error ? <Banner kind="loading">Loading forecast…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {run?.status === "failed" && run.error ? (
        <Banner kind="error">
          {run.error.error_code}: {run.error.message}
        </Banner>
      ) : null}

      {run ? (
        <section className="card forecast-summary" aria-labelledby="forecast-summary-heading">
          <p className="eyebrow">Forecast summary</p>
          <h2 id="forecast-summary-heading" className="summary-title">
            {modelName.toUpperCase()} · {frequency} ·{" "}
            {horizon !== null ? `${horizon}-day horizon` : "Horizon not available"}
          </h2>
          <div className="summary-badges">
            <StatusBadge label="Status" value={verify ?? "Not available"} kind={verificationBadgeKind(verify)} />
            <StatusBadge label="Human review" value={humanReviewLabel(run)} kind="muted" />
            <StatusBadge label="Confidence" value={confidenceLabel(run)} kind="muted" />
            <StatusBadge label="Uncertainty" value={uncertaintyLabel(run)} kind="muted" />
          </div>
          <dl className="dl compact summary-meta">
            <dt>Last historical date</dt>
            <dd>{formatDisplayDate(lastHist)}</dd>
            <dt>Forecast start</dt>
            <dd>{formatDisplayDate(forecastStart)}</dd>
            <dt>Forecast end</dt>
            <dd>{formatDisplayDate(forecastEnd)}</dd>
          </dl>
        </section>
      ) : null}

      {dataset && forecast ? (
        <section className="card">
          <h2>
            Historical performance &amp; {horizon !== null ? `${horizon}-day` : ""} forecast
          </h2>
          <p className="muted">Historical values, point forecast, and prediction interval</p>
          <ForecastChart history={history} forecast={forecast} />
          {interpretation ? <p className="chart-note">{interpretation}</p> : null}
        </section>
      ) : null}
      {run && !forecast && run.status !== "failed" ? (
        <Banner kind="warning">No forecast artifact is attached to this run yet.</Banner>
      ) : null}

      {forecast ? (
        <section className="kpi-grid" aria-label="Key forecast insights">
          <article className="card">
            <h3>Forecast direction</h3>
            <p className="kpi-value">
              {direction === "Increasing" ? "↑ Increasing" : direction === "Decreasing" ? "↓ Decreasing" : "Direction: Mixed"}
            </p>
          </article>
          <article className="card">
            <h3>Forecast horizon</h3>
            <p className="kpi-value metric">
              {horizon !== null ? `${horizon} ${horizon === 1 ? "period" : "periods"}` : "Not available"}
            </p>
          </article>
          <article className="card">
            <h3>Confidence</h3>
            <p className="kpi-value">{run ? confidenceLabel(run) : "Not available"}</p>
          </article>
          <article className="card">
            <h3>Uncertainty</h3>
            <p className="kpi-value">{run ? uncertaintyLabel(run) : "Not available"}</p>
          </article>
        </section>
      ) : null}

      {run ? (
        <section className="card" aria-labelledby="governance-heading">
          <h2 id="governance-heading">Verification &amp; governance</h2>
          <dl className="dl compact">
            <dt>Verification status</dt>
            <dd>
              <StatusBadge value={verify ?? "Not returned"} kind={verificationBadgeKind(verify)} />
            </dd>
            <dt>Human checkpoint</dt>
            <dd>{humanReviewLabel(run)}</dd>
            <dt>Source data modified</dt>
            <dd>
              {run.human_checkpoint
                ? run.human_checkpoint.source_data_unmodified
                  ? "No"
                  : "Yes"
                : "Not available"}
            </dd>
          </dl>
          {verify === "WARN" ? (
            <Banner kind="warning">
              WARN means the backend verifier challenged the forecast and found issues that did not
              fail the run. The original claim was not quiet-accepted.
            </Banner>
          ) : null}
          {verify === "FAIL" ? (
            <Banner kind="error">
              FAIL means the backend verifier rejected the result. The original claim was not
              quiet-accepted.
            </Banner>
          ) : null}
          {verify === "PASS" ? (
            <Banner kind="ok">PASS means the deterministic checks did not fail. It is not a guarantee.</Banner>
          ) : null}
          {run.human_checkpoint?.triggers.length ? (
            <ul className="warning-list">
              {run.human_checkpoint.triggers.map((item) => (
                <li key={item}>{CHECKPOINT_TRIGGER_LABELS[item] ?? item}</li>
              ))}
            </ul>
          ) : null}
          {warnChecks.length > 0 ? (
            <ul className="warning-list">
              {warnChecks.map((check) => (
                <li key={check.check_id}>
                  {check.result}: {check.name}. {check.explanation}
                </li>
              ))}
            </ul>
          ) : null}
          <HumanCheckpointPanel run={run} onUpdated={setRun} />
          <div className="actions">
            <Link className="button" href={`/runs/${run.id}/verification`}>
              Open verification details
            </Link>
          </div>
        </section>
      ) : null}

      {forecast ? (
        <section className="card">
          <h2>Model configuration</h2>
          <dl className="dl config-grid">
            <dt>Model</dt>
            <dd>{modelName}</dd>
            <dt>Frequency</dt>
            <dd>{frequency}</dd>
            <dt>Forecast horizon</dt>
            <dd className="metric">{horizon !== null ? `${horizon} periods` : "Not available"}</dd>
            <dt>Training range</dt>
            <dd>
              {formatDisplayDate(forecast.training_range.start)} →{" "}
              {formatDisplayDate(forecast.training_range.end)}
            </dd>
            <dt>Prediction coverage</dt>
            <dd className="metric">{formatCoveragePercent(forecast.interval_coverage_nominal)}</dd>
            <dt>Seed</dt>
            <dd className="metric">{forecast.random_seed ?? "None"}</dd>
            <dt>Generated</dt>
            <dd>{formatDisplayDate(forecast.generated_at)}</dd>
          </dl>
          <button
            type="button"
            className="linkish"
            onClick={() => setTechOpen((open) => !open)}
            aria-expanded={techOpen}
          >
            {techOpen ? "Hide technical details" : "Technical details"}
          </button>
          {techOpen ? (
            <dl className="dl compact">
              <dt>Run ID</dt>
              <dd className="metric">{run?.id ?? "Not available"}</dd>
              <dt>Dataset ID</dt>
              <dd className="metric">{run?.dataset_id ?? "Not available"}</dd>
              <dt>Generated (ISO)</dt>
              <dd>{formatTimestamp(forecast.generated_at)}</dd>
              {configEntries.map(([key, value]) => (
                <Fragment key={key}>
                  <dt>{key}</dt>
                  <dd className="metric">{value === null ? "None" : String(value)}</dd>
                </Fragment>
              ))}
            </dl>
          ) : null}
        </section>
      ) : null}

      {forecast ? (
        <section className="card">
          <h2>Forecast details</h2>
          <p className="muted">Point estimates and prediction intervals for each forecast period.</p>
          <div className="table-wrap table-sticky">
            <table className="table-forecast">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Forecast</th>
                  <th>Lower bound</th>
                  <th>Upper bound</th>
                  <th>Interval width</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((stamp, index) => {
                  const lower = forecast.lower[index] ?? null;
                  const upper = forecast.upper[index] ?? null;
                  const width =
                    lower !== null &&
                    upper !== null &&
                    Number.isFinite(lower) &&
                    Number.isFinite(upper)
                      ? upper - lower
                      : null;
                  return (
                    <tr key={stamp}>
                      <td>{formatDisplayDate(stamp)}</td>
                      <td className="metric col-forecast">{formatForecastNumber(forecast.yhat[index] ?? null)}</td>
                      <td className="metric col-bound">{formatForecastNumber(lower)}</td>
                      <td className="metric col-bound">{formatForecastNumber(upper)}</td>
                      <td className="metric col-bound">{formatForecastNumber(width)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {tableRows.length > 14 ? (
            <div className="actions">
              <button type="button" className="secondary" onClick={() => setShowAllRows((value) => !value)}>
                {showAllRows ? "Show fewer rows" : `Show all ${tableRows.length} periods`}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {run ? (
        <section className="card">
          <h2>Model comparison</h2>
          {(run.candidates ?? []).length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>WIS</th>
                    <th>Rank</th>
                    <th>Selected</th>
                  </tr>
                </thead>
                <tbody>
                  {(run.candidates ?? []).map((row) => {
                    const selected = run.selected_strategy_id === row.model_id;
                    return (
                      <tr key={row.model_id} className={selected ? "row-selected" : undefined}>
                        <td>{row.model_id}</td>
                        <td className="metric">{formatForecastNumber(row.official_wis)}</td>
                        <td className="metric">{row.rank ?? "—"}</td>
                        <td>{selected ? "selected" : "not selected"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <>
              <p>No official backtest candidates are available for this run.</p>
              <p className="muted">
                Model selection cannot be independently compared against other candidates for this
                run. Open the comparison page if a later response attaches rows.
              </p>
            </>
          )}
          <div className="actions">
            <Link className="button secondary" href={`/runs/${run.id}/comparison`}>
              Open model comparison
            </Link>
          </div>
        </section>
      ) : null}

      {run ? (
        <section className="card">
          <h2>Risks &amp; limitations</h2>
          {(run.risks ?? []).length > 0 ? (
            <ul className="risk-cards">
              {(run.risks ?? []).map((risk) => (
                <li key={risk.statement}>
                  <p>{risk.statement}</p>
                  <p className="muted">
                    {risk.uncertainty}
                    {risk.evidence_ids.length > 0 ? ` · ${risk.evidence_ids.join(", ")}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <>
              <p>No explicit risk claims were returned by the forecasting API.</p>
              <p className="muted">
                Review verification warnings and prediction intervals before making decisions. This
                note is guidance only; it is not a backend-identified risk.
              </p>
            </>
          )}
        </section>
      ) : null}

      {run ? (
        <section className="card">
          <h2>Evidence</h2>
          {evidenceIds.length > 0 ? (
            <>
              <p>
                <span className="metric">{evidenceIds.length}</span> evidence item
                {evidenceIds.length === 1 ? "" : "s"} attached
              </p>
              <ul className="evidence-chips">
                {evidenceIds.map((id) => (
                  <li key={id}>
                    <span className="chip">{id}</span>
                  </li>
                ))}
              </ul>
              <p className="muted">
                IDs are copied from the run response (run evidence, checkpoint evidence, and risk
                citations). There is no evidence-detail route.
              </p>
            </>
          ) : (
            <p className="muted">No evidence attached to this run.</p>
          )}
        </section>
      ) : null}

      {run && readiness ? (
        <section className="card decision-card" aria-labelledby="readiness-heading">
          <h2 id="readiness-heading">Decision readiness</h2>
          <p className="kpi-value">{readiness.state}</p>
          <p className="muted">This is a governance summary. It is not an automated business decision.</p>
          {readiness.reasons.length > 0 ? (
            <ul>
              {readiness.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          <div className="actions">
            <Link className="button" href={`/runs/${run.id}/verification`}>
              Review verification details
            </Link>
            <Link className="button secondary" href={`/runs/${run.id}/comparison`}>
              View model comparison
            </Link>
          </div>
        </section>
      ) : null}

      {run?.analysis_markdown ? (
        <section className="card">
          <h2>Final analysis</h2>
          <p className="prose">{run.analysis_markdown}</p>
        </section>
      ) : null}
    </AppShell>
  );
}

function StatusBadge({
  label,
  value,
  kind,
}: {
  label?: string;
  value: string;
  kind: "ok" | "warning" | "error" | "muted";
}) {
  return (
    <span className={`status-badge status-badge-${kind}`}>
      {label ? `${label}: ` : null}
      {value}
    </span>
  );
}
