import type { ReactNode } from "react";
import { clsx } from "clsx";
import type { LucideIcon } from "lucide-react";
import type { Freshness } from "../api/types";
import { THIN, formatDateTime, formatTime } from "../lib/format";
import { FreshnessChip } from "./StatusChip";

const TZ_NOTE = "Source time assumed to be Malaysia time (UTC+8); JPS does not state a timezone.";

/** `<time>` with the full timestamp and timezone disclosure in its tooltip. */
export function TimeLabel({ iso, prefix, full = false, className }: { iso: string | null | undefined; prefix?: string; full?: boolean; className?: string }) {
  if (!iso) return <span className={clsx("text-ink-3", className)}>{prefix ? `${prefix} —` : "—"}</span>;
  return (
    <time dateTime={iso} title={`${formatDateTime(iso)}. ${TZ_NOTE}`} className={clsx("num", className)}>
      {prefix && `${prefix} `}
      {full ? formatDateTime(iso) : formatTime(iso)}
    </time>
  );
}

interface MeasurementProps {
  label: string;
  /** Pre-formatted value from lib/format (e.g. `5.00 m`), or `—`. */
  value: string;
  icon?: LucideIcon;
  observationTime?: string | null;
  freshness?: Freshness;
  ageMinutes?: number | null;
  detail?: ReactNode;
  size?: "md" | "lg";
}

/** An observed value with its time and freshness. Missing values read "No reading available", never 0. */
export function Measurement({ label, value, icon: Icon, observationTime, freshness, ageMinutes, detail, size = "lg" }: MeasurementProps) {
  const missing = value === "—";
  const [num, unit] = missing ? ["—", ""] : splitUnit(value);
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2 text-sm font-medium text-ink-2">
        {Icon && <Icon aria-hidden className="size-[18px] text-telemetry-text" />}
        {label}
      </div>
      <div className={clsx("num mt-1 font-semibold text-ink", size === "lg" ? "text-metric" : "text-xl")}>
        {num}
        {unit && <span className="ml-1 text-base font-normal text-ink-2">{unit}</span>}
      </div>
      {missing && <p className="text-sm text-ink-3">No reading available</p>}
      {detail && <div className="mt-1 text-sm text-ink-2">{detail}</div>}
      {(observationTime !== undefined || freshness) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
          {observationTime !== undefined && <TimeLabel iso={observationTime} prefix="Obs" full />}
          {freshness && <FreshnessChip freshness={freshness} ageMinutes={ageMinutes} showAge />}
        </div>
      )}
    </div>
  );
}

function splitUnit(v: string): [string, string] {
  const i = v.lastIndexOf(THIN);
  return i > 0 ? [v.slice(0, i), v.slice(i + 1)] : [v, ""];
}
