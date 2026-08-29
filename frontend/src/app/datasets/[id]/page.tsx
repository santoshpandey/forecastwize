"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { JourneyNav } from "@/components/JourneyNav";
import { ApiError, getDataset } from "@/lib/api";
import { formatNumber, formatTimestamp } from "@/lib/format";
import { asId } from "@/lib/route";
import { setStoredDatasetId } from "@/lib/session";
import type { DatasetResponse, DiagnosticSummary } from "@/lib/types";

function DiagnosticCard({
  title,
  item,
  detectedMeansWarning,
}: {
  title: string;
  item: DiagnosticSummary | null;
  detectedMeansWarning: boolean;
}) {
  if (!item) {
    return (
      <div className="card">
        <h2>{title}</h2>
        <p className="muted">The API did not return this diagnostic.</p>
      </div>
    );
  }
  const kind = item.detected && detectedMeansWarning ? "warning" : "ok";
  return (
    <div className="card">
      <h2>{title}</h2>
      <Banner kind={kind}>
        {item.detected ? "Flagged by the backend diagnostic." : "Not flagged."} Confidence:{" "}
        {item.confidence}. Strength: {item.strength}.
      </Banner>
      <p>{item.summary}</p>
      <p className="muted metric">Flagged points (from API): {formatNumber(item.n_flagged)}</p>
      {item.limitations.length > 0 ? (
        <ul>
          {item.limitations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function DatasetPage() {
  const params = useParams<{ id: string }>();
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const id = asId(params.id);
    if (!id) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getDataset(id)
      .then((value) => {
        if (cancelled) {
          return;
        }
        setDataset(value);
        setStoredDatasetId(value.id);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Could not load dataset.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  return (
    <AppShell current="workspace">
      <JourneyNav dataset={dataset} run={null} current="diagnostics" />
      <h1 className="page-title">Dataset diagnostics</h1>
      <p className="lede">
        Counts, range, frequency, gaps, and screens below are returned by the API. This page does
        not invent seasonality or anomaly scores.
      </p>
      {loading ? <Banner kind="loading">Loading dataset…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {dataset ? (
        <>
          {dataset.warnings.length > 0 ? (
            <Banner kind="warning">
              {dataset.warnings.map((item) => item.message).join(" ")}
            </Banner>
          ) : null}
          <div className="card">
            <h2>{dataset.filename}</h2>
            <dl className="dl">
              <dt>Row count</dt>
              <dd className="metric">{formatNumber(dataset.n_rows)}</dd>
              <dt>Date range</dt>
              <dd>
                {formatTimestamp(dataset.timestamp_start)} → {formatTimestamp(dataset.timestamp_end)}
              </dd>
              <dt>Frequency</dt>
              <dd>
                {dataset.frequency ?? "Unresolved"}{" "}
                {dataset.frequency_confidence ? `(${dataset.frequency_confidence} confidence)` : ""}
              </dd>
              <dt>Missing values</dt>
              <dd className="metric">{formatNumber(dataset.n_missing_values)}</dd>
              <dt>Missing periods</dt>
              <dd className="metric">{formatNumber(dataset.missing_periods.length)}</dd>
            </dl>
          </div>
          <div className="card">
            <h2>Missing periods</h2>
            {dataset.missing_periods.length === 0 ? (
              <p className="muted">No inferred gap periods were returned.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Start</th>
                      <th>End</th>
                      <th>Steps</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dataset.missing_periods.map((period) => (
                      <tr key={`${period.start}-${period.end}`}>
                        <td>{formatTimestamp(period.start)}</td>
                        <td>{formatTimestamp(period.end)}</td>
                        <td className="metric">{formatNumber(period.n_steps)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="grid grid-3">
            <DiagnosticCard title="Anomalies" item={dataset.anomalies} detectedMeansWarning />
            <DiagnosticCard
              title="Seasonality"
              item={dataset.seasonality}
              detectedMeansWarning={false}
            />
            <DiagnosticCard
              title="Structural break"
              item={dataset.structural_break}
              detectedMeansWarning
            />
          </div>
          <div className="actions">
            <a className="button" href={`/datasets/${dataset.id}/configure`}>
              Configure forecast
            </a>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}
