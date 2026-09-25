import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { Site } from "../api/types";
import type { Option } from "../components/Controls";

export const ALL = "all";

/** Filter state lives in the URL so views are shareable and survive Map/List switches. */
export function useUrlParam(name: string, fallback = ALL): [string, (v: string) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get(name) ?? fallback;
  const set = useCallback(
    (v: string) =>
      setParams(
        (p) => {
          const next = new URLSearchParams(p);
          if (v === fallback) next.delete(name);
          else next.set(name, v);
          return next;
        },
        { replace: true },
      ),
    [name, fallback, setParams],
  );
  return [value, set];
}

/** Sets several params in one navigation (separate setters in one tick would overwrite each other). */
export function useSetParams() {
  const [, setParams] = useSearchParams();
  return useCallback(
    (updates: Record<string, string | null>) =>
      setParams(
        (p) => {
          const next = new URLSearchParams(p);
          for (const [k, v] of Object.entries(updates)) {
            if (v === null || v === ALL || v === "") next.delete(k);
            else next.set(k, v);
          }
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
}

export function districtOptions(sites: Site[] | undefined): Option[] {
  const names = [...new Set((sites ?? []).map((s) => s.district))].sort();
  return [{ value: ALL, label: "All districts" }, ...names.map((d) => ({ value: d, label: d }))];
}

export const matchesDistrict = (site: Site, district: string) => district === ALL || site.district === district;

export const matchesSearch = (site: Site, q: string) => {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [site.name, site.district, site.main_basin, site.sub_basin, ...site.sensors.map((s) => s.display_station_id)]
    .filter(Boolean)
    .some((v) => v!.toLowerCase().includes(needle));
};
