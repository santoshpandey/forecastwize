"use client";

import { useState } from "react";

import { Banner } from "@/components/Banner";
import { ApiError, decideRunCheckpoint } from "@/lib/api";
import type { RunResponse } from "@/lib/types";

const TRIGGER_LABELS: Record<string, string> = {
  data_modification_proposed: "Data modification proposed",
  low_forecast_confidence: "Forecast confidence is low",
  verification_failed_repeatedly: "Verification failed repeatedly",
  material_uncertainty: "Material uncertainty remains",
};

export function HumanCheckpointPanel({
  run,
  onUpdated,
}: {
  run: RunResponse;
  onUpdated: (next: RunResponse) => void;
}) {
  const checkpoint = run.human_checkpoint;
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!checkpoint) {
    return null;
  }
  const decided =
    checkpoint.status === "approved" || checkpoint.status === "rejected";
  const waiting = checkpoint.required && checkpoint.status === "waiting_for_approval";
  if (!waiting && !decided && !checkpoint.required) {
    return null;
  }
  const triggers = checkpoint.triggers ?? [];
  const transforms = checkpoint.proposed_transforms ?? [];

  async function decide(action: "accept" | "reject" | "review") {
    setBusy(action);
    setError(null);
    try {
      const next = await decideRunCheckpoint(run.id, action, note.trim() || undefined);
      onUpdated(next);
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Could not record the checkpoint.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card" aria-labelledby="checkpoint-heading">
      <h2 id="checkpoint-heading">Human checkpoint</h2>
      {waiting ? (
        <Banner kind="warning">
          <strong>Decision required.</strong> {checkpoint.reason} This control does not
          auto-approve. Source data is not modified.
        </Banner>
      ) : null}
      {checkpoint.status === "approved" ? (
        <Banner kind="ok">
          Accepted. Source data unmodified: {String(checkpoint.source_data_unmodified)}.{" "}
          {checkpoint.decision_note}
        </Banner>
      ) : null}
      {checkpoint.status === "rejected" ? (
        <Banner kind="warning">
          Rejected. The recommendation was not adopted. Source data unmodified:{" "}
          {String(checkpoint.source_data_unmodified)}. {checkpoint.decision_note}
        </Banner>
      ) : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {triggers.length > 0 ? (
        <ul>
          {triggers.map((item) => (
            <li key={item}>{TRIGGER_LABELS[item] ?? item}</li>
          ))}
        </ul>
      ) : null}
      <p className="muted">
        Checkpoint: {checkpoint.checkpoint_id ?? "unassigned"}. Evidence:{" "}
        {checkpoint.evidence_ids.join(", ") || "none"}. Status: {checkpoint.status}.
      </p>
      {transforms.length > 0 ? (
        <div>
          <h3>Proposed data modifications (not applied)</h3>
          <ul>
            {transforms.map((item) => (
              <li key={item.name}>
                {item.name}: {item.policy}. {item.reason} Applied: {String(item.applied)}.
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {waiting ? (
        <>
          <label htmlFor={`checkpoint-note-${run.id}`}>Note (optional)</label>
          <input
            id={`checkpoint-note-${run.id}`}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            disabled={busy !== null}
          />
          <div className="actions">
            <button type="button" disabled={busy !== null} onClick={() => void decide("accept")}>
              {busy === "accept" ? "Recording…" : "Accept"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy !== null}
              onClick={() => void decide("reject")}
            >
              {busy === "reject" ? "Recording…" : "Reject"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy !== null}
              onClick={() => void decide("review")}
            >
              {busy === "review" ? "Recording…" : "Review"}
            </button>
          </div>
          <p className="muted">
            Accept records approval of the recommendation. Reject preserves the rejection on the
            run trajectory. Review keeps the gate open. None of these actions modify the original
            dataset.
          </p>
        </>
      ) : null}
    </section>
  );
}
