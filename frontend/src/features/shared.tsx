import type { ReactNode } from "react";
import { clsx } from "clsx";
import { ChartSpline, Landmark } from "lucide-react";
import { useStations } from "../api/client";
import type { Site } from "../api/types";
import { Select } from "../components/Controls";
import { TimeLabel } from "../components/Measurement";
import { formatMetres, formatMm, formatPercent } from "../lib/format";
import { sensorOf } from "../lib/status";
import { TONE } from "../lib/tone";
import type { Tone } from "../lib/status";
import { districtOptions, useUrlParam } from "../lib/useUrlState";

export function DistrictSelect() {
  const stations = useStations();
  const [district, setDistrict] = useUrlParam("district");
  return (
    <Select
      label="District"
      hideLabel
      value={district}
      options={districtOptions(stations.data?.sites)}
      onChange={setDistrict}
      disabled={!stations.data}
      className="w-48"
    />
  );
}

/** Primary current reading(s) for a site: water level and/or 1 h rainfall, never 0 for missing. */
export function SiteReading({ site, withTime = false }: { site: Site; withTime?: boolean }) {
  const wl = sensorOf(site, "WATER_LEVEL");
  const rf = sensorOf(site, "RAINFALL");
  const time = (wl ?? rf)?.latest?.observation_time;
  return (
    <span className="num inline-flex flex-col leading-tight">
      {wl && <span className="font-medium text-ink">{formatMetres(wl.latest?.water_level_m)}</span>}
      {rf && (
        <span className={wl ? "text-xs text-ink-2" : "font-medium text-ink"}>
          {formatMm(rf.latest?.rainfall_1h_mm)}
          <span className="font-normal text-ink-3"> · 1 h</span>
        </span>
      )}
      {withTime && <TimeLabel iso={time} prefix="Obs" className="text-xs text-ink-3" />}
    </span>
  );
}

/** Horizontal count bar ("Water-level data 21 / 22 · 95%"). */
export function CountBar({ label, part, whole, tone = "info", suffix }: { label: ReactNode; part: number; whole: number; tone?: Tone; suffix?: ReactNode }) {
  const pct = whole > 0 ? Math.round((part / whole) * 100) : 0;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5">
      <span className="truncate text-sm text-ink-2">{label}</span>
      <span className="num text-sm font-medium text-ink">
        {part} / {whole}
        {suffix}
      </span>
      <div
        role="meter"
        aria-label={typeof label === "string" ? label : undefined}
        aria-valuemin={0}
        aria-valuemax={whole}
        aria-valuenow={part}
        aria-valuetext={`${part} of ${whole} (${formatPercent(part, whole)})`}
        className="col-span-2 h-1.5 overflow-hidden rounded-full bg-sunken"
      >
        <div className={clsx("h-full rounded-full", TONE[tone].bar)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** The two-source explainer used wherever JPS data and FloodGuard outputs sit side by side. */
export function SourceExplainer({ layout = "stack" }: { layout?: "stack" | "row" }) {
  return (
    <div className={clsx("grid gap-3", layout === "row" && "sm:grid-cols-2")}>
      <div className="flex gap-3 rounded-control bg-telemetry-subtle p-3">
        <Landmark aria-hidden className="mt-0.5 size-[18px] shrink-0 text-telemetry-text" />
        <div className="text-sm">
          <p className="font-semibold text-ink">JPS observed data</p>
          <p className="text-ink-2">Rainfall and water-level readings and official thresholds, as published by Jabatan Pengairan dan Saliran (JPS).</p>
        </div>
      </div>
      <div className="flex gap-3 rounded-control border border-dashed border-derived/50 bg-derived-subtle p-3">
        <ChartSpline aria-hidden className="mt-0.5 size-[18px] shrink-0 text-derived" />
        <div className="text-sm">
          <p className="font-semibold text-ink">FloodGuard-derived</p>
          <p className="text-ink-2">Freshness labels and model predictions computed by FloodGuard. Not official JPS warnings.</p>
        </div>
      </div>
    </div>
  );
}

/** Compact metric cell: icon, label, value, supporting line. Not a KPI card. */
export function Metric({ icon: Icon, label, value, detail, tone, iconClass }: { icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>; label: string; value: ReactNode; detail?: ReactNode; tone?: Tone; iconClass?: string }) {
  return (
    <div className="flex min-w-0 gap-3 rounded-control border border-line p-3.5">
      <Icon aria-hidden className={clsx("mt-0.5 size-6 shrink-0", iconClass ?? (tone ? TONE[tone].text : "text-telemetry-text"))} />
      <div className="min-w-0">
        <p className="text-sm text-ink-2">{label}</p>
        <p className={clsx("num mt-0.5 text-xl font-semibold", tone ? TONE[tone].text : "text-ink")}>{value}</p>
        {detail && <p className="mt-0.5 text-xs text-ink-3">{detail}</p>}
      </div>
    </div>
  );
}
