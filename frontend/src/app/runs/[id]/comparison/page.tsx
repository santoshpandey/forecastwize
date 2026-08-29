"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { JourneyNav } from "@/components/JourneyNav";
import { ApiError, getDataset, getRun } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { asId } from "@/lib/route";
import { setStoredDatasetId, setStoredRunId } from "@/lib/session";
import type { DatasetResponse, RunResponse } from "@/lib/types";

export default function ModelComparisonPage() {
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
        if (!cancelled) {
          setDataset(ds);
          setStoredDatasetId(ds.id);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Could not load comparison.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  return (
    <AppShell current="workspace">
      <JourneyNav dataset={dataset} run={run} current="comparison" />
      <h1 className="page-title">Model comparison</h1>
      <p className="lede">
        Official backtest WIS and ranks are copied from the strategist tool result. Lower WIS is
        better. Completed-only WIS is labeled and is not the selection rule.
      </p>
      {!run && !error ? <Banner kind="loading">Loading comparison…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {run?.selected_strategy_id ? (
        <Banner kind="ok">Selected strategy (from API): {run.selected_strategy_id}</Banner>
      ) : (
        run && <Banner kind="warning">No selected strategy_id was returned.</Banner>
      )}
      {run && run.candidates.length === 0 ? (
        <Banner kind="warning">No candidate backtest rows were attached to this run.</Banner>
      ) : null}
      {run && run.candidates.length > 0 ? (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Model</th>
                  <th>Official WIS</th>
                  <th>WIS (completed folds only)</th>
                  <th>Folds failed</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {run.candidates.map((row) => (
                  <tr key={row.model_id}>
                    <td className="metric">{row.rank ?? "—"}</td>
                    <td>{row.model_id}</td>
                    <td className="metric">{formatNumber(row.official_wis)}</td>
                    <td className="metric">{formatNumber(row.wis_completed_only)}</td>
                    <td className="metric">{formatNumber(row.n_folds_failed)}</td>
                    <td>{row.error_message ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
