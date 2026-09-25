import { describe, expect, it } from "vitest";
import type { ObservationSeries } from "../../api/types";
import { toChartSeries } from "./series";

const t = (min: number) => new Date(Date.UTC(2026, 8, 24, 0, min)).toISOString();

function series(points: ObservationSeries["points"]): ObservationSeries {
  return { sensor_id: "x", sensor_type: "WATER_LEVEL", unit: "m", interval_minutes: 5, from: t(0), to: t(60), points };
}

describe("toChartSeries", () => {
  it("maps MISSING points to null so lines break instead of plotting sentinels", () => {
    const { points } = toChartSeries(series([
      { t: t(0), value: 1, flag: "VALID" },
      { t: t(5), value: -9999, flag: "MISSING" },
      { t: t(10), value: 1.1, flag: "VALID" },
    ]));
    expect(points.map((p) => p.value)).toEqual([1, null, 1.1]);
  });

  it("emits a gap band and a line break when readings are more than 2 intervals apart", () => {
    const { points, gaps } = toChartSeries(series([
      { t: t(0), value: 1, flag: "VALID" },
      { t: t(30), value: 1.2, flag: "VALID" },
      { t: t(35), value: 1.3, flag: "VALID" },
      { t: t(60), value: 1.4, flag: "VALID" },
    ]));
    expect(gaps).toEqual([
      { from: Date.parse(t(0)), to: Date.parse(t(30)) },
      { from: Date.parse(t(35)), to: Date.parse(t(60)) },
    ]);
    // An explicit null sits between the runs so the line cannot bridge the gap.
    expect(points.filter((p) => p.value === null)).toHaveLength(2);
  });

  it("keeps source-flagged readings out of the observed line", () => {
    const { points } = toChartSeries(series([
      { t: t(0), value: 1, flag: "VALID" },
      { t: t(5), value: 9.9, flag: "SOURCE_FLAGGED" },
    ]));
    expect(points[1]).toMatchObject({ value: null, flagged: 9.9 });
  });

  it("marks the whole range as missing when there is no valid reading", () => {
    const { gaps } = toChartSeries(series([{ t: t(0), value: null, flag: "MISSING" }, { t: t(10), value: null, flag: "MISSING" }]));
    expect(gaps).toHaveLength(1);
  });
});
