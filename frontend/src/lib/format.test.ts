import { describe, expect, it } from "vitest";
import { formatAge, formatDateTime, formatMetres, formatMm, formatProbability, formatTime } from "./format";

describe("format", () => {
  it("never renders missing measurements as zero", () => {
    expect(formatMetres(null)).toBe("—");
    expect(formatMm(undefined)).toBe("—");
    expect(formatProbability(null)).toBe("—");
  });

  it("keeps real zero rainfall distinct from missing", () => {
    expect(formatMm(0)).toBe("0.0 mm");
  });

  it("formats water level with two decimals and a unit", () => {
    expect(formatMetres(3.1)).toBe("3.10 m");
  });

  it("renders times in Malaysia time with an explicit MYT label", () => {
    expect(formatDateTime("2026-09-23T17:45:00Z")).toBe("24 Sep 2026, 01:45 MYT");
  });

  it("shows only the clock for today and the date otherwise (MYT day boundary)", () => {
    const now = new Date("2026-09-24T02:00:00+08:00");
    expect(formatTime("2026-09-24T01:45:00+08:00", now)).toBe("01:45");
    expect(formatTime("2026-09-23T15:15:00+08:00", now)).toBe("23 Sep, 15:15");
  });

  it("rounds probabilities to whole percent", () => {
    expect(formatProbability(0.826)).toBe("83%");
  });

  it("describes observation age", () => {
    expect(formatAge(630)).toBe("10 h 30 min ago");
    expect(formatAge(null)).toBe("—");
  });
});
