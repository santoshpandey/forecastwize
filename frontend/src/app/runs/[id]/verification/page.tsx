"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { HumanCheckpointPanel } from "@/components/HumanCheckpointPanel";
import { JourneyNav } from "@/components/JourneyNav";
import { ApiError, getDataset, getRun } from "@/lib/api";
import { asId } from "@/lib/route";
import { setStoredDatasetId, setStoredRunId } from "@/lib/session";
import type { DatasetResponse, RunResponse } from "@/lib/types";

function checkKind(result: string): "error" | "warning" | "ok" {
  if (result === "FAIL") {
    return "error";
  }
  if (result === "WARN") {
    return "warning";
  }
  return "ok";
}

export default function VerificationPage() {
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
          setError(caught instanceof ApiError ? caught.message : "Could not load verification.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  return (
    <AppShell current="workspace">
      <JourneyNav dataset={dataset} run={run} current="verification" />
      <h1 className="page-title">Verification</h1>
      <p className="lede">
        Checks are deterministic backend results (PASS / WARN / FAIL). This page does not re-score
        residuals or coverage.
      </p>
      {!run && !error ? <Banner kind="loading">Loading verification…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {run?.verification_overall ? (
        <Banner kind={checkKind(run.verification_overall)}>
          Overall: {run.verification_overall}
          {run.overall_uncertainty ? ` · analyst uncertainty ${run.overall_uncertainty}` : ""}
        </Banner>
      ) : (
        run && <Banner kind="warning">No verification overall was returned for this run.</Banner>
      )}
      {run?.human_checkpoint ? <HumanCheckpointPanel run={run} onUpdated={setRun} /> : null}
      {run && run.verification_checks.length === 0 ? (
        <Banner kind="warning">No verification checks were attached to this run.</Banner>
      ) : null}
      {run
        ? run.verification_checks.map((check) => (
            <div className="card" key={check.check_id}>
              <h2>
                {check.check_id}: {check.name}
              </h2>
              <Banner kind={checkKind(check.result)}>
                {check.result} · severity {check.severity}
                {check.applicable ? "" : " · not applicable"}
              </Banner>
              <p>{check.explanation}</p>
            </div>
          ))
        : null}
    </AppShell>
  );
}
