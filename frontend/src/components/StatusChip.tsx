import { clsx } from "clsx";
import { Landmark, ChartSpline } from "lucide-react";
import type { Freshness, OfficialState, RiskLevel, SensorType, ServiceStatus } from "../api/types";
import { FRESHNESS, OFFICIAL_STATE, RISK, SENSOR, SERVICE, type Tone } from "../lib/status";
import { TONE } from "../lib/tone";
import { formatAge } from "../lib/format";

const chipBase = "inline-flex h-6 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-chip px-2 text-xs font-medium";

/** Official JPS water-level state: solid tint + icon + Malay term. */
export function OfficialStateChip({ state, size = "sm" }: { state: OfficialState; size?: "sm" | "lg" }) {
  const s = OFFICIAL_STATE[state];
  return (
    <span
      className={clsx(chipBase, TONE[s.tone].solidChip, size === "lg" && "h-9 px-3 text-base")}
      title={`Official JPS state: ${s.label} (${s.gloss})`}
    >
      <s.Icon aria-hidden className={size === "lg" ? "size-[18px]" : "size-3.5"} />
      <span lang="ms">{s.label}</span>
    </span>
  );
}

/** FloodGuard model risk: dashed outline so it can never read as an official state. */
export function RiskChip({ level, compact = false, value }: { level: RiskLevel; compact?: boolean; value?: string }) {
  const r = RISK[level];
  return (
    <span
      className={clsx(chipBase, "border border-dashed bg-surface", TONE[r.tone].outlineChip)}
      title={`FloodGuard model output: ${r.label}. Not an official JPS warning.`}
    >
      <r.Icon aria-hidden className="size-3.5" />
      {value && <span className="num">{value} ·</span>}
      {compact ? r.label.replace(" risk", "") : r.label}
    </span>
  );
}

export function StatusDot({ tone, className }: { tone: Tone; className?: string }) {
  return <span aria-hidden className={clsx("inline-block size-2 shrink-0 rounded-full", TONE[tone].dot, className)} />;
}

/** FloodGuard-derived freshness: dot + text; tooltip says who derived it. */
export function FreshnessChip({ freshness, ageMinutes, showAge = false }: { freshness: Freshness; ageMinutes?: number | null; showAge?: boolean }) {
  const f = FRESHNESS[freshness];
  const age = showAge && ageMinutes !== undefined && ageMinutes !== null && freshness !== "INVALID" ? formatAge(ageMinutes) : null;
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm text-ink-2"
      title={`FloodGuard-derived freshness: ${f.label}. ${f.description}`}
    >
      <StatusDot tone={f.tone} />
      <span className="font-medium text-ink">{f.label}</span>
      {age && <span className="num text-ink-3">· {age}</span>}
    </span>
  );
}

export function ServiceStatusLabel({ status }: { status: ServiceStatus }) {
  const s = SERVICE[status];
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-sm font-medium", TONE[s.tone].text)}>
      <StatusDot tone={s.tone} />
      {s.label}
    </span>
  );
}

export function SensorTypeLabel({ type, short = false }: { type: SensorType; short?: boolean }) {
  const s = SENSOR[type];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm text-ink-2" title={s.label}>
      <s.Icon aria-hidden className="size-4 text-telemetry-text" />
      {short ? s.short : s.label}
    </span>
  );
}

/** Source attribution tag: "JPS observed" vs "FloodGuard". */
export function SourceLabel({ source, children }: { source: "JPS" | "FloodGuard"; children?: string }) {
  const jps = source === "JPS";
  const Icon = jps ? Landmark : ChartSpline;
  return (
    <span
      className={clsx(
        "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-chip px-2 text-xs font-medium",
        jps ? "bg-telemetry-subtle text-telemetry-text" : "border border-dashed border-derived bg-derived-subtle text-derived",
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {children ?? (jps ? "JPS observed" : "FloodGuard")}
    </span>
  );
}
