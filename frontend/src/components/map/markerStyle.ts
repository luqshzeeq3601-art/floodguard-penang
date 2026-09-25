import { clsx } from "clsx";
import type { Site } from "../../api/types";
import { FRESHNESS, OFFICIAL_STATE, SENSOR, SITE_KIND_LABEL, siteFreshness, siteOfficialState, siteSensorKind, type Tone } from "../../lib/status";

export interface MarkerSpec {
  kind: "WATER_LEVEL" | "RAINFALL" | "SHARED";
  /** Fill tone: official JPS state for water level; telemetry for rainfall; neutral when not reporting. */
  fill: Tone | "telemetry";
  size: number;
  /** Not reporting (stale / no data / invalid): hollow dashed marker, official state withheld. */
  muted: boolean;
  label: string;
}

const SIZE_BY_RANK = [14, 16, 18, 20];

/** Shape = sensor type, fill = official JPS state (water level only), dashed = not reporting. */
export function markerSpec(site: Site): MarkerSpec {
  const kind = siteSensorKind(site);
  const freshness = siteFreshness(site);
  const muted = !FRESHNESS[freshness].reporting;
  const state = siteOfficialState(site);
  const hasWl = kind !== "RAINFALL";
  const fill: MarkerSpec["fill"] = muted ? "neutral" : hasWl && state ? OFFICIAL_STATE[state].tone : hasWl ? "neutral" : "telemetry";
  const size = !muted && state ? SIZE_BY_RANK[OFFICIAL_STATE[state].rank]! : kind === "RAINFALL" ? 12 : 14;
  const parts = [site.name, SITE_KIND_LABEL[kind]];
  if (state && !muted) parts.push(`official JPS state ${OFFICIAL_STATE[state].label}`);
  parts.push(`freshness ${FRESHNESS[freshness].label}`);
  return { kind, fill, size, muted, label: parts.join(", ") };
}

/** Class lists per fill, shared by map markers and the legend. */
export const MARKER_FILL: Record<MarkerSpec["fill"], string> = {
  telemetry: "bg-telemetry",
  normal: "bg-normal",
  caution: "bg-caution",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-neutral",
  info: "bg-primary",
};

export const sensorLabel = (kind: MarkerSpec["kind"]) => (kind === "SHARED" ? SITE_KIND_LABEL.SHARED : SENSOR[kind].label);

/** Class string for a marker body; used by the React glyph and by the imperative MapLibre markers. */
export function markerBodyClass(spec: Pick<MarkerSpec, "kind" | "fill" | "muted">) {
  return clsx(
    "relative block border-2 shadow-[0_1px_2px_rgb(16_24_40/0.3)]",
    spec.kind === "RAINFALL" ? "rounded-full" : "rounded-[3px]",
    spec.muted ? "border-dashed border-ink-2 bg-surface" : clsx("border-white", MARKER_FILL[spec.fill]),
  );
}

export const SHARED_BADGE_CLASS = "absolute -top-1 -right-1 size-2 rounded-full border border-white bg-telemetry";

