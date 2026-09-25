import { clsx } from "clsx";
import type { Threshold } from "../api/types";
import { formatMetres } from "../lib/format";
import { OFFICIAL_STATE } from "../lib/status";

const ORDER = ["WASPADA", "AMARAN", "BAHAYA"] as const;
const BAND = { below: "bg-normal/25", WASPADA: "bg-caution/45", AMARAN: "bg-warning/45", BAHAYA: "bg-danger/40" } as const;
const TICK = { WASPADA: "bg-caution", AMARAN: "bg-warning", BAHAYA: "bg-danger" } as const;

/**
 * Linear "level vs official thresholds" meter. Purely positional: it places the API-reported level
 * and the JPS thresholds on one scale. It never decides a state — the official state chip comes
 * from the API. NORMAL is not drawn (JPS does not document its meaning).
 */
export function ThresholdMeter({ value, thresholds, className }: { value: number | null | undefined; thresholds: Threshold[]; className?: string }) {
  const lines = ORDER.map((t) => thresholds.find((x) => x.threshold_type === t)).filter((t): t is Threshold => !!t);
  if (lines.length === 0) return null;

  const hasValue = value !== null && value !== undefined && !Number.isNaN(value);
  const lo0 = Math.min(lines[0]!.value_m, hasValue ? value : Infinity);
  const hi0 = Math.max(lines[lines.length - 1]!.value_m, hasValue ? value : -Infinity);
  const pad = Math.max((hi0 - lo0) * 0.25, 0.25);
  const lo = lo0 - pad;
  const hi = hi0 + pad * 0.6;
  const pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;

  const stops = [lo, ...lines.map((l) => l.value_m), hi];
  const bands = stops.slice(0, -1).map((from, i) => ({
    from,
    to: stops[i + 1]!,
    cls: i === 0 ? BAND.below : BAND[lines[i - 1]!.threshold_type as (typeof ORDER)[number]],
  }));

  const summary = hasValue
    ? `Water level ${formatMetres(value)} on a scale with ${lines.map((l) => `${OFFICIAL_STATE[l.threshold_type].label} ${formatMetres(l.value_m)}`).join(", ")}`
    : "No reading available";

  return (
    <figure className={clsx("select-none", className)}>
      <div role="img" aria-label={summary} className="relative pt-7 pb-20">
        <div className="relative h-2.5 overflow-hidden rounded-full bg-sunken">
          {bands.map((b) => (
            <span key={b.from} className={clsx("absolute inset-y-0", b.cls)} style={{ left: pos(b.from), width: `calc(${pos(b.to)} - ${pos(b.from)})` }} />
          ))}
        </div>
        {lines.map((l, i) => (
          <span key={l.threshold_type} className="absolute top-5 h-[26px] w-0.5" style={{ left: pos(l.value_m) }}>
            <span className={clsx("absolute inset-0 rounded-full", TICK[l.threshold_type as (typeof ORDER)[number]])} />
            {/* Alternate label rows so close thresholds never overlap. */}
            <span className={clsx("absolute top-full -translate-x-1/2 text-center text-xs whitespace-nowrap text-ink-2", i % 2 ? "mt-9" : "mt-1")}>
              <span lang="ms" className="block font-medium text-ink">
                {OFFICIAL_STATE[l.threshold_type].label}
              </span>
              <span className="num">{l.value_m.toFixed(2)}</span>
            </span>
          </span>
        ))}
        {hasValue && (
          <span className="absolute top-0 -translate-x-1/2" style={{ left: pos(value) }}>
            <span className="num block rounded-chip bg-ink px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap text-white">{formatMetres(value)}</span>
            <span className="mx-auto block h-5 w-0.5 bg-ink" />
          </span>
        )}
      </div>
      {!hasValue && <figcaption className="text-sm text-ink-3">No reading available</figcaption>}
    </figure>
  );
}
