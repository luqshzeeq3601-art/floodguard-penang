import { lazy, Suspense, useMemo } from "react";
import { List, Map as MapIcon, SearchX, SlidersHorizontal, X } from "lucide-react";
import { usePredictions, useStations } from "../api/client";
import type { Site } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel, PanelHeader } from "../components/Panel";
import { Select, SegmentedControl, type Option } from "../components/Controls";
import { Button } from "../components/Button";
import { Popover } from "../components/Popover";
import { InfoTip } from "../components/InfoTip";
import { OfficialStateChip } from "../components/StatusChip";
import { EmptyState, QueryState, Skeleton, UnavailableFeature } from "../components/States";
import { MapLegend } from "../components/map/MapLegend";
import { MapModeToggle } from "../components/map/MapModeToggle";
import { useMapMode } from "../components/map/useMapMode";
import { SiteReading, SourceExplainer } from "../features/shared";
import { StationsTable } from "../features/stations/StationsTable";
import { SelectedStation } from "../features/stations/SelectedStation";
import { FRESHNESS_OPTIONS, RISK_OPTIONS, STATE_OPTIONS, filterSites, predictionsBySite } from "../features/stations/filters";
import { FRESHNESS, compareByAttention, siteFreshness, siteOfficialState } from "../lib/status";
import { ALL, districtOptions, useSetParams, useUrlParam } from "../lib/useUrlState";

const StationMap = lazy(() => import("../components/map/StationMap"));

const TYPE_SEGMENTS = [
  { value: ALL, label: "All" },
  { value: "WATER_LEVEL", label: "Water level" },
  { value: "RAINFALL", label: "Rainfall" },
  { value: "SHARED", label: "Shared" },
];

const labelOf = (opts: Option[], v: string) => opts.find((o) => o.value === v)?.label ?? v;

