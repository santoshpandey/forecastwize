const STEPS = [
  "Data",
  "Data Detective",
  "Context Analysis",
  "Forecast Strategy",
  "Backtest",
  "Robustness",
  "Model Selection",
  "Forecast",
  "Verification",
  "Human checkpoint when required",
] as const;

export function WorkflowStrip() {
  return (
    <nav className="workflow-strip" aria-label="Implemented agent workflow">
      <ol>
        {STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="muted">
        Presentation of the existing graph. Robustness and model selection run inside the
        backtest node (EXP-010). This strip does not invent runtime events.
      </p>
    </nav>
  );
}
