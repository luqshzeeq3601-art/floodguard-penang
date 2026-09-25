import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Threshold } from "../api/types";
import { ThresholdMeter } from "./ThresholdMeter";

const th = (threshold_type: Threshold["threshold_type"], value_m: number): Threshold => ({ threshold_type, value_m, source: "SYNTHETIC", captured_at: "2026-09-24T00:00:00Z" });
const THRESHOLDS = [th("NORMAL", 0), th("WASPADA", 2.5), th("AMARAN", 3), th("BAHAYA", 3.5)];

describe("ThresholdMeter", () => {
  it("places the level on the threshold scale and describes it for screen readers", () => {
    render(<ThresholdMeter value={3.14} thresholds={THRESHOLDS} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/Water level 3\.14\s+m .*Waspada 2\.50\s+m, Amaran 3\.00\s+m, Bahaya 3\.50\s+m/);
    expect(screen.getByText(/^3\.14\s+m$/)).toBeInTheDocument();
  });

  it("never draws NORMAL (undocumented meaning)", () => {
    render(<ThresholdMeter value={1} thresholds={THRESHOLDS} />);
    expect(screen.queryByText("Normal")).toBeNull();
  });

  it("shows 'No reading available' and no marker when the level is missing", () => {
    render(<ThresholdMeter value={null} thresholds={THRESHOLDS} />);
    expect(screen.getByText("No reading available")).toBeInTheDocument();
    expect(screen.queryByText(/^\d+\.\d+\s+m$/)).toBeNull();
  });

  it("does not infer an official state from the numbers", () => {
    const { container } = render(<ThresholdMeter value={3.7} thresholds={THRESHOLDS} />);
    // Labels appear only as tick names; no state chip or "Bahaya reached" wording is produced.
    expect(container.querySelector("[title^='Official JPS state']")).toBeNull();
    expect(container.textContent).not.toMatch(/reached|above|below/i);
  });

  it("renders nothing without label-eligible thresholds", () => {
    const { container } = render(<ThresholdMeter value={2} thresholds={[th("NORMAL", 0)]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
