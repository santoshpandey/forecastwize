import type { ReactNode } from "react";

export function Banner({
  kind,
  children,
}: {
  kind: "error" | "warning" | "ok" | "loading";
  children: ReactNode;
}) {
  const role = kind === "error" ? "alert" : "status";
  return (
    <div className={`banner banner-${kind}`} role={role} aria-live="polite">
      {children}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  embedded = false,
}: {
  title: string;
  body: string;
  embedded?: boolean;
}) {
  const heading = embedded ? (
    <p>
      <strong>{title}</strong>
    </p>
  ) : (
    <h2>{title}</h2>
  );
  if (embedded) {
    return (
      <div>
        {heading}
        <p className="muted">{body}</p>
      </div>
    );
  }
  return (
    <div className="card">
      {heading}
      <p className="muted">{body}</p>
    </div>
  );
}
