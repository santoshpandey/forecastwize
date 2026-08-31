"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { ForecastChart } from "@/components/ForecastChart";
import { HumanCheckpointPanel } from "@/components/HumanCheckpointPanel";
import { WorkspaceJourneyNav } from "@/components/WorkspaceJourneyNav";
import { ApiError, getDataset, getRun } from "@/lib/api";
import { formatNumber, formatTimestamp } from "@/lib/format";
import { asId } from "@/lib/route";
import { setStoredDatasetId, setStoredRunId } from "@/lib/session";
import type { DatasetResponse, RunResponse } from "@/lib/types";

export default function ForecastResultPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<RunResponse | null>(null);
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  const verify = run?.verification_overall;

  return (
    <AppShell current="workspace">
      <WorkspaceJourneyNav
        current="result"
        datasetId={dataset?.id ?? run?.dataset_id ?? null}
        runId={run?.id ?? null}
      />
      <h1 className="page-title">Forecast result</h1>
      <p className="lede">
        Historical points and forecast arrays are taken from the API. Interval quality is not
        scored in the browser.
      </p>
      {!run && !error ? <Banner kind="loading">Loading forecast…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {run?.status === "failed" && run.error ? (
        <Banner kind="error">
          {run.error.error_code}: {run.error.message}
        </Banner>
      ) : null}
      {verify === "WARN" ? (
        <Banner kind="warning">Verification overall is WARN (from the backend verifier).</Banner>
      ) : null}
      {verify === "FAIL" ? (
        <Banner kind="error">Verification overall is FAIL. The original claim was not quiet-accepted.</Banner>
      ) : null}
      {run?.human_checkpoint ? <HumanCheckpointPanel run={run} onUpdated={setRun} /> : null}
      {dataset && forecast ? (
        <div className="card">
          <h2>Series and forecast</h2>
          <ForecastChart history={dataset.points} forecast={forecast} />
        </div>
      ) : null}
      {run && !forecast && run.status !== "failed" ? (
        <Banner kind="warning">No forecast artifact is attached to this run yet.</Banner>
      ) : null}
      {forecast ? (
        <div className="card">
          <h2>Selected model</h2>
          <dl className="dl">
            <dt>Strategy / model</dt>
            <dd>{run?.selected_strategy_id ?? forecast.model}</dd>
            <dt>Frequency</dt>
            <dd>{forecast.frequency}</dd>
            <dt>Verification</dt>
            <dd>{run?.verification_overall ?? "Not returned"}</dd>
            <dt>Horizon</dt>
            <dd className="metric">{formatNumber(forecast.forecast_horizon)}</dd>
            <dt>Training range</dt>
            <dd>
              {formatTimestamp(forecast.training_range.start)} →{" "}
              {formatTimestamp(forecast.training_range.end)}
            </dd>
            <dt>Nominal coverage</dt>
            <dd className="metric">{formatNumber(forecast.interval_coverage_nominal)}</dd>
            <dt>Seed</dt>
            <dd className="metric">{forecast.random_seed ?? "None"}</dd>
            <dt>Generated</dt>
            <dd>{formatTimestamp(forecast.generated_at)}</dd>
          </dl>
        </div>
      ) : null}
      {forecast ? (
        <div className="card">
          <h2>Point forecast and interval</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>yhat</th>
                  <th>Lower</th>
                  <th>Upper</th>
                </tr>
              </thead>
              <tbody>
                {forecast.timestamps.map((stamp, index) => (
                  <tr key={stamp}>
                    <td>{formatTimestamp(stamp)}</td>
                    <td className="metric">{formatNumber(forecast.yhat[index] ?? null)}</td>
                    <td className="metric">{formatNumber(forecast.lower[index] ?? null)}</td>
                    <td className="metric">{formatNumber(forecast.upper[index] ?? null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {run ? (
        <div className="grid grid-2">
          <div className="card">
            <h2>Verification result</h2>
            <p>{run.verification_overall ?? "Not returned"}</p>
            <Link href={`/runs/${run.id}/verification`}>Open verification detail</Link>
          </div>
          <div className="card">
            <h2>Model comparison</h2>
            <p className="muted">
              {run.candidates.length} candidate row(s) from official backtest WIS.
            </p>
            <Link href={`/runs/${run.id}/comparison`}>Open model comparison</Link>
          </div>
        </div>
      ) : null}
      {run && run.risks.length > 0 ? (
        <div className="card">
          <h2>Risks</h2>
          <ul>
            {run.risks.map((risk) => (
              <li key={risk.statement}>
                {risk.statement}{" "}
                <span className="muted">
                  ({risk.uncertainty}; evidence {risk.evidence_ids.join(", ") || "none"})
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        run && (
          <div className="card">
            <h2>Risks</h2>
            <p className="muted">The API returned no risk claims for this run.</p>
          </div>
        )
      )}
      {run && run.evidence_ids.length > 0 ? (
        <div className="card">
          <h2>Evidence</h2>
          <p className="metric">{run.evidence_ids.join(", ")}</p>
        </div>
      ) : (
        run && (
          <div className="card">
            <h2>Evidence</h2>
            <p className="muted">No evidence IDs were attached to this run.</p>
          </div>
        )
      )}
      {run?.analysis_markdown ? (
        <div className="card">
          <h2>Final analysis</h2>
          <p className="prose">{run.analysis_markdown}</p>
        </div>
      ) : null}
    </AppShell>
  );
}
