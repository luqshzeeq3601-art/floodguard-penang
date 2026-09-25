import type { HorizonPrediction, SitePrediction } from "../../api/types";
import { RISK } from "../../lib/status";

export const HORIZONS = [30, 60, 120] as const;

export const horizonOf = (p: SitePrediction, h: number): HorizonPrediction | undefined => p.horizons.find((x) => x.horizon_minutes === h);

/** Highest model risk across horizons (for sorting / filtering only). */
export function maxRisk(p: SitePrediction | undefined) {
  if (!p || p.status === "UNAVAILABLE") return null;
  return p.horizons.reduce<HorizonPrediction | null>((best, h) => (!best || RISK[h.risk_level].rank > RISK[best.risk_level].rank ? h : best), null);
}

