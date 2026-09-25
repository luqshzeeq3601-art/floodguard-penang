import type { ObservationSeries } from "../../api/types";

export interface ChartPoint {
  t: number;
  value: number | null;
  /** Readings the source flagged (e.g. severity ERROR): drawn as hollow points, never joined. */
  flagged: number | null;
  forecast?: number | null;
}

export interface Gap {
  from: number;
  to: number;
}

/**
 * Normalises an API series for charting. MISSING values become null so lines break; flagged values
 * move to their own series. A gap band is emitted when valid readings are more than 2× the series
 * interval apart (the API already mapped -9999 / ERROR-only / absent rows to MISSING or omitted them).
 */
export function toChartSeries(series: ObservationSeries): { points: ChartPoint[]; gaps: Gap[] } {
  const maxStep = series.interval_minutes * 2 * 60_000;
  const points: ChartPoint[] = [];
  const gaps: Gap[] = [];
  let lastValid: number | null = null;

  for (const p of [...series.points].sort((a, b) => Date.parse(a.t) - Date.parse(b.t))) {
    const t = Date.parse(p.t);
    if (Number.isNaN(t)) continue;
    const valid = p.flag === "VALID" && p.value !== null;
    if (valid) {
      if (lastValid !== null && t - lastValid > maxStep) {
        gaps.push({ from: lastValid, to: t });
        // Explicit null between runs so the line never bridges the gap.
        points.push({ t: lastValid + 1, value: null, flagged: null });
      }
      lastValid = t;
    }
    points.push({ t, value: valid ? p.value : null, flagged: p.flag === "SOURCE_FLAGGED" ? p.value : null });
  }
  const end = Date.parse(series.to);
  if (lastValid !== null && !Number.isNaN(end) && end - lastValid > maxStep) gaps.push({ from: lastValid, to: end });
  if (lastValid === null && points.length > 0) gaps.push({ from: points[0]!.t, to: points[points.length - 1]!.t });
  return { points, gaps };
}

export function valueRange(points: ChartPoint[]): [number, number] | null {
  const vals = points.flatMap((p) => [p.value, p.flagged, p.forecast ?? null]).filter((v): v is number => v !== null);
  if (vals.length === 0) return null;
  return [Math.min(...vals), Math.max(...vals)];
}
