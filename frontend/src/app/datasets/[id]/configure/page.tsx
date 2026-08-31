"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { WorkspaceJourneyNav } from "@/components/WorkspaceJourneyNav";
import { ApiError, createRun, getDataset } from "@/lib/api";
import { asId } from "@/lib/route";
import { setStoredDatasetId, setStoredRunId } from "@/lib/session";
import type { DatasetResponse } from "@/lib/types";

export default function ConfigurePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [frequency, setFrequency] = useState("");
  const [horizon, setHorizon] = useState("14");
  const [coverage, setCoverage] = useState("0.95");
  const [seed, setSeed] = useState("42");

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
        setFrequency(value.frequency ?? "");
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

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dataset) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await createRun({
        dataset_id: dataset.id,
        horizon: Number(horizon),
        frequency: frequency || undefined,
        coverage: Number(coverage),
        seed: seed === "" ? undefined : Number(seed),
      });
      setStoredRunId(run.id);
      router.push(`/runs/${run.id}`);
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Could not start the agent run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell current="workspace">
      <WorkspaceJourneyNav current="configure" datasetId={dataset?.id ?? null} />
      <h1 className="page-title">Forecast configuration</h1>
      <p className="lede">
        Horizon, frequency, and coverage are sent to the API. The agent graph selects a strategy
        from backtest WIS; this form does not pick a winning model.
      </p>
      <div className="card">
        <h2>Official selection policy (frozen)</h2>
        <p>
          Production default is <strong>EXP-010</strong> (
          <code>selection_policy=exp010</code>, model-specific origins, last/earlier WIS veto{" "}
          <code>R=5.0</code>). This form does not change that policy or the official catalog
          benchmark.
        </p>
        <p className="muted">
          Official evaluation results are displayed on Evaluation. Do not treat this screen as a
          way to retune R or swap the frozen selection rule.
        </p>
      </div>
      {loading ? <Banner kind="loading">Loading dataset…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {dataset && !dataset.frequency ? (
        <Banner kind="warning">
          Frequency is unresolved on this dataset. Provide an explicit pandas offset alias before
          running.
        </Banner>
      ) : null}
      {dataset ? (
        <form className="card" onSubmit={(event) => void onSubmit(event)}>
          <label htmlFor="horizon">Forecast horizon (steps)</label>
          <input
            id="horizon"
            name="horizon"
            type="number"
            min={1}
            max={366}
            value={horizon}
            onChange={(event) => setHorizon(event.target.value)}
            required
          />
          <label htmlFor="frequency">Frequency</label>
          <input
            id="frequency"
            name="frequency"
            value={frequency}
            onChange={(event) => setFrequency(event.target.value)}
            placeholder="D, W-SUN, MS…"
          />
          <label htmlFor="coverage">Nominal interval coverage</label>
          <input
            id="coverage"
            name="coverage"
            type="number"
            min={0.01}
            max={0.99}
            step={0.01}
            value={coverage}
            onChange={(event) => setCoverage(event.target.value)}
            required
          />
          <label htmlFor="seed">Random seed (optional)</label>
          <input
            id="seed"
            name="seed"
            type="number"
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
          />
          <div className="actions">
            <button type="submit" disabled={busy}>
              {busy ? "Starting…" : "Run agent graph"}
            </button>
            <Link className="button secondary" href={`/datasets/${dataset.id}`}>
              Back to diagnostics
            </Link>
          </div>
        </form>
      ) : null}
    </AppShell>
  );
}
