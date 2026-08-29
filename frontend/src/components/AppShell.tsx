import type { ReactNode } from "react";

import { HealthStatus } from "@/components/HealthStatus";

export function AppShell({
  children,
  current,
}: {
  children: ReactNode;
  current: "dashboard" | "upload" | "evaluation" | "evaluations" | "workspace";
}) {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <div className="app-header-inner">
          <a className="brand" href="/">
            ForecastWize
          </a>
          <nav className="nav" aria-label="Primary">
            <a href="/" aria-current={current === "dashboard" ? "page" : undefined}>
              Dashboard
            </a>
            <a href="/upload" aria-current={current === "upload" ? "page" : undefined}>
              Upload dataset
            </a>
            <a href="/evaluation" aria-current={current === "evaluation" ? "page" : undefined}>
              Evaluation
            </a>
          </nav>
          <HealthStatus compact />
        </div>
      </header>
      <main id="main" className="main">
        {children}
      </main>
    </>
  );
}
