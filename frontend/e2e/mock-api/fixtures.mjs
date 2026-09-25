/**
 * SYNTHETIC TEST FIXTURES — NOT REAL DATA.
 *
 * Used only by Playwright tests and the `npm run dev:mock` preview. Station names, coordinates,
 * readings, thresholds, predictions and alerts are invented. No JPS content is reproduced here
 * (JPS data is PERMISSION REQUIRED; see docs/DATA_LICENSING_AND_ACCESS.md). District names are
 * public administrative geography. Never import this file from src/.
 */

const MIN = 60_000;
const iso = (ms) => new Date(ms).toISOString();
/** Snap to the 5-minute source grid, like JPS listings. */
const grid = (ms) => Math.floor(ms / (5 * MIN)) * 5 * MIN;

const D = {
  TL: "Timur Laut Pulau Pinang",
  BD: "Barat Daya Pulau Pinang",
  SPU: "Seberang Perai Utara",
  SPT: "Seberang Perai Tengah",
  SPS: "Seberang Perai Selatan",
};

// [id, name, district, lat, lon, sensors, scenario]
// scenario: official state for WL (N/W/A/B), or freshness override.
const SITES = [
  ["s01", "Synthetic River A at Bridge 1", D.SPU, 5.462, 100.43, "WL", "B"],
  ["s02", "Synthetic River B at Pump House", D.SPT, 5.372, 100.452, "WL+RF", "A"],
  ["s03", "Synthetic River C at Weir", D.SPT, 5.339, 100.47, "WL", "A"],
  ["s04", "Synthetic River D Upstream", D.TL, 5.402, 100.296, "WL+RF", "W"],
  ["s05", "Synthetic River E at Village", D.BD, 5.35, 100.228, "WL", "W"],
  ["s06", "Synthetic River F Mouth", D.TL, 5.425, 100.33, "WL", "W"],
  ["s07", "Synthetic River G at Estate", D.SPS, 5.2, 100.49, "WL", "N"],
  ["s08", "Synthetic River H at School", D.SPU, 5.52, 100.44, "WL+RF", "N"],
  ["s09", "Synthetic River J Retention Pond", D.TL, 5.39, 100.31, "WL", "STALE"],
  ["s10", "Synthetic River K at Market", D.SPS, 5.15, 100.47, "WL", "NO_DATA"],
  ["s11", "Synthetic Rain Gauge 1", D.TL, 5.41, 100.27, "RF", "FRESH"],
  ["s12", "Synthetic Rain Gauge 2", D.TL, 5.37, 100.3, "RF", "FRESH"],
  ["s13", "Synthetic Rain Gauge 3", D.BD, 5.3, 100.24, "RF", "FRESH"],
  ["s14", "Synthetic Rain Gauge 4", D.BD, 5.33, 100.21, "RF", "DELAYED"],
  ["s15", "Synthetic Rain Gauge 5", D.SPU, 5.49, 100.4, "RF", "FRESH"],
  ["s16", "Synthetic Rain Gauge 6", D.SPU, 5.56, 100.46, "RF", "FRESH"],
  ["s17", "Synthetic Rain Gauge 7", D.SPT, 5.36, 100.43, "RF", "FRESH"],
  ["s18", "Synthetic Rain Gauge 8", D.SPT, 5.31, 100.45, "RF", "STALE"],
  ["s19", "Synthetic Rain Gauge 9", D.SPS, 5.24, 100.5, "RF", "FRESH"],
  ["s20", "Synthetic Rain Gauge 10", D.SPS, 5.18, 100.52, "RF", "FRESH"],
  ["s21", "Synthetic River L at Park", D.SPT, 5.41, 100.49, "WL+RF", "N"],
  ["s22", "Synthetic Rain Gauge 11 (no location)", D.TL, null, null, "RF", "FRESH"],
];

