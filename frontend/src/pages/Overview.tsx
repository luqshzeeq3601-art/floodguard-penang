import { lazy, Suspense, useMemo, useState } from "react";
import { Link } from "react-router";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Bell, CloudRain, Info, Map as MapIcon, Waves, WifiOff } from "lucide-react";
import { clsx } from "clsx";
import { useAlerts, useStations } from "../api/client";
import type { Alert, OfficialState, Site } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel, PanelHeader } from "../components/Panel";
import { FilterTabs } from "../components/Controls";
import { Button, TextLink } from "../components/Button";
import { FreshnessChip, OfficialStateChip } from "../components/StatusChip";
import { TimeLabel } from "../components/Measurement";
import { InfoTip } from "../components/InfoTip";
import { EmptyState, QueryState, Skeleton, UnavailableFeature } from "../components/States";
import { MapLegend } from "../components/map/MapLegend";
import { MapModeToggle } from "../components/map/MapModeToggle";
import { useMapMode } from "../components/map/useMapMode";
import { DistrictSelect, SiteReading, SourceExplainer } from "../features/shared";
import { AlertSeverity } from "../features/alerts/AlertsTable";
import { countSensors, type SensorCounts } from "../features/counts";
import { formatPercent, formatSignedMetres } from "../lib/format";
import { ALERT_CATEGORY, FRESHNESS, OFFICIAL_STATE, OFFICIAL_STATES, compareByAttention, sensorOf, siteFreshness, siteOfficialState } from "../lib/status";
import { TONE } from "../lib/tone";
import { matchesDistrict, useUrlParam } from "../lib/useUrlState";

const StationMap = lazy(() => import("../components/map/StationMap"));

export default function Overview() {
  const stations = useStations();
  const [district] = useUrlParam("district");
  const sites = useMemo(() => (stations.data?.sites ?? []).filter((s) => matchesDistrict(s, district)), [stations.data, district]);
  const counts = useMemo(() => countSensors(sites), [sites]);

  return (
    <>
      <PageHeader title="Overview" updatedAt={stations.dataUpdatedAt || undefined}>
        <DistrictSelect />
      </PageHeader>
      <QueryState query={stations} what="Stations" loading={<OverviewSkeleton />}>
        {() => (
          <div className="fade-in grid gap-5 xl:grid-cols-12">
            <SituationHero sites={sites} />
            <HealthStrip counts={counts} />
            <NeedsAttention sites={sites} />
            <RecentAlerts />
          </div>
        )}
      </QueryState>
    </>
  );
}

function stateCounts(sites: Site[]) {
  const c: Record<OfficialState, number> = { NORMAL: 0, WASPADA: 0, AMARAN: 0, BAHAYA: 0 };
  for (const s of sites) {
    const st = siteOfficialState(s);
    if (st) c[st] += 1;
  }
  return c;
}

/** "1 station at Bahaya, 2 at Amaran and 3 at Waspada." — built from API states only. */
function situationSentence(c: Record<OfficialState, number>) {
  const parts = (["BAHAYA", "AMARAN", "WASPADA"] as const).filter((s) => c[s] > 0).map((s, i) => `${c[s]}${i === 0 ? (c[s] === 1 ? " station" : " stations") : ""} at ${OFFICIAL_STATE[s].label}`);
  if (parts.length === 0) return "All evaluated stations are currently below threshold.";
  const last = parts.pop()!;
  return `${parts.length ? `${parts.join(", ")} and ${last}` : last}.`;
}

