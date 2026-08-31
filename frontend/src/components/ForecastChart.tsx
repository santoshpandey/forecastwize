"use client";

import { useMemo, useState, type MouseEvent } from "react";

import { formatDisplayDate, formatForecastNumber } from "@/lib/format";
import type { ForecastResult, SeriesPoint } from "@/lib/types";

function xOf(index: number, n: number, width: number, pad: number): number {
  if (n <= 1) {
    return pad;
  }
  return pad + (index / (n - 1)) * (width - pad * 2);
}

function yOf(value: number, min: number, max: number, height: number, pad: number): number {
  const span = max - min || 1;
  return height - pad - ((value - min) / span) * (height - pad * 2);
}

type HoverPoint = {
  index: number;
  kind: "history" | "forecast";
  timestamp: string;
  value: number | null;
  lower: number | null;
  upper: number | null;
};

export function ForecastChart({
  history,
  forecast,
}: {
  history: SeriesPoint[];
  forecast: ForecastResult | null;
}) {
  const [hover, setHover] = useState<HoverPoint | null>(null);
  const histVals = history
    .map((point) => point.value)
    .filter((value): value is number => value !== null);
  const forecastVals = forecast ? [...forecast.yhat, ...forecast.lower, ...forecast.upper] : [];
  const all = [...histVals, ...forecastVals];
  const width = 720;
  const height = 300;
  const pad = 36;
  const offset = history.length;
  const total = history.length + (forecast?.yhat.length ?? 0);

  const points: HoverPoint[] = useMemo(() => {
    const rows: HoverPoint[] = history.map((point, index) => ({
      index,
      kind: "history" as const,
      timestamp: point.timestamp,
      value: point.value,
      lower: null,
      upper: null,
    }));
    if (forecast) {
      forecast.timestamps.forEach((stamp, i) => {
        rows.push({
          index: offset + i,
          kind: "forecast",
          timestamp: stamp,
          value: forecast.yhat[i] ?? null,
          lower: forecast.lower[i] ?? null,
          upper: forecast.upper[i] ?? null,
        });
      });
    }
    return rows;
  }, [forecast, history, offset]);

  if (all.length === 0) {
    return <p className="muted">No series values were returned by the API.</p>;
  }
  const min = Math.min(...all);
  const max = Math.max(...all);
  const histPath = history
    .map((point, index) => {
      if (point.value === null) {
        return null;
      }
      const command = index === 0 ? "M" : "L";
      return `${command} ${xOf(index, total, width, pad)} ${yOf(point.value, min, max, height, pad)}`;
    })
    .filter((part): part is string => part !== null)
    .join(" ");

  const lastHistoryIndex = [...history]
    .map((point, index) => (point.value === null ? -1 : index))
    .filter((index) => index >= 0)
    .at(-1);
  const lastHistoryValue =
    lastHistoryIndex !== undefined ? history[lastHistoryIndex]?.value : null;
  let band = "";
  let forecastLine = "";
  if (forecast) {
    const upper = forecast.upper.map((value, index) => {
      return `${xOf(offset + index, total, width, pad)},${yOf(value, min, max, height, pad)}`;
    });
    const lower = [...forecast.lower]
      .reverse()
      .map((value, revIndex) => {
        const index = forecast.lower.length - 1 - revIndex;
        return `${xOf(offset + index, total, width, pad)},${yOf(value, min, max, height, pad)}`;
      });
    band = `M ${upper.join(" L ")} L ${lower.join(" L ")} Z`;
    const firstYhat = forecast.yhat[0];
    const connector =
      lastHistoryIndex !== undefined &&
      lastHistoryValue !== null &&
      lastHistoryValue !== undefined &&
      firstYhat !== undefined
        ? `M ${xOf(lastHistoryIndex, total, width, pad)} ${yOf(lastHistoryValue, min, max, height, pad)} L ${xOf(offset, total, width, pad)} ${yOf(firstYhat, min, max, height, pad)} `
        : "";
    forecastLine =
      connector +
      forecast.yhat
        .map((value, index) => {
          const command = index === 0 && connector === "" ? "M" : "L";
          return `${command} ${xOf(offset + index, total, width, pad)} ${yOf(value, min, max, height, pad)}`;
        })
        .join(" ");
  }

  const splitX = forecast ? xOf(Math.max(offset - 1, 0), total, width, pad) : null;
  const firstHist = history[0]?.timestamp ?? null;
  const lastFc = forecast?.timestamps.at(-1) ?? null;
  const startFc = forecast?.timestamps[0] ?? null;

  function onMove(event: MouseEvent<SVGSVGElement>): void {
    const rect = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - rect.left) / rect.width) * width;
    let best: HoverPoint | null = null;
    let bestDist = Infinity;
    for (const point of points) {
      const x = xOf(point.index, total, width, pad);
      const dist = Math.abs(x - viewX);
      if (dist < bestDist) {
        bestDist = dist;
        best = point;
      }
    }
    setHover(best);
  }

  return (
    <figure className="chart-figure">
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Historical series with backend point forecast and prediction interval"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {splitX !== null ? (
          <rect
            x={splitX}
            y={pad - 8}
            width={width - pad - splitX}
            height={height - pad * 2 + 8}
            fill="#eef3f8"
          />
        ) : null}
        {band ? <path d={band} fill="#c5d4e4" stroke="none" /> : null}
        {histPath ? <path d={histPath} fill="none" stroke="#1b1b1b" strokeWidth="1.8" /> : null}
        {forecastLine ? (
          <path
            d={forecastLine}
            fill="none"
            stroke="#1f4e79"
            strokeWidth="2"
            strokeDasharray="5 4"
          />
        ) : null}
        {splitX !== null ? (
          <>
            <line
              x1={splitX}
              x2={splitX}
              y1={pad - 8}
              y2={height - pad}
              stroke="#1f4e79"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            <text x={splitX + 6} y={pad - 12} fontSize="11" fill="#1f4e79">
              Forecast starts
            </text>
          </>
        ) : null}
        {hover ? (
          <circle
            cx={xOf(hover.index, total, width, pad)}
            cy={
              hover.value === null
                ? height / 2
                : yOf(hover.value, min, max, height, pad)
            }
            r="3.5"
            fill="#1f4e79"
          />
        ) : null}
        <text x={4} y={pad} fontSize="11" fill="#5e5e5e">
          {formatForecastNumber(max)}
        </text>
        <text x={4} y={height - pad + 4} fontSize="11" fill="#5e5e5e">
          {formatForecastNumber(min)}
        </text>
        <text x={pad} y={height - 8} fontSize="11" fill="#5e5e5e">
          {formatDisplayDate(firstHist)}
        </text>
        {startFc ? (
          <text x={splitX ?? pad} y={height - 8} fontSize="11" fill="#5e5e5e" textAnchor="middle">
            {formatDisplayDate(startFc)}
          </text>
        ) : null}
        <text x={width - pad} y={height - 8} fontSize="11" fill="#5e5e5e" textAnchor="end">
          {formatDisplayDate(lastFc ?? history.at(-1)?.timestamp ?? null)}
        </text>
      </svg>
      {hover ? (
        <div className="chart-tooltip" role="status">
          <strong>{formatDisplayDate(hover.timestamp)}</strong>
          {hover.kind === "history" ? (
            <span>Historical: {formatForecastNumber(hover.value)}</span>
          ) : (
            <>
              <span>Forecast: {formatForecastNumber(hover.value)}</span>
              <span>
                Interval: {formatForecastNumber(hover.lower)} – {formatForecastNumber(hover.upper)}
              </span>
            </>
          )}
        </div>
      ) : null}
      <figcaption className="legend">
        <span>
          <i className="swatch" aria-hidden="true" /> Historical
        </span>
        <span>
          <i className="swatch swatch-forecast" aria-hidden="true" /> Forecast
        </span>
        <span>
          <i className="swatch swatch-band" aria-hidden="true" /> Prediction interval
        </span>
      </figcaption>
    </figure>
  );
}
