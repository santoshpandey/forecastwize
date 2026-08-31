"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Banner, EmptyState } from "@/components/Banner";
import { WorkflowStrip } from "@/components/WorkflowStrip";
import { WorkspaceJourneyNav } from "@/components/WorkspaceJourneyNav";
import { AggregateWisChart, PerCaseWisChart } from "@/components/WisComparisonChart";
import { ApiError, getEvaluationDashboard } from "@/lib/api";
import { formatImprovementPercent, formatNumber, formatTimestamp } from "@/lib/format";
import type {
  CaseComparison,
  CatalogCase,
  EvaluationDashboardResponse,
  MetricComparison,
} from "@/lib/types";

const HEADLINE: { key: string; label: string; source: "metrics" | "runtime" | "failures" }[] = [
  { key: "wis", label: "WIS", source: "metrics" },
  { key: "smape", label: "sMAPE", source: "metrics" },
  { key: "wmape", label: "WMAPE", source: "metrics" },
  { key: "mase", label: "MASE", source: "metrics" },
  { key: "interval_coverage", label: "Coverage", source: "metrics" },
  { key: "interval_width", label: "Interval Width", source: "metrics" },
  { key: "wall_seconds", label: "Runtime", source: "runtime" },
  { key: "n_cases_failed", label: "Failures", source: "failures" },
];

type WisOutcome = "won" | "lost" | "tie" | "undefined";

function wisOutcome(row: CaseComparison): WisOutcome {
  const value = row.metrics.wis?.relative_improvement;
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "undefined";
  }
  if (value > 0) {
    return "won";
  }
  if (value < 0) {
    return "lost";
  }
  return "tie";
}

function headlineMetric(
  dashboard: EvaluationDashboardResponse,
  item: (typeof HEADLINE)[number],
): MetricComparison | undefined {
  const aggregate = dashboard.comparison.aggregate;
  if (item.source === "runtime") {
    return aggregate.wall_seconds;
  }
  if (item.source === "failures") {
    return aggregate.n_cases_failed;
  }
  return aggregate.metrics[item.key];
}

function catalogMap(catalog: CatalogCase[]): Map<string, CatalogCase> {
  return new Map(catalog.map((row) => [row.case_id, row]));
}

function improvementClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "muted";
  }
  if (value < 0) {
    return "delta-lost";
  }
  if (value > 0) {
    return "delta-won";
  }
  return "muted";
}