function SituationHero({ sites }: { sites: Site[] }) {
  const [mode, setMode] = useMapMode();
  const [selected, setSelected] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(false);
  const counts = useMemo(() => stateCounts(sites), [sites]);
  const evaluated = OFFICIAL_STATES.reduce((n, s) => n + counts[s], 0);
  const top = [...OFFICIAL_STATES].reverse().find((s) => counts[s] > 0) ?? null;
  const located = useMemo(() => sites.filter((s) => s.latitude !== null && s.longitude !== null), [sites]);
  const sel = sites.find((s) => s.site_id === selected) ?? null;

  return (
    <Panel variant="raised" padded={false} className="overflow-hidden xl:col-span-12" aria-labelledby="situation-title">
      <div className="grid lg:grid-cols-[minmax(300px,5fr)_7fr]">
        <div className="flex flex-col gap-5 p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5">
              <h2 id="situation-title" className="text-lg font-semibold text-ink">
                Current Situation
              </h2>
              <InfoTip label="About official JPS states">
                <span className="block">
                  <span lang="ms">Normal, Waspada, Amaran</span> and <span lang="ms">Bahaya</span> are official JPS water-level thresholds.
                </span>
              </InfoTip>
            </div>
            <span className="rounded-chip bg-subtle px-2.5 py-1 text-xs font-medium text-ink-3">
              Pulau Pinang
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-control bg-subtle p-3.5 border border-line/60">
            {top ? <OfficialStateChip state={top} size="lg" /> : <span className="text-sm font-medium text-ink-2">No water-level alert</span>}
            <p className="min-w-0 flex-1 text-sm font-medium text-ink">{situationSentence(counts)}</p>
          </div>

          <div>
            <div className="flex items-center justify-between text-xs font-medium text-ink-2">
              <span>Threshold Status</span>
              <span className="num text-ink-3">{evaluated} evaluated</span>
            </div>
            <div role="img" aria-label={OFFICIAL_STATES.map((s) => `${OFFICIAL_STATE[s].label} ${counts[s]}`).join(", ")} className="mt-2 flex h-2 gap-0.5 overflow-hidden rounded-full bg-sunken">
              {[...OFFICIAL_STATES].reverse().map((s) =>
                counts[s] > 0 ? <span key={s} className={TONE[OFFICIAL_STATE[s].tone].bar} style={{ width: `${(counts[s] / Math.max(evaluated, 1)) * 100}%` }} /> : null,
              )}
            </div>
            <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
              {[...OFFICIAL_STATES].reverse().map((s) => (
                <li key={s} className="inline-flex items-center gap-1.5">
                  <span aria-hidden className={clsx("size-2 rounded-full", TONE[OFFICIAL_STATE[s].tone].dot)} />
                  <span className="num font-semibold text-ink">{counts[s]}</span>
                  <span lang="ms">{OFFICIAL_STATE[s].label}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-auto flex flex-wrap items-center gap-3 pt-2">
            <TextLink to="/map" iconEnd={ArrowRight}>
              Open live map
            </TextLink>
            {located.length > 0 && (
              <Button size="sm" icon={MapIcon} className="md:hidden" aria-expanded={showMap} onClick={() => setShowMap((v) => !v)}>
                {showMap ? "Hide map" : "Show map"}
              </Button>
            )}
          </div>
        </div>

        <div className={clsx("relative min-h-[320px] border-line max-lg:border-t lg:min-h-[440px] lg:border-l", !showMap && "max-md:hidden")}>
          {located.length === 0 ? (
            <UnavailableFeature title="Station locations not available" description="The API returned no verified coordinates. Use the station list instead." />
          ) : (
            <>
              <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
                <StationMap sites={located} selectedId={selected} onSelect={setSelected} mode={mode} className="absolute inset-0" />
              </Suspense>
              <MapModeToggle mode={mode} onChange={setMode} className="absolute top-3 right-3 z-10 bg-surface shadow-pop" />
              <div className="absolute bottom-3 left-3 z-10 max-w-[calc(100%-24px)] rounded-control border border-line bg-surface px-3 py-2 shadow-pop">
                <MapLegend inline />
              </div>
              {sel && (
                <div className="scale-in absolute top-14 right-3 left-3 z-10 rounded-control border border-line bg-surface p-3 shadow-overlay sm:left-auto sm:w-72">
                  <Link to={`/stations/${encodeURIComponent(sel.site_id)}`} className="font-semibold text-ink hover:text-primary hover:underline">
                    {sel.name}
                  </Link>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                    <SiteReading site={sel} />
                    {siteOfficialState(sel) && <OfficialStateChip state={siteOfficialState(sel)!} />}
                  </div>
                  <p className="mt-1 text-xs text-ink-3">
                    <TimeLabel iso={sel.sensors[0]?.latest?.observation_time} prefix="Obs" full /> · {FRESHNESS[siteFreshness(sel)].label}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}

function HealthStrip({ counts }: { counts: SensorCounts }) {
  const alerts = useAlerts(24);
  const active = alerts.data?.alerts.filter((a) => a.status === "ACTIVE" && a.category === "FLOODGUARD_PREDICTION").length;
  const cells = [
    { icon: Waves, label: "WL Reporting", value: `${counts.wl.reporting} / ${counts.wl.total}`, detail: formatPercent(counts.wl.reporting, counts.wl.total), iconClass: "text-telemetry-text" },
    { icon: CloudRain, label: "RF Reporting", value: `${counts.rf.reporting} / ${counts.rf.total}`, detail: formatPercent(counts.rf.reporting, counts.rf.total), iconClass: "text-telemetry-text" },
    { icon: WifiOff, label: "Offline", value: String(counts.notReporting), detail: "Stale / No data", iconClass: "text-ink-3" },
    {
      icon: Bell,
      label: "Active Alerts",
      value: alerts.data ? String(active) : "—",
      detail: alerts.error?.kind === "not_available" ? "Not available" : alerts.data ? "Model output" : alerts.isPending ? "Loading" : "Unavailable",
      iconClass: "text-derived",
    },
  ];
  return (
    <Panel padded={false} className="max-md:order-2 xl:col-span-12" aria-label="Monitoring health">
      <ul className="stagger-in grid divide-line sm:grid-cols-2 sm:divide-x xl:grid-cols-4 max-sm:divide-y">
        {cells.map((c) => (
          <li key={c.label} className="flex items-center gap-3.5 px-5 py-4 transition-ui hover:bg-subtle/50">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-control bg-subtle">
              <c.icon aria-hidden className={clsx("size-5", c.iconClass)} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-ink-3">{c.label}</p>
              <p className="flex items-baseline gap-2">
                <span className="num text-xl font-bold text-ink">{c.value}</span>
                <span className="num text-xs text-ink-3">{c.detail}</span>
              </p>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

type AttentionTab = "all" | "BAHAYA" | "AMARAN" | "WASPADA";

function ChangeArrow({ delta }: { delta: number | null | undefined }) {
  if (delta === null || delta === undefined) return null;
  const Icon = delta > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="num inline-flex items-center gap-0.5 text-xs text-ink-2" title="Change vs one hour earlier (from the API)">
      {delta !== 0 && <Icon aria-hidden className="size-3.5" />}
      {formatSignedMetres(delta)}
      <span className="sr-only"> in the last hour</span>
    </span>
  );
}

function NeedsAttention({ sites }: { sites: Site[] }) {
  const [tab, setTab] = useState<AttentionTab>("all");
  const flagged = useMemo(() => sites.filter((s) => { const st = siteOfficialState(s); return st ? OFFICIAL_STATE[st].rank > 0 : false; }).sort(compareByAttention), [sites]);
  const rows = tab === "all" ? flagged : flagged.filter((s) => siteOfficialState(s) === tab);
  const count = (st: OfficialState) => flagged.filter((s) => siteOfficialState(s) === st).length;

  return (
    <Panel className="max-md:order-1 xl:col-span-7" aria-labelledby="attention-title">
      <PanelHeader
        id="attention-title"
        title="Needs attention"
        info={<InfoTip label="How this list is ranked">Water-level stations at or above Waspada, ranked by official JPS state, then by FloodGuard freshness.</InfoTip>}
        actions={<TextLink to="/stations" iconEnd={ArrowRight}>All stations</TextLink>}
      />
      <FilterTabs
        label="Filter by official state"
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "all", label: "All", count: flagged.length },
          ...(["BAHAYA", "AMARAN", "WASPADA"] as const).map((st) => ({ value: st as AttentionTab, label: OFFICIAL_STATE[st].label, count: count(st) })),
        ]}
      />
      {rows.length === 0 ? (
        <EmptyState icon={Info} title={tab === "all" ? "No water-level station is at or above Waspada" : `No station at ${OFFICIAL_STATE[tab as OfficialState].label}`} />
      ) : (
        <ol className="stagger-in mt-3 divide-y divide-line">
          {rows.map((s, i) => {
            const wl = sensorOf(s, "WATER_LEVEL");
            return (
              <li key={s.site_id} className="relative grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-control px-2 py-3 transition-ui hover:bg-subtle sm:grid-cols-[1.5rem_minmax(0,1fr)_auto_auto_auto]">
                <span className="num text-sm text-ink-3">{i + 1}</span>
                <div className="min-w-0">
                  {/* Stretched link: the whole row opens the station. */}
                  <Link to={`/stations/${encodeURIComponent(s.site_id)}`} className="font-medium text-ink after:absolute after:inset-0 after:rounded-control hover:text-primary">
                    {s.name}
                  </Link>
                  <p className="truncate text-xs text-ink-3">{s.district}</p>
                </div>
                <div className="text-right">
                  <SiteReading site={s} />
                  <div>
                    <ChangeArrow delta={wl?.latest?.water_level_change_1h_m} />
                  </div>
                </div>
                <div className="max-sm:col-start-2 max-sm:row-start-2">{siteOfficialState(s) && <OfficialStateChip state={siteOfficialState(s)!} />}</div>
                <div className="flex flex-col items-end gap-0.5 text-sm max-sm:col-start-3 max-sm:row-start-2">
                  <TimeLabel iso={wl?.latest?.observation_time} className="text-ink-2" />
                  <FreshnessChip freshness={siteFreshness(s)} />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

function RecentAlerts() {
  const alerts = useAlerts(24);
  return (
    <Panel className="max-md:order-3 xl:col-span-5" aria-labelledby="recent-alerts-title">
      <PanelHeader
        id="recent-alerts-title"
        title="Recent alerts"
        qualifier="(24 h)"
        info={
          <InfoTip label="About alert sources">
            <SourceExplainer />
          </InfoTip>
        }
        actions={<TextLink to="/alerts" iconEnd={ArrowRight}>View all</TextLink>}
      />
      <QueryState query={alerts} what="Alerts">
        {(d) =>
          d.alerts.length === 0 ? (
            <EmptyState title="No alerts in the last 24 hours" />
          ) : (
            <ul className="stagger-in divide-y divide-line">
              {[...d.alerts]
                .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
                .slice(0, 6)
                .map((a) => (
                  <AlertRow key={a.alert_id} alert={a} />
                ))}
            </ul>
          )
        }
      </QueryState>
    </Panel>
  );
}

function AlertRow({ alert: a }: { alert: Alert }) {
  const c = ALERT_CATEGORY[a.category];
  return (
    <li className="relative flex items-start gap-3 rounded-control px-2 py-3 transition-ui hover:bg-subtle">
      <div className="w-24 shrink-0 pt-0.5">
        <AlertSeverity alert={a} />
      </div>
      <div className="min-w-0 flex-1">
        <Link to={`/alerts?alert=${encodeURIComponent(a.alert_id)}`} className="block truncate text-sm font-medium text-ink after:absolute after:inset-0 after:rounded-control hover:text-primary">
          {a.site_name ?? c.label}
        </Link>
        <p className="line-clamp-1 text-sm text-ink-2">{a.message}</p>
        <p className="text-xs text-ink-3">{c.source === "JPS" ? "JPS official" : "FloodGuard"}</p>
      </div>
      <TimeLabel iso={a.created_at} className="shrink-0 text-xs text-ink-3" />
    </li>
  );
}

function OverviewSkeleton() {
  return (
    <div aria-busy="true" className="grid gap-5 xl:grid-cols-12">
      <span className="sr-only">Loading overview</span>
      <Skeleton className="h-[440px] rounded-panel xl:col-span-12" />
      <Skeleton className="h-20 rounded-panel xl:col-span-12" />
      <Skeleton className="h-96 rounded-panel xl:col-span-7" />
      <Skeleton className="h-96 rounded-panel xl:col-span-5" />
    </div>
  );
}
