import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ObservationSeries, Threshold } from "../../api/types";
import { formatClock, formatDate, formatDateTime, formatMetres, formatMm } from "../../lib/format";
import { OFFICIAL_STATE } from "../../lib/status";
import { token } from "../../lib/tokens";
import { toChartSeries, valueRange, type ChartPoint } from "./series";

export interface ForecastPoint {
  t: string;
  value: number;
}

interface Props {
  series: ObservationSeries;
  /** WATER_LEVEL only. NORMAL is never drawn: its meaning is not documented by JPS. */
  thresholds?: Threshold[];
  forecast?: ForecastPoint[];
  height?: number;
}

const THRESHOLD_TONE = { WASPADA: "caution", AMARAN: "warning", BAHAYA: "danger" } as const;

/** Water-level line or rainfall bars with threshold lines, gap bands and a separated forecast. */
export function ObservationChart({ series, thresholds = [], forecast = [], height = 260 }: Props) {
  const [asTable, setAsTable] = useState(false);
  const isLevel = series.sensor_type === "WATER_LEVEL";
  const fmt = isLevel ? formatMetres : formatMm;

  const { points, gaps, lastObs, domain, lines } = useMemo(() => {
    const { points, gaps } = toChartSeries(series);
    const lastObs = [...points].reverse().find((p) => p.value !== null)?.t ?? null;
    const fc: ChartPoint[] = isLevel && lastObs !== null && forecast.length > 0
      ? forecast.map((f) => ({ t: Date.parse(f.t), value: null, flagged: null, forecast: f.value }))
      : [];
    // Forecast line starts at the last observation so it reads as a continuation, not a new series.
    const anchor = points.find((p) => p.t === lastObs);
    if (anchor && fc.length) anchor.forecast = anchor.value;
    const all = [...points, ...fc].sort((a, b) => a.t - b.t);
    const lines = thresholds.filter((t) => t.threshold_type !== "NORMAL");
    let domain: [number, number] | ["auto", "auto"] = ["auto", "auto"];
    const r = valueRange(all);
    if (isLevel && r) {
      const waspada = lines.find((l) => l.threshold_type === "WASPADA")?.value_m;
      const lo = r[0];
      const hi = Math.max(r[1], waspada ?? r[1]);
      const pad = Math.max((hi - lo) * 0.1, 0.1);
      domain = [Math.floor((lo - pad) * 10) / 10, Math.ceil((hi + pad) * 10) / 10];
    }
    return { points: all, gaps, lastObs, domain, lines };
  }, [series, thresholds, forecast, isLevel]);

  const valid = points.filter((p) => p.value !== null);
  const summary = valid.length
    ? `${isLevel ? "Water level" : "Rainfall"} from ${formatDateTime(series.from)} to ${formatDateTime(series.to)}. ` +
      `Latest ${fmt(valid[valid.length - 1]!.value)}. ${gaps.length} missing-data ${gaps.length === 1 ? "period" : "periods"}.`
    : "No readings available in this range.";
  const multiDay = Date.parse(series.to) - Date.parse(series.from) > 36 * 3_600_000;

  const c = {
    grid: token("chart-grid"),
    axis: token("chart-axis"),
    level: token("chart-level"),
    rain: token("chart-rain"),
    forecast: token("chart-forecast"),
    sunken: token("sunken"),
    ink3: token("ink-3"),
  };

  return (
    <div>
      <div className="mb-2 flex items-start justify-between gap-3">
        <ul aria-label="Chart legend" className="flex min-w-0 flex-1 flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          <li className="inline-flex items-center gap-1.5">
            {isLevel ? <span aria-hidden className="h-0.5 w-4 bg-chart-level" /> : <span aria-hidden className="h-2.5 w-2 bg-chart-rain" />}
            Observed (JPS)
          </li>
          {forecast.length > 0 && isLevel && (
            <li className="inline-flex items-center gap-1.5">
              <span aria-hidden className="w-4 border-t-2 border-dashed border-chart-forecast" />
              Forecast (FloodGuard)
            </li>
          )}
          {lines.map((l) => (
            <li key={l.threshold_type} className="inline-flex items-center gap-1.5">
              <span aria-hidden className={`w-4 border-t-2 border-dotted ${THRESHOLD_BORDER[THRESHOLD_TONE[l.threshold_type as keyof typeof THRESHOLD_TONE]]}`} />
              <span lang="ms">{OFFICIAL_STATE[l.threshold_type].label}</span> {formatMetres(l.value_m)}
            </li>
          ))}
          {gaps.length > 0 && (
            <li className="inline-flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-4 border border-line bg-sunken" />
              No data
            </li>
          )}
        </ul>
        <button type="button" onClick={() => setAsTable((v) => !v)} className="shrink-0 rounded-sm text-xs font-medium whitespace-nowrap text-primary hover:underline max-md:min-h-11">
          {asTable ? "View as chart" : "View as table"}
        </button>
      </div>

      {asTable ? (
        <SeriesTable points={points} fmt={fmt} isLevel={isLevel} />
      ) : (
        <div role="img" aria-label={summary} style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <defs>
                <pattern id="gap-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" fill={c.sunken} />
                  <line x1="0" y1="0" x2="0" y2="6" stroke={c.grid} strokeWidth="2" />
                </pattern>
              </defs>
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={[Date.parse(series.from), forecast.length && isLevel ? "dataMax" : Date.parse(series.to)]}
                tickFormatter={(t: number) => (multiDay ? formatDate(new Date(t).toISOString()).replace(/ \d{4}$/, "") : formatClock(new Date(t).toISOString()))}
                tick={{ fontSize: 11, fill: c.ink3 }}
                stroke={c.axis}
                minTickGap={24}
              />
              <YAxis
                domain={isLevel ? domain : [0, "auto"]}
                tick={{ fontSize: 11, fill: c.ink3 }}
                stroke={c.axis}
                width={44}
                tickFormatter={(v: number) => (isLevel ? v.toFixed(1) : String(v))}
                label={{ value: isLevel ? "m" : "mm", position: "insideTopLeft", offset: 0, dy: -4, fontSize: 11, fill: c.ink3 }}
              />
              {gaps.map((g) => (
                <ReferenceArea key={g.from} x1={g.from} x2={g.to} fill="url(#gap-hatch)" fillOpacity={1} strokeOpacity={0} ifOverflow="hidden" />
              ))}
              {lastObs !== null && forecast.length > 0 && isLevel && (
                <ReferenceArea x1={lastObs} fill={c.sunken} fillOpacity={0.6} ifOverflow="hidden" />
              )}
              {lines.map((l) => (
                <ReferenceLine
                  key={l.threshold_type}
                  y={l.value_m}
                  stroke={token(THRESHOLD_TONE[l.threshold_type as keyof typeof THRESHOLD_TONE])}
                  strokeDasharray="2 3"
                  ifOverflow={l.threshold_type === "WASPADA" ? "extendDomain" : "hidden"}
                  label={{ value: `${OFFICIAL_STATE[l.threshold_type].label} ${l.value_m.toFixed(2)}`, position: "insideTopLeft", fontSize: 11, fill: c.ink3 }}
                />
              ))}
              {lastObs !== null && forecast.length > 0 && isLevel && (
                <ReferenceLine x={lastObs} stroke={c.ink3} label={{ value: "Last obs", position: "insideBottomLeft", fontSize: 11, fill: c.ink3 }} />
              )}
              <Tooltip
                labelFormatter={(t) => formatDateTime(new Date(Number(t)).toISOString())}
                formatter={(v, name) => [v === null || v === undefined ? "No reading" : fmt(Number(v)), String(name)]}
                contentStyle={{ borderRadius: 10, borderColor: c.grid, fontSize: 12 }}
              />
              {isLevel ? (
                <Line dataKey="value" name="Observed (JPS)" stroke={c.level} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} type="linear" />
              ) : (
                <Bar dataKey="value" name="Observed (JPS)" fill={c.rain} fillOpacity={0.85} isAnimationActive={false} maxBarSize={10} />
              )}
              {isLevel && forecast.length > 0 && (
                <Line dataKey="forecast" name="Forecast (FloodGuard)" stroke={c.forecast} strokeWidth={2} strokeDasharray="6 4" dot={{ r: 3 }} connectNulls isAnimationActive={false} type="linear" />
              )}
              <Scatter dataKey="flagged" name="Source-flagged reading" fill="#ffffff" stroke={c.ink3} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

const THRESHOLD_BORDER = { caution: "border-caution", warning: "border-warning", danger: "border-danger" } as const;

function SeriesTable({ points, fmt, isLevel }: { points: ChartPoint[]; fmt: (v: number | null) => string; isLevel: boolean }) {
  const rows = points.filter((p) => p.value !== null || p.flagged !== null || (p.forecast ?? null) !== null).slice(-60).reverse();
  return (
    <div className="max-h-72 overflow-y-auto rounded-control border border-line">
      <table className="w-full text-sm">
        <caption className="sr-only">{isLevel ? "Water level readings" : "Rainfall readings"} (latest 60)</caption>
        <thead className="sticky top-0 bg-subtle text-xs text-ink-3">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-medium">Time (MYT)</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
            <th scope="col" className="px-3 py-2 text-left font-medium">Type</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((p) => (
            <tr key={`${p.t}-${p.forecast ?? ""}`}>
              <td className="num px-3 py-1.5">{formatDateTime(new Date(p.t).toISOString())}</td>
              <td className="num px-3 py-1.5 text-right">{fmt(p.value ?? p.flagged ?? p.forecast ?? null)}</td>
              <td className="px-3 py-1.5 text-ink-2">
                {p.value !== null ? "Observed (JPS)" : p.flagged !== null ? "Source-flagged" : "Forecast (FloodGuard)"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
