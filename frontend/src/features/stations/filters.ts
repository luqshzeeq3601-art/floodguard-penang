import type { SitePrediction, Site } from "../../api/types";
import type { Option } from "../../components/Controls";
import { FRESHNESS, FRESHNESS_STATES, OFFICIAL_STATE, OFFICIAL_STATES, RISK, RISK_LEVELS, siteFreshness, siteOfficialState, siteSensorKind } from "../../lib/status";
import { ALL, matchesDistrict, matchesSearch } from "../../lib/useUrlState";
import { maxRisk } from "../predictions/horizons";

export interface SiteFilters {
  district: string;
  type: string;
  freshness: string;
  state: string;
  risk: string;
  q: string;
}

export const TYPE_OPTIONS: Option[] = [
  { value: ALL, label: "All types" },
  { value: "WATER_LEVEL", label: "Water level" },
  { value: "RAINFALL", label: "Rainfall" },
  { value: "SHARED", label: "Shared (WL + RF)" },
];

export const FRESHNESS_OPTIONS: Option[] = [{ value: ALL, label: "All freshness" }, ...FRESHNESS_STATES.map((f) => ({ value: f, label: FRESHNESS[f].label }))];

export const STATE_OPTIONS: Option[] = [
  { value: ALL, label: "All states" },
  ...OFFICIAL_STATES.map((s) => ({ value: s, label: OFFICIAL_STATE[s].label })),
  { value: "NONE", label: "No official state" },
];

export const RISK_OPTIONS: Option[] = [{ value: ALL, label: "All risk levels" }, ...RISK_LEVELS.map((r) => ({ value: r, label: RISK[r].label })), { value: "NONE", label: "No prediction" }];

/** "Shared" matches only sites with both sensors; "Water level" / "Rainfall" match any site carrying that sensor. */
export function matchesType(site: Site, type: string) {
  if (type === ALL) return true;
  if (type === "SHARED") return siteSensorKind(site) === "SHARED";
  return site.sensors.some((s) => s.sensor_type === type);
}

export function filterSites(sites: Site[], f: Partial<SiteFilters>, predictions?: Map<string, SitePrediction>) {
  return sites.filter((s) => {
    if (f.district && !matchesDistrict(s, f.district)) return false;
    if (f.type && !matchesType(s, f.type)) return false;
    if (f.freshness && f.freshness !== ALL && siteFreshness(s) !== f.freshness) return false;
    if (f.state && f.state !== ALL) {
      const st = siteOfficialState(s);
      if (f.state === "NONE" ? st !== null : st !== f.state) return false;
    }
    if (f.risk && f.risk !== ALL && predictions) {
      const r = maxRisk(predictions.get(s.site_id))?.risk_level ?? null;
      if (f.risk === "NONE" ? r !== null : r !== f.risk) return false;
    }
    if (f.q && !matchesSearch(s, f.q)) return false;
    return true;
  });
}

export const predictionsBySite = (list: SitePrediction[] | undefined) => new Map((list ?? []).map((p) => [p.site_id, p]));