const LEVEL = { N: 1.2, W: 2.62, A: 3.14, B: 3.71 };
const THRESHOLDS = { NORMAL: 0.0, WASPADA: 2.5, AMARAN: 3.0, BAHAYA: 3.5 };
const STATE = { N: "NORMAL", W: "WASPADA", A: "AMARAN", B: "BAHAYA" };
const CONTEXT = {
  N: "1.30 m below Waspada",
  W: "0.12 m above Waspada",
  A: "0.14 m above Amaran",
  B: "0.21 m above Bahaya",
};

function latest(now, scenario, type, i) {
  const age = scenario === "STALE" ? 610 : scenario === "DELAYED" ? 55 : scenario === "NO_DATA" ? null : 10 + (i % 3) * 5;
  const obs = age === null ? null : iso(grid(now - age * MIN));
  const freshness = scenario === "STALE" ? "STALE" : scenario === "DELAYED" ? "DELAYED" : scenario === "NO_DATA" ? "NO_DATA" : "FRESH";
  const base = { observation_time: obs, retrieved_at: iso(now - 2 * MIN), age_minutes: age, freshness };
  if (type === "WATER_LEVEL") {
    const v = scenario in LEVEL ? LEVEL[scenario] : scenario === "STALE" ? 1.05 : null;
    return { ...base, water_level_m: v, water_level_change_1h_m: v === null ? null : scenario === "B" ? 0.18 : scenario === "A" ? 0.09 : -0.02 };
  }
  const rain = scenario === "NO_DATA" ? null : [0, 2.4, 12.6, 0.4, 5.0, 0][i % 6];
  return { ...base, rainfall_1h_mm: rain, rainfall_since_midnight_mm: rain === null ? null : rain * 3 + 1.5 };
}

export function stations(now = Date.now()) {
  return {
    generated_at: iso(now - MIN),
    sites: SITES.map(([id, name, district, lat, lon, sensors, sc], i) => {
      const hasWl = sensors.includes("WL");
      const hasRf = sensors.includes("RF");
      const wlScenario = sc;
      const rfScenario = ["N", "W", "A", "B"].includes(sc) ? "FRESH" : sc;
      const list = [];
      if (hasWl) {
        const evaluable = wlScenario in STATE;
        list.push({
          sensor_id: `${id}-wl`,
          sensor_type: "WATER_LEVEL",
          display_station_id: `SYN${String(i + 1).padStart(3, "0")}WL`,
          latest: latest(now, wlScenario, "WATER_LEVEL", i),
          official_state: evaluable ? STATE[wlScenario] : null,
          threshold_context: evaluable ? CONTEXT[wlScenario] : null,
          thresholds: Object.entries(THRESHOLDS).map(([t, v]) => ({ threshold_type: t, value_m: v, source: "SYNTHETIC", captured_at: iso(now - 3 * 24 * 60 * MIN) })),
        });
      }
      if (hasRf) {
        list.push({
          sensor_id: `${id}-rf`,
          sensor_type: "RAINFALL",
          display_station_id: `SYN${String(i + 1).padStart(3, "0")}RF`,
          latest: latest(now, rfScenario, "RAINFALL", i),
          official_state: null,
          threshold_context: null,
          thresholds: [],
        });
      }
      return {
        site_id: id,
        name,
        district,
        main_basin: hasWl ? "Synthetic Basin" : null,
        sub_basin: hasWl ? `Synthetic Sub-basin ${String.fromCharCode(65 + (i % 4))}` : null,
        latitude: lat,
        longitude: lon,
        coordinate_note: lat === null ? null : "Synthetic coordinates for testing.",
        jps_internal_id: null,
        source_url: null,
        quality_flags: lat === null ? ["MISSING_COORDINATES"] : [],
        sensors: list,
      };
    }),
  };
}

export function station(id, now = Date.now()) {
  return stations(now).sites.find((s) => s.site_id === id) ?? null;
}

