import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { alerts, monitoring, predictions, station, stations } from "../../e2e/mock-api/fixtures.mjs";
import { mockFetch, renderRoute } from "../test/render";
import { axeViolations } from "../test/axe";
import Stations from "./Stations";
import Predictions from "./Predictions";
import StationDetail from "./StationDetail";
import Alerts from "./Alerts";
import DataStatus from "./DataStatus";

// WebGL is unavailable in jsdom; the map is covered by the Playwright run.
vi.mock("../components/map/StationMap", () => ({ default: () => <div data-testid="map" /> }));

afterEach(() => vi.unstubAllGlobals());

// SYNTHETIC fixtures (e2e/mock-api/fixtures.mjs).
const FULL = {
  "/api/v1/stations": stations(),
  "/api/v1/predictions": predictions(),
  "/api/v1/alerts": alerts(24),
  "/api/v1/monitoring": monitoring(),
  "/health": { status: "ok" },
  "/ready": { ready: true, checks: [] },
};

describe("Stations page", () => {
  it("never assigns an official JPS state to rainfall-only stations", async () => {
    mockFetch(FULL);
    renderRoute(<Stations />, "/stations?q=Rain%20Gauge%201", "/stations");
    const table = await screen.findByRole("table");
    const row = within(table).getByText("Synthetic Rain Gauge 1").closest("tr")!;
    expect(within(row).queryByText(/Normal|Waspada|Amaran|Bahaya/)).toBeNull();
    expect(within(row).getByText("JPS publishes no rainfall state")).toBeInTheDocument();
  });

  it("shows a missing water level as a dash, not zero", async () => {
    mockFetch(FULL);
    renderRoute(<Stations />, "/stations?q=River%20K", "/stations");
    const table = await screen.findByRole("table");
    const row = within(table).getByText("Synthetic River K at Market").closest("tr")!;
    expect(within(row).queryByText("0.00")).toBeNull();
    expect(within(row).getByText("No data")).toBeInTheDocument();
  });

  it("offers Clear filters when nothing matches", async () => {
    mockFetch(FULL);
    renderRoute(<Stations />, "/stations?q=zzz", "/stations");
    expect(await screen.findByText("No stations match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("shows an error state with retry when the API is unreachable", async () => {
    mockFetch({ "/api/v1/stations": "NETWORK_ERROR" });
    renderRoute(<Stations />, "/stations", "/stations");
    expect(await screen.findByText("Couldn't load stations", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(0);
  });

  it("has no detectable accessibility violations", async () => {
    mockFetch(FULL);
    const { container } = renderRoute(<Stations />, "/stations", "/stations");
    await screen.findByRole("table");
    expect(await axeViolations(container)).toEqual([]);
  }, 15_000);
});

describe("gated capabilities", () => {
  it("explains that predictions are not available instead of rendering mock values", async () => {
    mockFetch({ "/api/v1/stations": stations() });
    renderRoute(<Predictions />, "/predictions", "/predictions");
    expect(await screen.findByText("Predictions not available yet")).toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).toBeNull();
  });

  it("disables the FloodGuard risk filter when predictions are not available", async () => {
    mockFetch({ "/api/v1/stations": stations() });
    renderRoute(<Stations />, "/stations", "/stations");
    await screen.findByRole("table");
    expect(screen.getByLabelText("FloodGuard risk level")).toBeDisabled();
  });

  it("shows alerts as not available when the endpoint does not exist", async () => {
    mockFetch({});
    renderRoute(<Alerts />, "/alerts", "/alerts");
    expect(await screen.findByText("Alerts not available yet")).toBeInTheDocument();
  });
});

describe("Predictions page", () => {
  it("labels predictions as model output and withholds values for stale input", async () => {
    mockFetch(FULL);
    renderRoute(<Predictions />, "/predictions", "/predictions");
    expect(screen.getByText("Model outputs for situational awareness only. Not official JPS warnings.")).toBeInTheDocument();
    const table = await screen.findByRole("table");
    const stale = within(table).getByText("Synthetic River J Retention Pond").closest("tr")!;
    expect(within(stale).getAllByText("Unavailable")).toHaveLength(3);
    expect(within(stale).queryByText(/\d+%/)).toBeNull();
  });

  it("flags predictions made on delayed input", async () => {
    mockFetch(FULL);
    renderRoute(<Predictions />, "/predictions", "/predictions");
    const table = await screen.findByRole("table");
    const row = within(table).getByText("Synthetic River F Mouth").closest("tr")!;
    expect(within(row).getByText("Delayed")).toBeInTheDocument();
  });
});

describe("Station detail", () => {
  it("separates JPS observations, official thresholds and FloodGuard predictions", async () => {
    mockFetch({ ...FULL, "/api/v1/stations/s01": station("s01") });
    renderRoute(<StationDetail />, "/stations/s01", "/stations/:stationId");
    expect(await screen.findByRole("heading", { level: 1, name: "Synthetic River A at Bridge 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Current observation/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Official JPS thresholds" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "FloodGuard predictions" })).toBeInTheDocument();
    expect(screen.getByText("Model output · Not official warnings")).toBeInTheDocument();
    expect(await screen.findByText(/They explain the model, not the cause of flooding/)).toBeInTheDocument();
  });

  it("shows no thresholds for a rainfall-only station", async () => {
    mockFetch({ ...FULL, "/api/v1/stations/s11": station("s11") });
    renderRoute(<StationDetail />, "/stations/s11", "/stations/:stationId");
    expect(await screen.findByText("JPS publishes no rainfall thresholds for this station.")).toBeInTheDocument();
  });

  it("reports an unknown station as not found", async () => {
    mockFetch(FULL);
    renderRoute(<StationDetail />, "/stations/nope", "/stations/:stationId");
    expect(await screen.findByText("Station not found")).toBeInTheDocument();
  });
});

describe("Alerts and status", () => {
  it("keeps official, FloodGuard, data-quality and system alerts distinct", async () => {
    mockFetch(FULL);
    renderRoute(<Alerts />, "/alerts", "/alerts");
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("JPS official").length).toBeGreaterThan(0);
    expect(within(table).getAllByText("FloodGuard").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /acknowledge|assign|snooze/i })).toBeNull();
  });

  it("does not expose internal error details on the status page", async () => {
    mockFetch(FULL);
    const { container } = renderRoute(<DataStatus />, "/status", "/status");
    await screen.findAllByText("JPS rainfall listing");
    expect(container.textContent).not.toMatch(/Traceback|Exception|postgres:\/\/|mlflow/i);
    expect(await axeViolations(container)).toEqual([]);
  });
});
