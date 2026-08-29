"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/Banner";
import { HealthStatus } from "@/components/HealthStatus";
import { JourneyNav } from "@/components/JourneyNav";
import { getStoredDatasetId, getStoredRunId } from "@/lib/session";

export default function DashboardPage() {
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setDatasetId(getStoredDatasetId());
    setRunId(getStoredRunId());
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AppShell current="dashboard">
      <JourneyNav dataset={null} run={null} current="dashboard" />
      <h1 className="page-title">Dashboard</h1>
      <p className="lede">
        ForecastWize is a decision-support workspace. Numerical forecasts and scores come from
        the backend. This UI displays those results; it does not calculate WIS or other official
        metrics in the browser.
      </p>
      <HealthStatus />
      <div className="grid grid-2">
        <div className="card">
          <h2>Start an analysis</h2>
          <p className="muted">Upload a CSV with timestamp and value columns, then review diagnostics.</p>
          <div className="actions">
            <a className="button" href="/upload">
              Upload dataset
            </a>
          </div>
        </div>
        <div className="card">
          <h2>Resume</h2>
          {datasetId ? (
            <div className="actions">
              <a className="button secondary" href={`/datasets/${datasetId}`}>
                Open last dataset
              </a>
              {runId ? (
                <a className="button secondary" href={`/runs/${runId}`}>
                  Open last agent run
                </a>
              ) : null}
            </div>
          ) : (
            <EmptyState
              embedded
              title="No dataset in this session"
              body="Upload a series to begin. Session links are stored in this browser tab only."
            />
          )}
        </div>
        <div className="card">
          <h2>Evaluation comparison</h2>
          <p className="muted">
            Official BASELINE vs ADVANCED comparison from evaluation JSON.
          </p>
          <div className="actions">
            <a className="button secondary" href="/evaluation">
              Open evaluation dashboard
            </a>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