/** 5-minute series with one multi-hour gap, a short gap and one source-flagged reading. */
export function observations(sensorId, hours, now = Date.now()) {
  const site = stations(now).sites.flatMap((s) => s.sensors).find((s) => s.sensor_id === sensorId);
  if (!site) return null;
  const isLevel = site.sensor_type === "WATER_LEVEL";
  const end = grid(site.latest?.observation_time ? Date.parse(site.latest.observation_time) : now - 60 * MIN);
  const start = grid(now - hours * 60 * MIN);
  const current = isLevel ? (site.latest?.water_level_m ?? 1.2) : 0;
  const points = [];
  for (let t = start, k = 0; t <= end; t += 5 * MIN, k++) {
    const hoursAgo = (end - t) / (60 * MIN);
    const gap = hoursAgo > 9 && hoursAgo < 12;
    const short = hoursAgo > 4 && hoursAgo < 4.3;
    if (short) continue; // absent rows
    if (gap) {
      points.push({ t: iso(t), value: null, flag: "MISSING" });
      continue;
    }
    const value = isLevel
      ? Math.max(0, current - hoursAgo * 0.04 + 0.08 * Math.sin(k / 9))
      : hoursAgo < 3 && k % 4 === 0
        ? Number((2 + ((k * 7) % 11) * 0.8).toFixed(1))
        : k % 13 === 0
          ? 0.5
          : 0;
    const flagged = isLevel && Math.abs(hoursAgo - 6) < 0.04;
    points.push({ t: iso(t), value: Number(value.toFixed(2)), flag: flagged ? "SOURCE_FLAGGED" : "VALID" });
  }
  return { sensor_id: sensorId, sensor_type: site.sensor_type, unit: isLevel ? "m" : "mm", interval_minutes: 5, from: iso(start), to: iso(now), points };
}

const PRED = {
  s01: ["HIGH", [0.71, 0.82, 0.88], [3.8, 3.9, 4.02]],
  s02: ["HIGH", [0.52, 0.66, 0.74], [3.22, 3.3, 3.41]],
  s03: ["MEDIUM", [0.38, 0.45, 0.51], [3.18, 3.2, 3.24]],
  s04: ["MEDIUM", [0.22, 0.31, 0.4], [2.66, 2.7, 2.77]],
  s05: ["LOW", [0.08, 0.12, 0.17], [2.6, 2.58, 2.55]],
  s06: ["LOW", [0.06, 0.09, 0.14], [2.61, 2.6, 2.59]],
  s07: ["LOW", [0.02, 0.03, 0.05], [1.2, 1.21, 1.22]],
  s08: ["LOW", [0.03, 0.05, 0.08], [1.22, 1.24, 1.27]],
  s21: ["LOW", [0.02, 0.03, 0.04], [1.2, 1.2, 1.21]],
};
const levelFor = (p) => (p < 0.15 ? "LOW" : p < 0.5 ? "MEDIUM" : "HIGH");

export function predictions(now = Date.now()) {
  const generated = iso(grid(now - 3 * MIN));
  const list = Object.entries(PRED).map(([id, [, probs, levels]]) => ({
    site_id: id,
    sensor_id: `${id}-wl`,
    status: id === "s06" ? "DEGRADED" : "AVAILABLE",
    unavailable_reason: null,
    based_on_observation_time: iso(grid(now - 10 * MIN)),
    generated_at: generated,
    input_freshness: id === "s06" ? "DELAYED" : "FRESH",
    input_age_minutes: id === "s06" ? 55 : 10,
    model_version: "synthetic-test-0",
    horizons: [30, 60, 120].map((h, k) => ({ horizon_minutes: h, risk_probability: probs[k], risk_level: levelFor(probs[k]), predicted_water_level_m: levels[k] })),
    contributors:
      id === "s01" || id === "s02"
        ? [
            { label: "Rainfall, last 1 h", direction: "INCREASES" },
            { label: "Water-level rise, last 30 min", direction: "INCREASES" },
            { label: "Rainfall, last 24 h", direction: "INCREASES" },
            { label: "Time since last peak", direction: "DECREASES" },
          ]
        : [],
  }));
  for (const id of ["s09", "s10"]) {
    list.push({
      site_id: id,
      sensor_id: `${id}-wl`,
      status: "UNAVAILABLE",
      unavailable_reason: id === "s09" ? "input data stale" : "no reading available",
      based_on_observation_time: null,
      generated_at: generated,
      input_freshness: id === "s09" ? "STALE" : "NO_DATA",
      input_age_minutes: id === "s09" ? 610 : null,
      model_version: "synthetic-test-0",
      horizons: [],
      contributors: [],
    });
  }
  return {
    model: {
      ready: true,
      model_version: "synthetic-test-0",
      last_run_at: generated,
      next_run_at: iso(grid(now) + 15 * MIN),
      unavailable_reason: null,
      calibration_note: "Synthetic fixture: calibration not evaluated.",
    },
    predictions: list,
  };
}

