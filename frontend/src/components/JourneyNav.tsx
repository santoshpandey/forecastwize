import type { DatasetResponse, RunResponse } from "@/lib/types";

type Step = {
  href: string | null;
  label: string;
  key: string;
};

export function JourneyNav({
  dataset,
  run,
  current,
}: {
  dataset: DatasetResponse | null;
  run: RunResponse | null;
  current: string;
}) {
  const datasetId = dataset?.id;
  const runId = run?.id;
  const steps: Step[] = [
    { key: "dashboard", href: "/", label: "Dashboard" },
    { key: "upload", href: "/upload", label: "Upload" },
    {
      key: "diagnostics",
      href: datasetId ? `/datasets/${datasetId}` : null,
      label: "Diagnostics",
    },
    {
      key: "configure",
      href: datasetId ? `/datasets/${datasetId}/configure` : null,
      label: "Configure",
    },
    { key: "execution", href: runId ? `/runs/${runId}` : null, label: "Agent run" },
    { key: "result", href: runId ? `/runs/${runId}/result` : null, label: "Forecast" },
    {
      key: "verification",
      href: runId ? `/runs/${runId}/verification` : null,
      label: "Verification",
    },
    {
      key: "comparison",
      href: runId ? `/runs/${runId}/comparison` : null,
      label: "Model comparison",
    },
    { key: "evaluation", href: "/evaluation", label: "Evaluation" },
  ];

  return (
    <ol className="journey" aria-label="Analysis journey">
      {steps.map((step) => (
        <li key={step.key}>
          {step.href ? (
            <a href={step.href} aria-current={current === step.key ? "page" : undefined}>
              {step.label}
            </a>
          ) : (
            <span>{step.label}</span>
          )}
        </li>
      ))}
    </ol>
  );
}
