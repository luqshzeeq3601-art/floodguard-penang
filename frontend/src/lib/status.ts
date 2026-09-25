/** Single mapping from API enums to labels, tones and icons. Components never map statuses themselves. */
import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleSlash,
  Clock3,
  CloudRain,
  Database,
  OctagonAlert,
  Server,
  TriangleAlert,
  Waves,
  ChartSpline,
  type LucideIcon,
} from "lucide-react";
import type {
  AlertCategory,
  Freshness,
  OfficialState,
  RiskLevel,
  SensorType,
  ServiceStatus,
  Site,
} from "../api/types";

export type Tone = "normal" | "caution" | "warning" | "danger" | "neutral" | "info";

interface StatusStyle {
  label: string;
  tone: Tone;
  Icon: LucideIcon;
  description: string;
}

export const OFFICIAL_STATE: Record<OfficialState, StatusStyle & { gloss: string; rank: number }> = {
  NORMAL: { label: "Normal", gloss: "below Waspada", tone: "normal", Icon: CircleCheck, rank: 0, description: "Water level below the Waspada threshold." },
  WASPADA: { label: "Waspada", gloss: "alert", tone: "caution", Icon: CircleAlert, rank: 1, description: "Water level at or above the Waspada (alert) threshold." },
  AMARAN: { label: "Amaran", gloss: "warning", tone: "warning", Icon: TriangleAlert, rank: 2, description: "Water level at or above the Amaran (warning) threshold." },
  BAHAYA: { label: "Bahaya", gloss: "danger", tone: "danger", Icon: OctagonAlert, rank: 3, description: "Water level at or above the Bahaya (danger) threshold." },
};

export const OFFICIAL_STATES: OfficialState[] = ["NORMAL", "WASPADA", "AMARAN", "BAHAYA"];

export const FRESHNESS: Record<Freshness, StatusStyle & { rank: number; reporting: boolean }> = {
  FRESH: { label: "Fresh", tone: "normal", Icon: Clock3, rank: 0, reporting: true, description: "Observation is recent." },
  DELAYED: { label: "Delayed", tone: "caution", Icon: Clock3, rank: 1, reporting: true, description: "Observation is older than expected." },
  STALE: { label: "Stale", tone: "danger", Icon: Clock3, rank: 2, reporting: false, description: "No recent observation." },
  NO_DATA: { label: "No data", tone: "neutral", Icon: CircleDashed, rank: 3, reporting: false, description: "The source returned no usable reading." },
  INVALID: { label: "Invalid time", tone: "neutral", Icon: CircleSlash, rank: 4, reporting: false, description: "The observation time could not be trusted." },
};

export const FRESHNESS_STATES: Freshness[] = ["FRESH", "DELAYED", "STALE", "NO_DATA", "INVALID"];

export const RISK: Record<RiskLevel, StatusStyle & { rank: number }> = {
  LOW: { label: "Low risk", tone: "normal", Icon: CircleCheck, rank: 0, description: "Threshold escalation not expected by the model." },
  MEDIUM: { label: "Medium risk", tone: "caution", Icon: CircleAlert, rank: 1, description: "Moderate modelled chance of escalation. Watch observed levels." },
  HIGH: { label: "High risk", tone: "danger", Icon: TriangleAlert, rank: 2, description: "High modelled chance of threshold escalation within the horizon." },
};

export const RISK_LEVELS: RiskLevel[] = ["HIGH", "MEDIUM", "LOW"];

export const SENSOR: Record<SensorType, { label: string; short: string; Icon: LucideIcon }> = {
  WATER_LEVEL: { label: "Water level", short: "WL", Icon: Waves },
  RAINFALL: { label: "Rainfall", short: "RF", Icon: CloudRain },
};

export const ALERT_CATEGORY: Record<AlertCategory, { label: string; source: "JPS" | "FloodGuard"; Icon: LucideIcon }> = {
  OFFICIAL_THRESHOLD: { label: "Official threshold", source: "JPS", Icon: Waves },
  FLOODGUARD_PREDICTION: { label: "FloodGuard prediction", source: "FloodGuard", Icon: ChartSpline },
  DATA_QUALITY: { label: "Data quality", source: "FloodGuard", Icon: Database },
  SYSTEM: { label: "System", source: "FloodGuard", Icon: Server },
};

export const SERVICE: Record<ServiceStatus, { label: string; tone: Tone }> = {
  HEALTHY: { label: "Healthy", tone: "normal" },
  DEGRADED: { label: "Degraded", tone: "caution" },
  UNAVAILABLE: { label: "Unavailable", tone: "danger" },
};

/** Site-level helpers: pick values the API already computed; never derive new statuses. */
export const sensorOf = (site: Site, type: SensorType) => site.sensors.find((s) => s.sensor_type === type) ?? null;

export const siteSensorKind = (site: Site): "WATER_LEVEL" | "RAINFALL" | "SHARED" =>
  site.sensors.length > 1 ? "SHARED" : (site.sensors[0]?.sensor_type ?? "RAINFALL");

export const SITE_KIND_LABEL = { WATER_LEVEL: "Water level", RAINFALL: "Rainfall", SHARED: "Water level + rainfall" } as const;

export const siteOfficialState = (site: Site): OfficialState | null => sensorOf(site, "WATER_LEVEL")?.official_state ?? null;

/** Worst API-provided freshness across the site's sensors (for sorting and site markers). */
export function siteFreshness(site: Site): Freshness {
  let worst: Freshness = "NO_DATA";
  let rank = -1;
  for (const s of site.sensors) {
    const f = s.latest?.freshness ?? "NO_DATA";
    if (FRESHNESS[f].rank > rank) {
      rank = FRESHNESS[f].rank;
      worst = f;
    }
  }
  return worst;
}

/** Sort key: official state (worst first), then freshness (worst first), then name. */
export function compareByAttention(a: Site, b: Site): number {
  const sa = siteOfficialState(a);
  const sb = siteOfficialState(b);
  const ra = sa ? OFFICIAL_STATE[sa].rank : -1;
  const rb = sb ? OFFICIAL_STATE[sb].rank : -1;
  if (ra !== rb) return rb - ra;
  const fa = FRESHNESS[siteFreshness(a)].rank;
  const fb = FRESHNESS[siteFreshness(b)].rank;
  if (fa !== fb) return fb - fa;
  return a.name.localeCompare(b.name);
}