export function alerts(hours, now = Date.now()) {
  const at = (m) => iso(grid(now - m * MIN));
  const all = [
    { alert_id: "a1", category: "OFFICIAL_THRESHOLD", status: "ACTIVE", created_at: at(15), updated_at: at(10), site_id: "s01", site_name: "Synthetic River A at Bridge 1", district: D.SPU, sensor_type: "WATER_LEVEL", message: "Water level 3.71 m reached the Bahaya threshold (3.50 m).", official_state: "BAHAYA", observed_value: 3.71, observed_unit: "m", observation_time: at(10), threshold_value_m: 3.5, delivery_status: "SENT" },
    { alert_id: "a2", category: "FLOODGUARD_PREDICTION", status: "ACTIVE", created_at: at(20), updated_at: at(5), site_id: "s02", site_name: "Synthetic River B at Pump House", district: D.SPT, sensor_type: "WATER_LEVEL", message: "Model estimates high risk of threshold escalation within 60 min.", risk_level: "HIGH", horizon_minutes: 60, risk_probability: 0.66, model_version: "synthetic-test-0", delivery_status: "SENT" },
    { alert_id: "a3", category: "OFFICIAL_THRESHOLD", status: "ACTIVE", created_at: at(40), updated_at: at(10), site_id: "s02", site_name: "Synthetic River B at Pump House", district: D.SPT, sensor_type: "WATER_LEVEL", message: "Water level 3.14 m reached the Amaran threshold (3.00 m).", official_state: "AMARAN", observed_value: 3.14, observed_unit: "m", observation_time: at(10), threshold_value_m: 3.0 },
    { alert_id: "a4", category: "OFFICIAL_THRESHOLD", status: "ACTIVE", created_at: at(70), updated_at: at(10), site_id: "s03", site_name: "Synthetic River C at Weir", district: D.SPT, sensor_type: "WATER_LEVEL", message: "Water level 3.14 m reached the Amaran threshold (3.00 m).", official_state: "AMARAN", observed_value: 3.14, observed_unit: "m", observation_time: at(10), threshold_value_m: 3.0 },
    { alert_id: "a5", category: "DATA_QUALITY", status: "ACTIVE", created_at: at(190), updated_at: at(190), site_id: "s09", site_name: "Synthetic River J Retention Pond", district: D.TL, sensor_type: "WATER_LEVEL", message: "No observation received for more than 3 hours." },
    { alert_id: "a6", category: "OFFICIAL_THRESHOLD", status: "ACTIVE", created_at: at(210), updated_at: at(10), site_id: "s04", site_name: "Synthetic River D Upstream", district: D.TL, sensor_type: "WATER_LEVEL", message: "Water level 2.62 m reached the Waspada threshold (2.50 m).", official_state: "WASPADA", observed_value: 2.62, observed_unit: "m", observation_time: at(10), threshold_value_m: 2.5 },
    { alert_id: "a7", category: "OFFICIAL_THRESHOLD", status: "RESOLVED", created_at: at(420), updated_at: at(300), site_id: "s07", site_name: "Synthetic River G at Estate", district: D.SPS, sensor_type: "WATER_LEVEL", message: "Water level fell below the Waspada threshold (2.50 m).", official_state: "WASPADA", observed_value: 2.41, observed_unit: "m", observation_time: at(300), threshold_value_m: 2.5 },
    { alert_id: "a8", category: "SYSTEM", status: "RESOLVED", created_at: at(900), updated_at: at(860), site_id: null, site_name: null, district: null, sensor_type: null, message: "Water-level source listing was unreachable for 40 min." },
  ];
  return { from: iso(now - hours * 60 * MIN), to: iso(now), alerts: all.filter((a) => Date.parse(a.created_at) >= now - hours * 60 * MIN) };
}

