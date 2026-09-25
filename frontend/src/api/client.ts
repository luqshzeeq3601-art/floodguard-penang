import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type {
  AlertsResponse,
  MonitoringResponse,
  ObservationSeries,
  PredictionsResponse,
  ReadyResponse,
  Site,
  StationsResponse,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
export const POLL_INTERVAL_MS = Number(import.meta.env.VITE_POLL_INTERVAL_MS) || 60_000;

/** `not_available`: the endpoint does not exist yet (404/501) — the feature is gated, not broken. */
export type ApiErrorKind = "unreachable" | "not_available" | "server";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  constructor(kind: ApiErrorKind, status: number | null) {
    super(kind);
    this.kind = kind;
    this.status = status;
  }
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("unreachable", null);
  }
  if (res.status === 404 || res.status === 501) throw new ApiError("not_available", res.status);
  if (!res.ok) throw new ApiError("server", res.status);
  return (await res.json()) as T;
}

const retry = (count: number, err: unknown) =>
  !(err instanceof ApiError && err.kind === "not_available") && count < 2;

function useApi<T>(key: readonly unknown[], path: string | null, poll = true) {
  return useQuery<T, ApiError>({
    queryKey: key,
    queryFn: ({ signal }) => apiGet<T>(path!, signal),
    enabled: path !== null,
    refetchInterval: poll ? POLL_INTERVAL_MS : false,
    placeholderData: keepPreviousData,
    retry,
  });
}

export const useStations = () => useApi<StationsResponse>(["stations"], "/api/v1/stations");

export const useStation = (siteId: string) =>
  useApi<Site>(["station", siteId], `/api/v1/stations/${encodeURIComponent(siteId)}`);

export const useObservations = (sensorId: string | null, hours: number) =>
  useApi<ObservationSeries>(
    ["observations", sensorId, hours],
    sensorId ? `/api/v1/observations?sensor_id=${encodeURIComponent(sensorId)}&hours=${hours}` : null,
  );

export const usePredictions = () => useApi<PredictionsResponse>(["predictions"], "/api/v1/predictions");

export const useAlerts = (hours: number) =>
  useApi<AlertsResponse>(["alerts", hours], `/api/v1/alerts?hours=${hours}`);

export const useMonitoring = () => useApi<MonitoringResponse>(["monitoring"], "/api/v1/monitoring");

export const useHealth = () => useApi<{ status: string }>(["health"], "/health");

export const useReady = () => useApi<ReadyResponse>(["ready"], "/ready");
