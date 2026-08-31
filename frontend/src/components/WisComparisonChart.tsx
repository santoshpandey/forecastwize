import { formatNumber } from "@/lib/format";

type CaseBar = {
  caseId: string;
  baseline: number | null;
  agent: number | null;
  challenging?: boolean;
};

function barWidth(value: number, max: number, full: number): number {
  if (!Number.isFinite(value) || max <= 0) {
    return 0;
  }
  return (value / max) * full;
}

export function AggregateWisChart({
  baseline,
  advanced,
}: {
  baseline: number;
  advanced: number;
}) {
  const max = Math.max(baseline, advanced, 0) * 1.12 || 1;
  const full = 520;
  const baselineW = barWidth(baseline, max, full);
  const advancedW = barWidth(advanced, max, full);
  return (
    <figure className="wis-figure">
      <figcaption className="chart-caption">WIS — lower is better</figcaption>
      <svg
        className="chart wis-chart"
        viewBox="0 0 720 140"
        role="img"
        aria-label={`Official aggregate WIS. Baseline ${baseline}. Advanced ${advanced}. Lower is better.`}
      >
        <text x="8" y="38" className="chart-label">
          Baseline
        </text>
        <rect x="120" y="20" width={baselineW} height="28" fill="#8a8a8a" />
        <text x={128 + baselineW} y="40" className="chart-value">
          {formatNumber(baseline)}
        </text>
        <text x="8" y="90" className="chart-label">
          Advanced
        </text>
        <rect x="120" y="72" width={advancedW} height="28" fill="#1f4e79" />
        <text x={128 + advancedW} y="92" className="chart-value">
          {formatNumber(advanced)}
        </text>
        <text x="120" y="128" className="chart-axis">
          Shorter bar is better
        </text>
      </svg>
    </figure>
  );
}

export function PerCaseWisChart({ rows }: { rows: CaseBar[] }) {
  const values = rows.flatMap((row) => [row.baseline, row.agent]).filter((value): value is number => value !== null && Number.isFinite(value));
  const max = (values.length ? Math.max(...values) : 1) * 1.08;
  const n = rows.length;
  const width = 720;
  const height = 280;
  const padLeft = 36;
  const padBottom = 48;
  const padTop = 16;
  const groupW = (width - padLeft - 16) / Math.max(n, 1);
  const barW = Math.max(6, groupW * 0.32);
  const plotH = height - padBottom - padTop;

  return (
    <figure className="wis-figure">
      <figcaption className="chart-caption">Per-case WIS — lower is better. All 12 catalog cases.</figcaption>
      <svg
        className="chart wis-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Baseline versus advanced WIS for every catalog case"
      >
        {rows.map((row, index) => {
          const x0 = padLeft + index * groupW;
          const bH = row.baseline === null ? 0 : (row.baseline / max) * plotH;
          const aH = row.agent === null ? 0 : (row.agent / max) * plotH;
          const challenging = Boolean(row.challenging);
          return (
            <g key={row.caseId}>
              {challenging ? (
                <rect
                  x={x0 - 2}
                  y={padTop - 4}
                  width={groupW}
                  height={plotH + 8}
                  fill="#f8eeee"
                />
              ) : null}
              <rect
                x={x0 + groupW * 0.12}
                y={padTop + plotH - bH}
                width={barW}
                height={bH}
                fill="#8a8a8a"
              />
              <rect
                x={x0 + groupW * 0.12 + barW + 3}
                y={padTop + plotH - aH}
                width={barW}
                height={aH}
                fill={challenging ? "#8b1e1e" : "#1f4e79"}
              />
              <text
                x={x0 + groupW * 0.45}
                y={height - 28}
                textAnchor="middle"
                className="chart-tick"
              >
                {row.caseId}
              </text>
              {challenging ? (
                <text
                  x={x0 + groupW * 0.45}
                  y={height - 12}
                  textAnchor="middle"
                  className="chart-tick-warn"
                >
                  challenge
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span>
          <i className="swatch swatch-baseline" aria-hidden="true" /> Baseline WIS
        </span>
        <span>
          <i className="swatch swatch-advanced" aria-hidden="true" /> Advanced WIS
        </span>
        <span>
          <i className="swatch swatch-challenge" aria-hidden="true" /> Case 012 challenging (loss retained)
        </span>
      </div>
    </figure>
  );
}
