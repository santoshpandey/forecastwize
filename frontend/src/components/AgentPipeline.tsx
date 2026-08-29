import { PIPELINE_STEPS, type RunResponse } from "@/lib/types";

function stepState(
  run: RunResponse,
  nodes: readonly string[],
): "pending" | "current" | "done" | "failed" {
  if (run.status === "failed" && nodes.some((node) => run.nodes_visited.includes(node))) {
    return "failed";
  }
  const visited = nodes.some((node) => run.nodes_visited.includes(node));
  const last = run.nodes_visited[run.nodes_visited.length - 1];
  const isCurrent = last !== undefined && nodes.includes(last) && run.status !== "completed";
  if (isCurrent) {
    return "current";
  }
  if (visited || run.status === "completed") {
    return visited ? "done" : "pending";
  }
  return "pending";
}

export function AgentPipeline({ run }: { run: RunResponse }) {
  return (
    <ol className="pipeline" aria-label="Agent execution">
      {PIPELINE_STEPS.map((step, index) => {
        const state = stepState(run, step.nodes);
        const mark =
          state === "done" ? "mark-done" : state === "current" ? "mark-current" : state === "failed" ? "mark-failed" : "";
        return (
          <li key={step.id} className={state}>
            <span className={`mark ${mark}`} aria-hidden="true" />
            <span>
              {index + 1}. {step.label}
            </span>
            <span className="muted">{state}</span>
          </li>
        );
      })}
    </ol>
  );
}
