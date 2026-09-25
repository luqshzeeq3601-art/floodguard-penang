import type { AlertsResponse, MonitoringResponse, ObservationSeries, PredictionsResponse, ReadyResponse, Site, StationsResponse } from "../../src/api/types";

export function stations(now?: number): StationsResponse;
export function station(id: string, now?: number): Site | null;
export function observations(sensorId: string, hours: number, now?: number): ObservationSeries | null;
export function predictions(now?: number): PredictionsResponse;
export function alerts(hours: number, now?: number): AlertsResponse;
export function monitoring(now?: number): MonitoringResponse;
export function health(): { status: string };
export function ready(): ReadyResponse;
export function respond(pathname: string, searchParams: URLSearchParams, scenario?: "full" | "gated"): unknown;
