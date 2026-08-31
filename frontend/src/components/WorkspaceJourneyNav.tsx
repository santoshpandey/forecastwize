"use client";

import { useEffect, useState } from "react";

import { JourneyNav } from "@/components/JourneyNav";
import { getStoredDatasetId, getStoredRunId } from "@/lib/session";

export function WorkspaceJourneyNav({
  current,
  datasetId = null,
  runId = null,
}: {
  current: string;
  datasetId?: string | null;
  runId?: string | null;
}) {
  const [storedDatasetId, setStoredDatasetId] = useState<string | null>(null);
  const [storedRunId, setStoredRunId] = useState<string | null>(null);

  useEffect(() => {
    setStoredDatasetId(getStoredDatasetId());
    setStoredRunId(getStoredRunId());
  }, [datasetId, runId]);

  return (
    <JourneyNav
      current={current}
      datasetId={datasetId ?? storedDatasetId}
      runId={runId ?? storedRunId}
    />
  );
}
