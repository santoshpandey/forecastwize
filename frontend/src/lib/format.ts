/** Display helpers only. Do not compute forecasting metrics here. */

export function formatTimestamp(value: string | null): string {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toISOString().replace(".000Z", "Z");
}

export function formatDisplayDate(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function formatForecastNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatCoveragePercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Not available";
  }
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}%`;
}

export function formatFrequencyLabel(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
  }
  if (value === "D") {
    return "Daily";
  }
  if (value === "W" || value.startsWith("W-")) {
    return `Weekly (${value})`;
  }
  if (value === "M" || value === "MS" || value === "ME") {
    return "Monthly";
  }
  return value;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/** Display the artifact's relative_improvement as a percent. Does not compute WIS. */
export function formatImprovementPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}
