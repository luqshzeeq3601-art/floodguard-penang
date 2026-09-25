/**
 * Frontend view of the planned FloodGuard FastAPI contract (AGENTS.md §18, docs/02_ARCHITECTURE.md,
 * docs/STATION_MASTER_DESIGN.md, docs/18_ALERTING_PLAN.md). The API is not implemented yet; when it
 * is, regenerate these types from its OpenAPI schema and delete anything that drifted.
 *
 * Every status below is computed server-side. The browser only formats and sorts.
 */

export type SensorType = "RAINFALL" | "WATER_LEVEL";

/** Official JPS water-level threshold state ("Tahap Nilai Ambang"), evaluated by the API. */
export type OfficialState = "NORMAL" | "WASPADA" | "AMARAN" | "BAHAYA";

/** FloodGuard-derived freshness (scripts/_jps_common.py fg_live_status). Not a JPS status. */
export type Freshness = "FRESH" | "DELAYED" | "STALE" | "NO_DATA" | "INVALID";

/** FloodGuard model risk category. Deliberately not the JPS vocabulary. */
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type ThresholdType = "NORMAL" | "WASPADA" | "AMARAN" | "BAHAYA";

export interface Threshold {
  threshold_type: ThresholdType;
  value_m: number;
  source: string;
  captured_at: string;
}

export interface LatestObservation {
  /** Source display time, no declared timezone; the API returns it with the assumed +08:00 offset. */
  observation_time: string | null;
  retrieved_at: string;
  age_minutes: number | null;
  freshness: Freshness;
  water_level_m?: number | null;
  /** Change vs one hour earlier, computed by the API when both readings exist. */
  water_level_change_1h_m?: number | null;
  rainfall_1h_mm?: number | null;
  rainfall_since_midnight_mm?: number | null;
}

export interface Sensor {
  sensor_id: string;
  sensor_type: SensorType;
  display_station_id: string | null;
  latest: LatestObservation | null;
  /** WATER_LEVEL only; null when the API cannot evaluate it (stale, no data). */
  official_state: OfficialState | null;
  /** Plain-language distance to the next threshold, e.g. "0.20 m below Waspada". */
  threshold_context: string | null;
  thresholds: Threshold[];
}

export interface Site {
  site_id: string;
  name: string;
  district: string;
  main_basin: string | null;
  sub_basin: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinate_note: string | null;
  jps_internal_id: string | null;
  source_url: string | null;
  quality_flags: string[];
  sensors: Sensor[];
}

export interface StationsResponse {
  generated_at: string;
  sites: Site[];
}

export type PointFlag = "VALID" | "MISSING" | "SOURCE_FLAGGED";

export interface SeriesPoint {
  t: string;
  value: number | null;
  flag: PointFlag;
}

export interface ObservationSeries {
  sensor_id: string;
  sensor_type: SensorType;
  unit: "m" | "mm";
  interval_minutes: number;
  from: string;
  to: string;
  points: SeriesPoint[];
}

export interface HorizonPrediction {
  horizon_minutes: 30 | 60 | 120;
  risk_probability: number;
  risk_level: RiskLevel;
  predicted_water_level_m: number | null;
}

export interface Contributor {
  label: string;
  direction: "INCREASES" | "DECREASES";
}

export type PredictionStatus = "AVAILABLE" | "DEGRADED" | "UNAVAILABLE";

export interface SitePrediction {
  site_id: string;
  sensor_id: string;
  status: PredictionStatus;
  unavailable_reason: string | null;
  based_on_observation_time: string | null;
  generated_at: string;
  input_freshness: Freshness;
  input_age_minutes: number | null;
  model_version: string;
  horizons: HorizonPrediction[];
  contributors: Contributor[];
}

export interface ModelInfo {
  ready: boolean;
  model_version: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  unavailable_reason: string | null;
  calibration_note: string | null;
}

export interface PredictionsResponse {
  model: ModelInfo;
  predictions: SitePrediction[];
}

export type AlertCategory = "OFFICIAL_THRESHOLD" | "FLOODGUARD_PREDICTION" | "DATA_QUALITY" | "SYSTEM";

export interface Alert {
  alert_id: string;
  category: AlertCategory;
  status: "ACTIVE" | "RESOLVED";
  created_at: string;
  updated_at: string;
  site_id: string | null;
  site_name: string | null;
  district: string | null;
  sensor_type: SensorType | null;
  message: string;
  official_state?: OfficialState | null;
  risk_level?: RiskLevel | null;
  horizon_minutes?: number | null;
  risk_probability?: number | null;
  observed_value?: number | null;
  observed_unit?: "m" | "mm" | null;
  observation_time?: string | null;
  threshold_value_m?: number | null;
  model_version?: string | null;
  delivery_status?: "PENDING" | "SENT" | "FAILED" | "RETRIED" | null;
}

export interface AlertsResponse {
  from: string;
  to: string;
  alerts: Alert[];
}

export type ServiceStatus = "HEALTHY" | "DEGRADED" | "UNAVAILABLE";

export interface SourceStatus {
  source_id: string;
  name: string;
  sensor_type: SensorType | null;
  status: ServiceStatus;
  last_success_at: string | null;
  newest_observation_time: string | null;
  sensors_expected: number | null;
  sensors_reporting: number | null;
}

export interface ServiceInfo {
  service_id: string;
  name: string;
  description: string;
  status: ServiceStatus;
  detail: string | null;
  last_success_at: string | null;
  next_run_at: string | null;
}

export interface QualityIssue {
  issue_id: string;
  detected_at: string;
  source: string;
  site_id: string | null;
  site_name: string | null;
  issue: string;
  status: "OPEN" | "RESOLVED";
}

export interface FreshnessRule {
  fresh_max_minutes: number;
  stale_after_minutes: number;
}

export interface MonitoringResponse {
  generated_at: string;
  sources: SourceStatus[];
  services: ServiceInfo[];
  freshness_rule: FreshnessRule;
  quality_issues: QualityIssue[];
}

export interface ReadyResponse {
  ready: boolean;
  checks: { name: string; ok: boolean; detail: string | null }[];
}