export function monitoring(now = Date.now()) {
  const s = stations(now).sites.flatMap((x) => x.sensors);
  const count = (type) => ({ expected: s.filter((x) => x.sensor_type === type).length, reporting: s.filter((x) => x.sensor_type === type && ["FRESH", "DELAYED"].includes(x.latest?.freshness)).length });
  const wl = count("WATER_LEVEL");
  const rf = count("RAINFALL");
  return {
    generated_at: iso(now - MIN),
    sources: [
      { source_id: "jps-rf", name: "JPS rainfall listing", sensor_type: "RAINFALL", status: "HEALTHY", last_success_at: iso(now - 2 * MIN), newest_observation_time: iso(grid(now - 10 * MIN)), sensors_expected: rf.expected, sensors_reporting: rf.reporting },
      { source_id: "jps-wl", name: "JPS water-level listing", sensor_type: "WATER_LEVEL", status: "DEGRADED", last_success_at: iso(now - 2 * MIN), newest_observation_time: iso(grid(now - 10 * MIN)), sensors_expected: wl.expected, sensors_reporting: wl.reporting },
    ],
    services: [
      { service_id: "ingestion", name: "Scheduler / ingestion", description: "Polls JPS listings, validates and stores observations", status: "HEALTHY", detail: "Every 15 min", last_success_at: iso(now - 2 * MIN), next_run_at: iso(grid(now) + 15 * MIN) },
      { service_id: "db", name: "Database", description: "Observations, predictions and alerts", status: "HEALTHY", detail: null, last_success_at: iso(now - MIN), next_run_at: null },
      { service_id: "model", name: "Model service", description: "Runs FloodGuard flood-risk predictions", status: "HEALTHY", detail: "Model synthetic-test-0 loaded", last_success_at: iso(now - 3 * MIN), next_run_at: iso(grid(now) + 15 * MIN) },
    ],
    freshness_rule: { fresh_max_minutes: 30, stale_after_minutes: 180 },
    quality_issues: [
      { issue_id: "q1", detected_at: iso(now - 190 * MIN), source: "JPS water level", site_id: "s09", site_name: "Synthetic River J Retention Pond", issue: "No observation for more than 3 hours", status: "OPEN" },
      { issue_id: "q2", detected_at: iso(now - 95 * MIN), source: "JPS water level", site_id: "s10", site_name: "Synthetic River K at Market", issue: "Source returned no usable reading", status: "OPEN" },
      { issue_id: "q3", detected_at: iso(now - 400 * MIN), source: "JPS water level", site_id: "s01", site_name: "Synthetic River A at Bridge 1", issue: "Reading flagged by source (ERROR)", status: "RESOLVED" },
    ],
  };
}

export const health = () => ({ status: "ok" });
export const ready = () => ({ ready: true, checks: [{ name: "model", ok: true, detail: null }, { name: "database", ok: true, detail: null }] });

/** Routes a request path to a fixture body, or null for 404. `scenario=gated` hides unbuilt capabilities. */
export function respond(pathname, searchParams, scenario = "full") {
  const gated = scenario === "gated";
  if (pathname === "/health") return health();
  if (pathname === "/ready") return ready();
  if (pathname === "/api/v1/stations") return stations();
  const m = pathname.match(/^\/api\/v1\/stations\/([^/]+)$/);
  if (m) return station(decodeURIComponent(m[1]));
  if (pathname === "/api/v1/observations") return observations(searchParams.get("sensor_id"), Number(searchParams.get("hours") ?? 24));
  if (gated) return null;
  if (pathname === "/api/v1/predictions") return predictions();
  if (pathname === "/api/v1/alerts") return alerts(Number(searchParams.get("hours") ?? 24));
  if (pathname === "/api/v1/monitoring") return monitoring();
  return null;
}
