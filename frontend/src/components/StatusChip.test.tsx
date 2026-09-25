import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FreshnessChip, OfficialStateChip, RiskChip } from "./StatusChip";
import { Measurement } from "./Measurement";

describe("data semantics", () => {
  it("labels official JPS states with the Malay term, an icon and JPS attribution", () => {
    render(<OfficialStateChip state="AMARAN" />);
    const chip = screen.getByText("Amaran").parentElement!;
    expect(chip).toHaveAttribute("title", expect.stringContaining("Official JPS state"));
    expect(chip.querySelector("svg")).not.toBeNull();
  });

  it("renders FloodGuard risk as a dashed model-output chip that never uses JPS terms", () => {
    render(<RiskChip level="HIGH" />);
    const chip = screen.getByText("High risk").closest("span")!;
    expect(chip.className).toContain("border-dashed");
    expect(chip).toHaveAttribute("title", expect.stringContaining("Not an official JPS warning"));
    expect(chip.textContent).not.toMatch(/Waspada|Amaran|Bahaya/);
  });

  it("marks freshness as FloodGuard-derived", () => {
    render(<FreshnessChip freshness="STALE" ageMinutes={630} showAge />);
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByText(/10 h 30 min ago/)).toBeInTheDocument();
    expect(screen.getByText("Stale").parentElement).toHaveAttribute("title", expect.stringContaining("FloodGuard-derived"));
  });

  it("shows missing measurements as 'No reading available', never 0", () => {
    render(<Measurement label="Water level" value="—" observationTime={null} freshness="NO_DATA" />);
    expect(screen.getByText("No reading available")).toBeInTheDocument();
    expect(screen.queryByText(/^0/)).toBeNull();
  });

  it("always shows the observation time next to a live value", () => {
    render(<Measurement label="Water level" value={"3.14 m"} observationTime="2026-09-23T17:45:00Z" freshness="FRESH" />);
    expect(screen.getByText(/Obs 24 Sep 2026, 01:45 MYT/)).toBeInTheDocument();
  });
});
