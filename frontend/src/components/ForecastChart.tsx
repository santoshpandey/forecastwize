"use client";

import { formatNumber } from "@/lib/format";
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

export function ForecastChart({
  history,
  forecast,
}: {
  history: SeriesPoint[];
  forecast: ForecastResult | null;
}) {
  const histVals = history.map((point) => point.value).filter((value): value is number => value !== null);
  const forecastVals = forecast
    ? [...forecast.yhat, ...forecast.lower, ...forecast.upper]
    : [];
  const all = [...histVals, ...forecastVals];
  if (all.length === 0) {
    return <p className="muted">No series values were returned by the API.</p>;
  }
  const min = Math.min(...all);
  const max = Math.max(...all);
  const width = 720;
  const height = 280;
  const pad = 28;
  const histPath = history
    .map((point, index) => {
      if (point.value === null) {
        return null;
      }
      const command = index === 0 ? "M" : "L";
      return `${command} ${xOf(index, history.length + (forecast?.yhat.length ?? 0), width, pad)} ${yOf(point.value, min, max, height, pad)}`;
    })
    .filter((part): part is string => part !== null)
    .join(" ");

  const lastHistoryIndex = [...history]
    .map((point, index) => (point.value === null ? -1 : index))
    .filter((index) => index >= 0)
    .at(-1);
  const lastHistoryValue =
    lastHistoryIndex !== undefined ? history[lastHistoryIndex]?.value : null;
  const offset = history.length;
  const total = history.length + (forecast?.yhat.length ?? 0);
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

  return (
    <figure>
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Historical series with backend point forecast and prediction interval"
      >
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
        <text x={4} y={pad} fontSize="11" fill="#5e5e5e">
          {formatNumber(max)}
        </text>
        <text x={4} y={height - pad + 4} fontSize="11" fill="#5e5e5e">
          {formatNumber(min)}
        </text>
        <text x={pad} y={height - 6} fontSize="11" fill="#5e5e5e">
          History → forecast (backend series)
        </text>
      </svg>
      <figcaption className="legend">
        <span>
          <i className="swatch" aria-hidden="true" /> Historical (solid)
        </span>
        <span>
          <i className="swatch swatch-forecast" aria-hidden="true" /> Point forecast (dashed)
        </span>
        <span>
          <i className="swatch swatch-band" aria-hidden="true" /> Prediction interval
        </span>
      </figcaption>
    </figure>
  );
}