export default function LiveMap() {
  const stations = useStations();
  const predictions = usePredictions();
  const [district, setDistrict] = useUrlParam("district");
  const [type, setType] = useUrlParam("type");
  const [freshness, setFreshness] = useUrlParam("freshness");
  const [state, setState] = useUrlParam("state");
  const [risk, setRisk] = useUrlParam("risk");
  const [view, setView] = useUrlParam("view", "map");
  const [selected, setSelected] = useUrlParam("station", "");
  const [mode, setMode] = useMapMode();
  const setParams = useSetParams();

  const byPrediction = useMemo(() => predictionsBySite(predictions.data?.predictions), [predictions.data]);
  const riskAvailable = predictions.data !== undefined;
  const sites = useMemo(
    () => filterSites(stations.data?.sites ?? [], { district, type, freshness, state, risk: riskAvailable ? risk : ALL }, byPrediction).sort(compareByAttention),
    [stations.data, district, type, freshness, state, risk, riskAvailable, byPrediction],
  );
  const located = useMemo(() => sites.filter((s) => s.latitude !== null && s.longitude !== null), [sites]);
  const selectedSite = (stations.data?.sites ?? []).find((s) => s.site_id === selected) ?? null;
  const clear = () => setParams({ district: null, type: null, freshness: null, state: null, risk: null });
  const empty = <EmptyState icon={SearchX} title="No stations match these filters" action={<Button onClick={clear}>Clear filters</Button>} />;

  const chips = [
    district !== ALL && { key: "district", text: district, clear: () => setDistrict(ALL) },
    freshness !== ALL && { key: "freshness", text: `Freshness: ${labelOf(FRESHNESS_OPTIONS, freshness)}`, clear: () => setFreshness(ALL) },
    state !== ALL && { key: "state", text: `Official state: ${labelOf(STATE_OPTIONS, state)}`, clear: () => setState(ALL) },
    riskAvailable && risk !== ALL && { key: "risk", text: `FloodGuard: ${labelOf(RISK_OPTIONS, risk)}`, clear: () => setRisk(ALL) },
  ].filter(Boolean) as { key: string; text: string; clear: () => void }[];
  const moreCount = [freshness, state, riskAvailable ? risk : ALL].filter((v) => v !== ALL).length;

  return (
    <>
      <PageHeader title="Live Map" updatedAt={stations.dataUpdatedAt || undefined} />

      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <Select label="District" hideLabel value={district} onChange={setDistrict} options={districtOptions(stations.data?.sites)} disabled={!stations.data} className="w-48" />
        <SegmentedControl label="Sensor type" value={type} onChange={setType} segments={TYPE_SEGMENTS} className="max-sm:w-full max-sm:overflow-x-auto" />
        <Popover label="Filters" icon={SlidersHorizontal} badge={moreCount} align="left">
          <div className="grid gap-3">
            <Select label="Freshness" value={freshness} onChange={setFreshness} options={FRESHNESS_OPTIONS} />
            <Select label="Official state" value={state} onChange={setState} options={STATE_OPTIONS} />
            <Select
              label="FloodGuard risk"
              value={riskAvailable ? risk : ALL}
              onChange={setRisk}
              options={riskAvailable ? RISK_OPTIONS : [{ value: ALL, label: "Not available" }]}
              disabled={!riskAvailable}
            />
          </div>
        </Popover>
        <div className="ml-auto flex items-center gap-2.5">
          <SegmentedControl
            label="View"
            value={view as "map" | "list"}
            onChange={setView}
            segments={[
              { value: "map", label: "Map", icon: MapIcon },
              { value: "list", label: "List", icon: List },
            ]}
          />
        </div>
      </div>
      {chips.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="num font-medium text-ink-3">
            {sites.length} of {stations.data?.sites.length ?? 0}
          </span>
          {chips.map((c) => (
            <span key={c.key} className="inline-flex h-7 items-center gap-1 rounded-control border border-line bg-surface pr-1 pl-2.5 font-medium text-ink shadow-2xs">
              {c.text}
              <button type="button" aria-label={`Remove filter: ${c.text}`} onClick={c.clear} className="inline-flex size-5 items-center justify-center rounded-sm text-ink-3 hover:bg-hover hover:text-ink">
                <X aria-hidden className="size-3" />
              </button>
            </span>
          ))}
          <button type="button" onClick={clear} className="font-medium text-primary hover:underline">
            Clear all
          </button>
        </div>
      )}

      <QueryState query={stations} what="Stations" loading={<Skeleton className="h-[60vh] rounded-panel" />}>
        {() =>
          view === "list" ? (
            <Panel aria-labelledby="list-title">
              <PanelHeader id="list-title" title="Stations" qualifier={`(${sites.length})`} />
              <StationsTable sites={sites} variant="preview" caption="Stations matching the map filters" empty={empty} selectedId={selected || null} onSelect={setSelected} />
            </Panel>
          ) : (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(340px,400px)]">
              <Panel padded={false} className="relative overflow-hidden" aria-labelledby="map-heading">
                <h2 id="map-heading" className="sr-only">
                  Station map
                </h2>
                <a href="#station-rail" className="sr-only focus:not-sr-only focus:absolute focus:z-20 focus:m-3 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2">
                  Skip map, go to station list
                </a>
                {located.length === 0 ? (
                  sites.length === 0 ? (
                    empty
                  ) : (
                    <UnavailableFeature title="Station locations not available" description="The API returned no verified coordinates for these stations. Use the List view." />
                  )
                ) : (
                  <div className="relative h-[clamp(420px,calc(100dvh-240px),900px)]">
                    <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
                      <StationMap sites={located} selectedId={selected || null} onSelect={setSelected} mode={mode} className="absolute inset-0" />
                    </Suspense>
                    <MapModeToggle mode={mode} onChange={setMode} className="absolute top-3 right-3 z-10 bg-surface shadow-pop" />
                    <div className="absolute bottom-3 left-3 z-10 max-w-[calc(100%-24px)] rounded-control border border-line bg-surface px-3 py-2 shadow-pop">
                      <MapLegend inline />
                    </div>
                  </div>
                )}
              </Panel>
              <Panel as="aside" id="station-rail" variant="raised" aria-label="Selected station" className="xl:max-h-[clamp(420px,calc(100dvh-240px),900px)] xl:overflow-y-auto">
                {selectedSite ? (
                  <SelectedStation
                    site={selectedSite}
                    prediction={byPrediction.get(selectedSite.site_id)}
                    predictionsError={predictions.error}
                    predictionsLoading={predictions.isPending}
                    onClose={() => setSelected("")}
                  />
                ) : (
                  <AttentionRail sites={sites} onSelect={setSelected} />
                )}
              </Panel>
            </div>
          )
        }
      </QueryState>
    </>
  );
}

/** Rail content before a station is picked: the stations most worth looking at, ranked. */
function AttentionRail({ sites, onSelect }: { sites: Site[]; onSelect: (id: string) => void }) {
  const ranked = sites.slice(0, 12);
  return (
    <>
      <PanelHeader
        id="rail-title"
        title="Stations to watch"
        info={
          <InfoTip label="About this list and data sources" align="right">
            <span className="mb-2 block">Ranked by official JPS state, then by FloodGuard freshness. Select one to see its readings and predictions.</span>
            <SourceExplainer />
          </InfoTip>
        }
      />
      {ranked.length === 0 ? (
        <EmptyState title="No stations match these filters" />
      ) : (
        <ol className="stagger-in -mx-2 divide-y divide-line" aria-labelledby="rail-title">
          {ranked.map((s) => {
            const st = siteOfficialState(s);
            return (
              <li key={s.site_id}>
                <button type="button" onClick={() => onSelect(s.site_id)} className="flex w-full items-center gap-3 rounded-control px-2 py-2.5 text-left transition-ui hover:bg-subtle">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">{s.name}</span>
                    <span className="block text-xs text-ink-3">
                      {s.district} · {FRESHNESS[siteFreshness(s)].label}
                    </span>
                  </span>
                  <span className="text-right text-sm">
                    <SiteReading site={s} />
                  </span>
                  {st ? <OfficialStateChip state={st} /> : <span className="w-[74px]" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </>
  );
}
