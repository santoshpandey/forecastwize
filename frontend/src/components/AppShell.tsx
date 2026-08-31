import type { ReactNode } from "react";
import Link from "next/link";

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
          <Link className="brand" href="/">
            ForecastWize
          </Link>
          <nav className="nav" aria-label="Primary">
            <Link href="/" aria-current={current === "dashboard" ? "page" : undefined}>
              Dashboard
            </Link>
            <Link href="/upload" aria-current={current === "upload" ? "page" : undefined}>
              Upload dataset
            </Link>
            <Link href="/evaluation" aria-current={current === "evaluation" ? "page" : undefined}>
              Evaluation
            </Link>
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
