import { useSyncExternalStore } from "react";
import { Link } from "react-router";
import { clsx } from "clsx";
import { ArrowRight, CloudOff } from "lucide-react";
import { useStations } from "../../api/client";
import { formatClock } from "../../lib/format";
import { OFFICIAL_STATE, siteOfficialState } from "../../lib/status";

const subscribeOnline = (cb: () => void) => {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
};

/**
 * One slim, sticky line for conditions that affect every page: official Bahaya state, offline,
 * or API unreachable with stale data. Not dismissible while true; routine polling is never announced.
 */
export function StatusStrip() {
  const online = useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
  const stations = useStations();
  const since = stations.dataUpdatedAt ? formatClock(new Date(stations.dataUpdatedAt).toISOString()) : null;
  const bahaya = (stations.data?.sites ?? []).filter((s) => siteOfficialState(s) === "BAHAYA");

  const lines: React.ReactNode[] = [];
  if (bahaya.length > 0) {
    const Icon = OFFICIAL_STATE.BAHAYA.Icon;
    const first = bahaya[0]!;
    lines.push(
      <div key="bahaya" role="alert" className={clsx(stripClass, "border-danger/40 bg-danger-subtle text-danger-text")}>
        <Icon aria-hidden className="size-4 shrink-0" />
        <p className="min-w-0 flex-1 truncate">
          <span className="font-semibold">
            Official JPS state <span lang="ms">Bahaya</span> at {bahaya.length} {bahaya.length === 1 ? "station" : "stations"}
          </span>
          <span className="text-ink-2 max-sm:hidden"> · {bahaya.map((s) => s.name).join(", ")}</span>
        </p>
        <Link to={`/stations/${encodeURIComponent(first.site_id)}`} className="inline-flex shrink-0 items-center gap-1 font-medium text-danger-text hover:underline max-md:min-h-11">
          Open <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </div>,
    );
  }
  if (!online || (stations.error?.kind === "unreachable" && stations.data)) {
    lines.push(
      <div key="conn" role="status" className={clsx(stripClass, "border-line bg-subtle text-ink-2")}>
        <CloudOff aria-hidden className="size-4 shrink-0" />
        <p className="min-w-0 flex-1 truncate">
          <span className="font-medium text-ink">{online ? "Can't reach the FloodGuard service." : "You're offline."}</span>{" "}
          {since ? `Showing data received at ${since}.` : "Data will load when the connection returns."}
        </p>
      </div>,
    );
  }
  if (lines.length === 0) return null;
  return <div className="sticky top-0 z-20 -mx-4 space-y-1 px-4 pt-3 sm:-mx-6 sm:px-6 2xl:-mx-8 2xl:px-8">{lines}</div>;
}

const stripClass = "flex min-h-10 items-center gap-2.5 rounded-control border px-3 py-1.5 text-sm";
