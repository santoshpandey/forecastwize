"use client";

import Link from "next/link";

type Step = {
  key: string;
  label: string;
  href: string | null;
  unavailableHint: string;
};

export function JourneyNav({
  datasetId,
  runId,
  current,
}: {
  datasetId: string | null;
  runId: string | null;
  current: string;
}) {
  const steps: Step[] = [
    { key: "dashboard", href: "/", label: "Dashboard", unavailableHint: "" },
    { key: "upload", href: "/upload", label: "Upload", unavailableHint: "" },
    {
      key: "diagnostics",
      href: datasetId ? `/datasets/${datasetId}` : null,
      label: "Diagnostics",
      unavailableHint: "Upload a dataset in this session first.",
    },
    {
      key: "configure",
      href: datasetId ? `/datasets/${datasetId}/configure` : null,
      label: "Configure",
      unavailableHint: "Upload a dataset in this session first.",
    },
    {
      key: "execution",
      href: runId ? `/runs/${runId}` : null,
      label: "Agent run",
      unavailableHint: "Start an agent run from Configure first.",
    },
    {
      key: "result",
      href: runId ? `/runs/${runId}/result` : null,
      label: "Forecast",
      unavailableHint: "Start an agent run from Configure first.",
    },
    {
      key: "verification",
      href: runId ? `/runs/${runId}/verification` : null,
      label: "Verification",
      unavailableHint: "Start an agent run from Configure first.",
    },
    {
      key: "comparison",
      href: runId ? `/runs/${runId}/comparison` : null,
      label: "Model comparison",
      unavailableHint: "Start an agent run from Configure first.",
    },
    { key: "evaluation", href: "/evaluation", label: "Evaluation", unavailableHint: "" },
  ];

  return (
    <ol className="journey" aria-label="Analysis journey">
      {steps.map((step) => (
        <li key={step.key}>
          {step.href ? (
            <Link href={step.href} aria-current={current === step.key ? "page" : undefined}>
              {step.label}
            </Link>
          ) : (
            <span
              className="journey-unavailable"
              aria-disabled="true"
              title={step.unavailableHint}
            >
              {step.label}
              <span className="visually-hidden"> — {step.unavailableHint}</span>
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
