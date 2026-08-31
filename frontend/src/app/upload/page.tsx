"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { WorkspaceJourneyNav } from "@/components/WorkspaceJourneyNav";
import { ApiError, uploadDataset } from "@/lib/api";
import { setStoredDatasetId } from "@/lib/session";

export default function UploadPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setWarning(null);
    const form = event.currentTarget;
    const input = form.elements.namedItem("file");
    if (!(input instanceof HTMLInputElement) || !input.files?.[0]) {
      setError("Choose a .csv file before uploading.");
      return;
    }
    const file = input.files[0];
    setBusy(true);
    try {
      const dataset = await uploadDataset(file);
      setStoredDatasetId(dataset.id);
      if (dataset.warnings.length > 0) {
        setWarning(dataset.warnings.map((item) => item.message).join(" "));
      }
      router.push(`/datasets/${dataset.id}`);
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell current="upload">
      <WorkspaceJourneyNav current="upload" />
      <h1 className="page-title">Upload dataset</h1>
      <p className="lede">
        Files are validated by the API (type, size, CSV structure, path safety). The original file
        is stored as uploaded; missing values are recorded, not filled.
      </p>
      {error ? <Banner kind="error">{error}</Banner> : null}
      {warning ? <Banner kind="warning">{warning}</Banner> : null}
      {busy ? <Banner kind="loading">Uploading and validating…</Banner> : null}
      <form className="card" onSubmit={(event) => void onSubmit(event)}>
        <label htmlFor="file">CSV file</label>
        <input id="file" name="file" type="file" accept=".csv,text/csv" required />
        <p className="muted">Required columns: timestamp, value. Optional: series_id, context, event.</p>
        <div className="actions">
          <button type="submit" disabled={busy}>
            Upload and inspect
          </button>
        </div>
      </form>
    </AppShell>
  );
}
