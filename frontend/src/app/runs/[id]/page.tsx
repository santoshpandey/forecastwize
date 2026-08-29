"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AgentPipeline } from "@/components/AgentPipeline";
import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { HumanCheckpointPanel } from "@/components/HumanCheckpointPanel";
import { JourneyNav } from "@/components/JourneyNav";
import { ApiError, getDataset, getRun } from "@/lib/api";
import { asId } from "@/lib/route";
import { setStoredDatasetId, setStoredRunId } from "@/lib/session";
import type { DatasetResponse, RunResponse } from "@/lib/types";

function isActive(status: RunResponse["status"]): boolean {
  return status === "queued" || status === "running" || status === "retrying";
}

export default function RunExecutionPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<RunResponse | null>(null);
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const runId = asId(params.id);
    if (!runId) {
      return;
    }
    let cancelled = false;
    let timer: number | undefined;

    async function tick(target: string) {
      try {
        const next = await getRun(target);
        if (cancelled) {
          return;
        }
        setRun(next);
        setStoredRunId(next.id);
        setError(null);
        if (isActive(next.status)) {
          timer = window.setTimeout(() => {
            void tick(target);
          }, 1500);
        }
      } catch (caught: unknown) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Could not load the run.");
        }
      }
    }

    void tick(runId);
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [params.id]);

  useEffect(() => {
    if (!run) {
      return;
    }
    void getDataset(run.dataset_id)
      .then((value) => {
        setDataset(value);
        setStoredDatasetId(value.id);
      })
      .catch(() => {
        setDataset(null);
      });
  }, [run]);

  return (
    <AppShell current="workspace">
      <JourneyNav dataset={dataset} run={run} current="execution" />
      <h1 className="page-title">Agent execution</h1>
      <p className="lede">
        Steps reflect backend graph nodes. Status is polled from GET /runs; this page does not
        invent progress.
      </p>
      {!run && !error ? <Banner kind="loading">Loading run…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {run?.status === "failed" && run.error ? (
        <Banner kind="error">
          {run.error.error_code}: {run.error.message}
        </Banner>
      ) : null}
      {run ? <HumanCheckpointPanel run={run} onUpdated={setRun} /> : null}
      {run && isActive(run.status) ? (
        <Banner kind="loading">
          Run {run.status}
          {run.retry_number > 0 ? ` · retry ${run.retry_number} of ${run.max_retries}` : ""}
        </Banner>
      ) : null}
      {run ? (
        <>
          <div className="card">
            <h2>Pipeline</h2>
            <AgentPipeline run={run} />
          </div>
          {run.status === "completed" || run.status === "waiting_for_approval" ? (
            <div className="actions">
              <a className="button" href={`/runs/${run.id}/result`}>
                Open forecast result
              </a>
            </div>
          ) : null}
        </>
      ) : null}
    </AppShell>
  );
}
