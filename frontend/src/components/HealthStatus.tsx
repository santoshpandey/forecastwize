"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, getHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; data: HealthResponse };

export function HealthStatus({ compact = false }: { compact?: boolean }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const data = await getHealth();
      setState({ status: "ok", data });
    } catch (error: unknown) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Could not reach the ForecastWize API. Start the backend and retry.";
      setState({ status: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (compact) {
    if (state.status === "loading") {
      return (
        <p className="health-compact" aria-live="polite">
          Checking API…
        </p>
      );
    }
    if (state.status === "error") {
      return (
        <p className="health-compact" role="alert">
          API unreachable
        </p>
      );
    }
    return (
      <p className="health-compact" aria-live="polite">
        API {state.data.status} · {state.data.environment}
      </p>
    );
  }

  if (state.status === "loading") {
    return (
      <p className="banner banner-loading" aria-live="polite">
        Checking API health…
      </p>
    );
  }

  if (state.status === "error") {
    return (
      <div className="banner banner-error" role="alert">
        <p>{state.message}</p>
        <button type="button" className="secondary" onClick={() => void load()}>
          Retry health check
        </button>
      </div>
    );
  }

  return (
    <div className="banner banner-ok" aria-live="polite">
      <p>
        API <strong>{state.data.status}</strong> · {state.data.service} {state.data.version} ·{" "}
        {state.data.environment}
      </p>
      <p className="muted">Checked at {state.data.timestamp}</p>
    </div>
  );
}
