"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Banner, EmptyState } from "@/components/Banner";
import { JourneyNav } from "@/components/JourneyNav";
import { ApiError, compareEvaluations, getEvaluation, startEvaluation } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import {
  getStoredAgentEvalId,
  getStoredBaselineEvalId,
  setStoredAgentEvalId,
  setStoredBaselineEvalId,
} from "@/lib/session";
import type { EvaluationCompareResponse, EvaluationResponse } from "@/lib/types";

function isActive(status: EvaluationResponse["status"]): boolean {
  return status === "queued" || status === "running";
}

async function pollUntilDone(id: string): Promise<EvaluationResponse> {
  for (;;) {
    const current = await getEvaluation(id);
    if (!isActive(current.status)) {
      return current;
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, 2000);
    });
  }
}

export default function EvaluationsPage() {
  const [baseline, setBaseline] = useState<EvaluationResponse | null>(null);
  const [agent, setAgent] = useState<EvaluationResponse | null>(null);
  const [comparison, setComparison] = useState<EvaluationCompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const baselineId = getStoredBaselineEvalId();
    const agentId = getStoredAgentEvalId();
    if (baselineId) {
      void getEvaluation(baselineId).then(setBaseline).catch(() => undefined);
    }
    if (agentId) {
      void getEvaluation(agentId).then(setAgent).catch(() => undefined);
    }
  }, []);

  async function runSystem(system: "baseline" | "agent") {
    setError(null);
    setBusy(system);
    try {
      const started = await startEvaluation(system);
      const done = await pollUntilDone(started.id);
      if (system === "baseline") {
        setBaseline(done);
        setStoredBaselineEvalId(done.id);
      } else {
        setAgent(done);
        setStoredAgentEvalId(done.id);
      }
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Evaluation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function runCompare() {
    if (!baseline || !agent) {
      setError("Run both baseline and agent evaluations first.");
      return;
    }
    setError(null);
    setBusy("compare");
    try {
      const result = await compareEvaluations(baseline.id, agent.id);
      setComparison(result);
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Comparison failed.");
    } finally {
      setBusy(null);
    }
  }

  const wis = comparison?.aggregate.wis;

  return (
    <AppShell current="evaluations">
      <JourneyNav dataset={null} run={null} current="evaluation" />
      <h1 className="page-title">Evaluation comparison</h1>
      <p className="lede">
        Queue a new catalog run. Official BASELINE vs ADVANCED figures live on the{" "}
        <a href="/evaluation">evaluation dashboard</a>, which reads evaluation JSON. This page does
        not recompute improvement.
      </p>
      {error ? <Banner kind="error">{error}</Banner> : null}
      {busy ? <Banner kind="loading">Working: {busy}… catalog runs can take a while.</Banner> : null}
      <div className="actions">
        <button type="button" disabled={busy !== null} onClick={() => void runSystem("baseline")}>
          Run baseline evaluation
        </button>
        <button type="button" className="secondary" disabled={busy !== null} onClick={() => void runSystem("agent")}>
          Run agent evaluation
        </button>
        <button type="button" className="secondary" disabled={busy !== null} onClick={() => void runCompare()}>
          Compare via API
        </button>
      </div>
      <div className="grid grid-2">
        <EvalCard title="Baseline" item={baseline} />
        <EvalCard title="Agent" item={agent} />
      </div>
      {comparison ? (
        <div className="card">
          <h2>API comparison</h2>
          <p className="muted">
            {comparison.comparison_id} · case lists identical: {String(comparison.case_lists_identical)} ·
            primary metric {comparison.primary_metric}
          </p>
          {wis && wis.relative_improvement === null ? (
            <Banner kind="warning">
              Official WIS relative_improvement is null in the comparison payload (failed cases remain
              in the aggregate). Do not treat completed-only means as the headline.
            </Banner>
          ) : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Agent</th>
                  <th>Relative improvement (API)</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(comparison.aggregate).map((row) => (
                  <tr key={row.name}>
                    <td>{row.name}</td>
                    <td className="metric">{formatNumber(row.baseline)}</td>
                    <td className="metric">{formatNumber(row.agent)}</td>
                    <td className="metric">{formatNumber(row.relative_improvement)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {comparison.notes.map((note) => (
            <p className="muted" key={note}>
              {note}
            </p>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No comparison yet"
          body="Run both systems, then Compare via API. Relative improvement is copied from the response; this page does not compute it."
        />
      )}
    </AppShell>
  );
}

function EvalCard({ title, item }: { title: string; item: EvaluationResponse | null }) {
  if (!item) {
    return (
      <div className="card">
        <h2>{title}</h2>
        <p className="muted">Not run in this session.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <h2>{title}</h2>
      <p>
        Status: {item.status}
        {item.evaluation_run_id ? ` · ${item.evaluation_run_id}` : ""}
      </p>
      {item.error ? (
        <Banner kind="error">
          {item.error.error_code}: {item.error.message}
        </Banner>
      ) : null}
      {item.aggregate ? (
        <dl className="dl">
          <dt>Official WIS</dt>
          <dd className="metric">{formatNumber(item.aggregate.wis)}</dd>
          <dt>WIS completed-only (not headline)</dt>
          <dd className="metric">{formatNumber(item.aggregate.wis_completed_only)}</dd>
          <dt>Cases failed</dt>
          <dd className="metric">{formatNumber(item.aggregate.n_cases_failed)}</dd>
          <dt>sMAPE</dt>
          <dd className="metric">{formatNumber(item.aggregate.smape)}</dd>
        </dl>
      ) : (
        <p className="muted">No aggregate yet.</p>
      )}
      {item.errors.length > 0 ? (
        <Banner kind="error">
          {item.errors.map((row) => `${row.case_id}: ${row.error_message ?? row.error_type}`).join(" ")}
        </Banner>
      ) : null}
    </div>
  );
}
