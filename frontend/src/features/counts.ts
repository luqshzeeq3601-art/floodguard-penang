import type { Site } from "../api/types";
import { FRESHNESS, OFFICIAL_STATE } from "../lib/status";

export interface SensorCounts {
  wl: { total: number; reporting: number };
  rf: { total: number; reporting: number };
  /** Water-level sensors whose API-evaluated official state is Waspada or higher. */
  atOrAboveWaspada: number;
  /** Sensors whose API freshness is stale, no data or invalid. */
  notReporting: number;
}

/** Tallies of API-provided statuses. Counting is presentation; no status is derived here. */
export function countSensors(sites: Site[]): SensorCounts {
  const c: SensorCounts = { wl: { total: 0, reporting: 0 }, rf: { total: 0, reporting: 0 }, atOrAboveWaspada: 0, notReporting: 0 };
  for (const site of sites) {
    for (const s of site.sensors) {
      const bucket = s.sensor_type === "WATER_LEVEL" ? c.wl : c.rf;
      bucket.total += 1;
      const reporting = FRESHNESS[s.latest?.freshness ?? "NO_DATA"].reporting;
      if (reporting) bucket.reporting += 1;
      else c.notReporting += 1;
      if (s.official_state && OFFICIAL_STATE[s.official_state].rank > 0) c.atOrAboveWaspada += 1;
    }
  }
  return c;
}
