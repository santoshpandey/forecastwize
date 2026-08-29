"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Banner } from "@/components/Banner";
import { JourneyNav } from "@/components/JourneyNav";
import { ApiError, getEvaluationChangelog } from "@/lib/api";

export default function EvaluationChangelogPage() {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getEvaluationChangelog()
      .then((value) => {
        if (!cancelled) {
          setMarkdown(value.markdown);
          setPath(value.path);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Could not load the changelog.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell current="evaluation">
      <JourneyNav dataset={null} run={null} current="evaluation" />
      <h1 className="page-title">Experiment changelog</h1>
      <p className="lede">
        Repository file {path ?? "docs/changelog.md"}, served by the API. Scores still live in
        evaluation JSON, not in this narrative.
      </p>
      <div className="actions">
        <a className="button" href="/evaluation">
          Back to evaluation dashboard
        </a>
      </div>
      {!markdown && !error ? <Banner kind="loading">Loading changelog…</Banner> : null}
      {error ? <Banner kind="error">{error}</Banner> : null}
      {markdown ? (
        <article className="card">
          <pre className="prose changelog">{markdown}</pre>
        </article>
      ) : null}
    </AppShell>
  );
}