export default function EvaluationDashboardPage() {
  const [data, setData] = useState<EvaluationDashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void getEvaluationDashboard()
      .then((value) => {
        if (!cancelled) {
          setData(value);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(
            caught instanceof ApiError ? caught.message : "Could not load evaluation artifacts.",
          );
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
  }, []);

  const catalog = useMemo(() => catalogMap(data?.catalog ?? []), [data]);
  const won = data?.comparison.per_case.filter((row) => wisOutcome(row) === "won") ?? [];
  const lost = data?.comparison.per_case.filter((row) => wisOutcome(row) === "lost") ?? [];
  const tied = data?.comparison.per_case.filter((row) => wisOutcome(row) === "tie") ?? [];
  const challenging = data?.catalog.filter((row) => row.challenging) ?? [];
  const officialWis = data?.comparison.aggregate.metrics.wis;
  const nCases = data?.comparison.aggregate.n_cases;
  const nFailed = data?.comparison.aggregate.n_cases_failed.agent;
  const interventions = data?.comparison.aggregate.human_intervention_count;

  return (
    <AppShell current="evaluation">
      <WorkspaceJourneyNav current="evaluation" />
      <h1 className="page-title">Evaluation dashboard</h1>
      <p className="lede">
        BASELINE vs ADVANCED on the shared catalog. Every figure is copied from evaluation JSON.
        This page does not calculate WIS or other official metrics in the browser.
      </p>
      <WorkflowStrip />
      <Banner kind="ok">Improvement is calculated from the evaluation artifacts.</Banner>
      {loading ? <Banner kind="loading">Loading evaluation/results/comparison.json via the API…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {data ? (
        <>
          <p className="muted">
            Artifact <code>{data.artifact_path}</code>
            {data.baseline_artifact_path ? ` · ${data.baseline_artifact_path}` : ""}
            {data.agent_artifact_path ? ` · ${data.agent_artifact_path}` : ""} ·{" "}
            {data.comparison.comparison_id} · git {data.comparison.git_commit ?? "unknown"} ·{" "}
            {formatTimestamp(data.comparison.timestamp)}
          </p>
          <div className="actions">
            <Link className="button" href="/evaluation/changelog">
              Experiment changelog
            </Link>
            <Link className="button secondary" href="/evaluations">
              Queue a new catalog run
            </Link>
          </div>
          {officialWis && officialWis.relative_improvement === null ? (
            <Banner kind="warning">
              Official aggregate WIS relative_improvement is null in the artifact. Failed cases stay
              in the case list. Completed-only means are not the headline.
            </Banner>
          ) : null}
          {!data.comparison.case_lists_identical ? (
            <Banner kind="error">Case lists in the artifact are not identical.</Banner>
          ) : null}

          <section className="hero-result" aria-labelledby="official-result-heading">
            <h2 id="official-result-heading" className="section-title">
              Official result
            </h2>
            <p className={`hero-improvement ${improvementClass(officialWis?.relative_improvement ?? null)}`}>
              <span className="metric-hero">{formatImprovementPercent(officialWis?.relative_improvement)}</span>
              <span className="hero-kicker">WIS improvement · primary metric · lower WIS is better</span>
            </p>
            <div className="hero-grid">
              <article className="card">
                <h3>Baseline WIS</h3>
                <p className="metric hero-metric">{formatNumber(officialWis?.baseline)}</p>
              </article>
              <article className="card">
                <h3>Advanced WIS</h3>
                <p className="metric hero-metric">{formatNumber(officialWis?.agent)}</p>
              </article>
              <article className="card">
                <h3>Catalog</h3>
                <p className="metric hero-metric">
                  {formatNumber(nCases ?? null)} cases
                </p>
                <p className="muted">
                  Failures (advanced): {formatNumber(nFailed ?? null)}
                </p>
              </article>
              <article className="card">
                <h3>Holdout WIS outcomes</h3>
                <p className="metric">
                  {formatNumber(won.length)} advanced wins · {formatNumber(lost.length)} baseline
                  wins · {formatNumber(tied.length)} ties
                </p>
                <p className="muted">Counted from per-case WIS relative_improvement in the artifact.</p>
              </article>
            </div>
          </section>

          {officialWis?.baseline !== null &&
          officialWis?.baseline !== undefined &&
          officialWis.agent !== null &&
          officialWis.agent !== undefined ? (
            <div className="card">
              <h2>Aggregate WIS</h2>
              <AggregateWisChart baseline={officialWis.baseline} advanced={officialWis.agent} />
            </div>
          ) : null}

          <h2 className="section-title">Per-case WIS</h2>
          <div className="card">
            <PerCaseWisChart
              rows={data.comparison.per_case.map((row) => ({
                caseId: row.case_id,
                baseline: row.metrics.wis?.baseline ?? null,
                agent: row.metrics.wis?.agent ?? null,
                challenging: Boolean(catalog.get(row.case_id)?.challenging),
              }))}
            />
          </div>

          <h2 className="section-title">Human checkpoints vs human decisions</h2>
          <div className="card">
            <p>
              Automated catalog <code>{data.comparison.agent_evaluation_run_id}</code>:{" "}
              <strong className="metric">
                {formatNumber(interventions?.agent ?? null)}
              </strong>{" "}
              <code>HUMAN_CHECKPOINT_CREATED</code> events (artifact{" "}
              <code>human_intervention_count</code>). That count is checkpoints opened, not
              Accept clicks. Official catalog trajectories contain{" "}
              <strong>0</strong> <code>HUMAN_DECISION</code> events.
            </p>
            <p className="muted">
              Interactive Accept lives on a live Agent run (or the checked-in demo under{" "}
              <code>evaluation/artifacts/human-demo/</code>): checkpoint created → human Accept →{" "}
              <code>HUMAN_DECISION</code> → <code>RUN_COMPLETED</code>. The catalog harness does
              not auto-approve.
            </p>
          </div>

          <h2 className="section-title">Challenging case</h2>
          {challenging.length === 0 ? (
            <EmptyState
              title="No challenging case labeled"
              body="The catalog did not mark any case as adversarial."
            />
          ) : (
            challenging.map((item) => {
              const row = data.comparison.per_case.find((entry) => entry.case_id === item.case_id);
              const wis = row?.metrics.wis;
              const outcome = row ? wisOutcome(row) : "undefined";
              return (
                <div className="card card-challenge" key={item.case_id}>
                  <h3>
                    Case {item.case_id} — {item.name}
                    {item.challenging ? " · challenging" : ""}
                  </h3>
                  <Banner kind="warning">
                    Catalog challenge: {item.expected_challenge}. Negative results are retained.
                    {outcome === "lost" ? " Advanced loses this case on holdout WIS." : ""}
                  </Banner>
                  <p>{item.description}</p>
                  {row ? (
                    <dl className="dl">
                      <dt>Baseline status</dt>
                      <dd>{row.baseline_status}</dd>
                      <dt>Advanced status</dt>
                      <dd>{row.agent_status}</dd>
                      <dt>WIS baseline</dt>
                      <dd className="metric">{formatNumber(wis?.baseline)}</dd>
                      <dt>WIS advanced</dt>
                      <dd className="metric">{formatNumber(wis?.agent)}</dd>
                      <dt>WIS improvement</dt>
                      <dd className={`metric ${improvementClass(wis?.relative_improvement)}`}>
                        {formatImprovementPercent(wis?.relative_improvement)}
                      </dd>
                    </dl>
                  ) : (
                    <p className="muted">This case is not in the comparison artifact.</p>
                  )}
                  {item.case_id === "012" ? (
                    <p className="muted">
                      EXP-010 selection for this catalog case is recorded in the official
                      trajectory{" "}
                      <code>evaluation/results/trajectories/agent-20260830T030413Z/case_012.jsonl</code>
                      , not in comparison JSON: <code>MODEL_VETOED</code> seasonal_naive, ets,
                      arima; <code>MODEL_SELECTED</code> naive. This page does not recompute those
                      events.
                    </p>
                  ) : null}
                </div>
              );
            })
          )}

          <h2 className="section-title">Aggregate comparison</h2>
          <div className="metric-tiles">
            {HEADLINE.map((item) => {
              const metric = headlineMetric(data, item);
              return (
                <article className="card metric-tile" key={item.key}>
                  <h3>{item.label}</h3>
                  <dl className="dl compact">
                    <dt>Baseline</dt>
                    <dd className="metric">{formatNumber(metric?.baseline)}</dd>
                    <dt>Advanced</dt>
                    <dd className="metric">{formatNumber(metric?.agent)}</dd>
                    <dt>Improvement</dt>
                    <dd className={`metric ${improvementClass(metric?.relative_improvement)}`}>
                      {formatImprovementPercent(metric?.relative_improvement)}
                    </dd>
                  </dl>
                </article>
              );
            })}
          </div>

          <h2 className="section-title">Cases where advanced won</h2>
          <p className="muted">WIS relative_improvement &gt; 0 in the artifact. Empty if none.</p>
          <OutcomeTable rows={won} catalog={catalog} empty="No case has a positive WIS relative_improvement in this artifact." />

          <h2 className="section-title">Cases where advanced lost</h2>
          <p className="muted">WIS relative_improvement &lt; 0 in the artifact. Losses are not omitted.</p>
          <OutcomeTable rows={lost} catalog={catalog} empty="No case has a negative WIS relative_improvement in this artifact." />

          <h2 className="section-title">Per-case comparison</h2>
          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Challenge</th>
                    <th>WIS baseline</th>
                    <th>WIS advanced</th>
                    <th>WIS improvement</th>
                    <th>Outcome</th>
                    <th>sMAPE</th>
                    <th>Coverage</th>
                    <th>Runtime</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.comparison.per_case.map((row) => {
                    const meta = catalog.get(row.case_id);
                    const outcome = wisOutcome(row);
                    const wis = row.metrics.wis;
                    return (
                      <tr key={row.case_id} className={outcome === "lost" ? "row-lost" : undefined}>
                        <td>
                          {row.case_id}
                          {meta ? ` ${meta.name}` : ""}
                          {meta?.challenging ? " · challenging" : ""}
                        </td>
                        <td>{meta?.expected_challenge ?? "—"}</td>
                        <td className="metric">{formatNumber(wis?.baseline)}</td>
                        <td className="metric">{formatNumber(wis?.agent)}</td>
                        <td className={`metric ${improvementClass(wis?.relative_improvement)}`}>
                          {formatImprovementPercent(wis?.relative_improvement)}
                        </td>
                        <td>{outcome}</td>
                        <td className={`metric ${improvementClass(row.metrics.smape?.relative_improvement)}`}>
                          {formatImprovementPercent(row.metrics.smape?.relative_improvement)}
                        </td>
                        <td className={`metric ${improvementClass(row.metrics.interval_coverage?.relative_improvement)}`}>
                          {formatImprovementPercent(row.metrics.interval_coverage?.relative_improvement)}
                        </td>
                        <td className={`metric ${improvementClass(row.runtime_seconds.relative_improvement)}`}>
                          {formatImprovementPercent(row.runtime_seconds.relative_improvement)}
                        </td>
                        <td>
                          {row.baseline_status}/{row.agent_status}
                          {row.agent_error_message ? ` · ${row.agent_error_message}` : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {data.comparison.notes.map((note) => (
            <p className="muted" key={note}>
              {note}
            </p>
          ))}
        </>
      ) : null}
    </AppShell>
  );
}

function OutcomeTable({
  rows,
  catalog,
  empty,
}: {
  rows: CaseComparison[];
  catalog: Map<string, CatalogCase>;
  empty: string;
}) {
  if (rows.length === 0) {
    return <EmptyState title="None in this artifact" body={empty} />;
  }
  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Case</th>
              <th>Challenge</th>
              <th>WIS baseline</th>
              <th>WIS advanced</th>
              <th>Improvement</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const meta = catalog.get(row.case_id);
              const wis = row.metrics.wis;
              return (
                <tr key={row.case_id}>
                  <td>
                    {row.case_id} {meta?.name ?? ""}
                  </td>
                  <td>{meta?.expected_challenge ?? "—"}</td>
                  <td className="metric">{formatNumber(wis?.baseline)}</td>
                  <td className="metric">{formatNumber(wis?.agent)}</td>
                  <td className={`metric ${improvementClass(wis?.relative_improvement)}`}>
                    {formatImprovementPercent(wis?.relative_improvement)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
