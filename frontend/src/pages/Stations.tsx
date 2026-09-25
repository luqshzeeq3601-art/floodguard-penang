import { useMemo } from "react";
import { BookOpen, CloudRain, Layers, LayoutGrid, SearchX, Waves } from "lucide-react";
import { useMonitoring, usePredictions, useStations } from "../api/client";
import type { Site } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel, PanelHeader } from "../components/Panel";
import { FilterTabs, SearchInput, Select } from "../components/Controls";
import { Button } from "../components/Button";
import { Popover } from "../components/Popover";
import { InfoTip } from "../components/InfoTip";
import { EmptyState, QueryState, SkeletonRows } from "../components/States";
import { FreshnessChip, OfficialStateChip } from "../components/StatusChip";
import { StationsTable } from "../features/stations/StationsTable";
import { FRESHNESS_OPTIONS, RISK_OPTIONS, filterSites, matchesType, predictionsBySite } from "../features/stations/filters";
import { formatPercent } from "../lib/format";
import { freshnessRuleText } from "../features/freshnessRule";
import { FRESHNESS, FRESHNESS_STATES, OFFICIAL_STATE, OFFICIAL_STATES, compareByAttention, siteFreshness } from "../lib/status";
import { TONE } from "../lib/tone";
import { ALL, districtOptions, useSetParams, useUrlParam } from "../lib/useUrlState";

export default function Stations() {
  const stations = useStations();
  const predictions = usePredictions();
  const [district, setDistrict] = useUrlParam("district");
  const [type, setType] = useUrlParam("type");
  const [freshness, setFreshness] = useUrlParam("freshness");
  const [risk, setRisk] = useUrlParam("risk");
  const [q, setQ] = useUrlParam("q", "");

  const all = useMemo(() => stations.data?.sites ?? [], [stations.data]);
  const byPrediction = useMemo(() => predictionsBySite(predictions.data?.predictions), [predictions.data]);
  const riskAvailable = predictions.data !== undefined;
  const base = useMemo(() => filterSites(all, { district, freshness, risk: riskAvailable ? risk : ALL, q }, byPrediction), [all, district, freshness, risk, riskAvailable, q, byPrediction]);
  const rows = useMemo(() => base.filter((s) => matchesType(s, type)).sort(compareByAttention), [base, type]);
  const typeCount = (t: string) => base.filter((s) => matchesType(s, t)).length;
  const monitoring = useMonitoring();
  const setParams = useSetParams();
  const clear = () => setParams({ district: null, type: null, freshness: null, risk: null, q: null });

  return (
    <>
      <PageHeader title="Stations" updatedAt={stations.dataUpdatedAt || undefined} />
      <div className="grid gap-5 2xl:grid-cols-12">
        <Panel className="min-w-0 2xl:col-span-9" aria-label="Station table">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <FilterTabs
              label="Sensor type"
              value={type}
              onChange={setType}
              tabs={[
                { value: ALL, label: "All", icon: LayoutGrid, count: typeCount(ALL) },
                { value: "RAINFALL", label: "Rainfall", icon: CloudRain, count: typeCount("RAINFALL") },
                { value: "WATER_LEVEL", label: "Water level", icon: Waves, count: typeCount("WATER_LEVEL") },
                { value: "SHARED", label: "Shared", icon: Layers, count: typeCount("SHARED") },
              ]}
            />
            <SearchInput label="Search stations" placeholder="Search stations, districts, basins" value={q} onChange={setQ} className="w-full sm:w-72" />
          </div>
          <div className="mt-3 mb-4 flex flex-wrap items-center gap-2.5">
            <Select label="District" hideLabel value={district} onChange={setDistrict} options={districtOptions(all)} disabled={!stations.data} className="w-52" />
            <Select label="Freshness" hideLabel value={freshness} onChange={setFreshness} options={FRESHNESS_OPTIONS} className="w-44" />
            <Select
              label="FloodGuard risk level"
              hideLabel
              value={riskAvailable ? risk : ALL}
              onChange={setRisk}
              options={riskAvailable ? RISK_OPTIONS : [{ value: ALL, label: "Risk: not available" }]}
              disabled={!riskAvailable}
              className="w-48"
            />
            <div className="ml-auto">
              <Popover label="Legend" icon={BookOpen}>
                <StatusGuide rule={monitoring.data?.freshness_rule} />
              </Popover>
            </div>
          </div>
          <QueryState query={stations} what="Stations" loading={<SkeletonRows rows={10} label="Loading stations" />}>
            {() => (
              <StationsTable
                sites={rows}
                variant="full"
                caption="Pulau Pinang JPS stations, ranked by official state then freshness"
                pageSize={25}
                empty={<EmptyState icon={SearchX} title="No stations match these filters" action={<Button onClick={clear}>Clear filters</Button>} />}
              />
            )}
          </QueryState>
        </Panel>
        <InsightRail sites={all} />
      </div>
    </>
  );
}

function InsightRail({ sites }: { sites: Site[] }) {
  const districts = [...new Set(sites.map((s) => s.district))]
    .map((d) => ({ d, n: sites.filter((s) => s.district === d).length }))
    .sort((a, b) => b.n - a.n);
  const maxD = Math.max(1, ...districts.map((x) => x.n));
  const fresh = FRESHNESS_STATES.map((f) => ({ f, n: sites.filter((s) => siteFreshness(s) === f).length })).filter((x) => x.n > 0 || x.f !== "INVALID");

  if (sites.length === 0) return <div className="2xl:col-span-3" />;
  return (
    <div className="grid content-start gap-5 md:grid-cols-2 2xl:col-span-3 2xl:grid-cols-1">
      <Panel aria-labelledby="freshness-dist">
        <PanelHeader
          id="freshness-dist"
          title="Freshness"
          qualifier={`(${sites.length} sites)`}
          info={<InfoTip label="About freshness" align="right">Worst FloodGuard-derived freshness across each site's sensors. Not a JPS status.</InfoTip>}
        />
        <StackedBar parts={fresh.map((x) => ({ n: x.n, cls: TONE[FRESHNESS[x.f].tone].bar, label: FRESHNESS[x.f].label }))} total={sites.length} />
        <ul className="mt-3 space-y-1.5 text-sm">
          {fresh.map((x) => (
            <li key={x.f} className="flex items-center justify-between gap-2">
              <FreshnessChip freshness={x.f} />
              <span className="num font-medium text-ink">
                {x.n} <span className="font-normal text-ink-3">({formatPercent(x.n, sites.length)})</span>
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel aria-labelledby="by-district">
        <PanelHeader id="by-district" title="Stations by district" />
        <ul className="space-y-2.5 text-sm">
          {districts.map(({ d, n }) => (
            <li key={d} className="grid grid-cols-[minmax(0,1fr)_minmax(60px,40%)_2ch] items-center gap-3">
              <span className="truncate text-ink-2" title={d}>
                {d}
              </span>
              <span aria-hidden className="h-1.5 rounded-full bg-sunken">
                <span className="block h-full rounded-full bg-primary" style={{ width: `${(n / maxD) * 100}%` }} />
              </span>
              <span className="num text-right font-medium text-ink">{n}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function StatusGuide({ rule }: { rule?: { fresh_max_minutes: number; stale_after_minutes: number } }) {
  return (
    <div className="text-sm">
      <h3 className="mb-2 text-xs font-medium text-ink-3">Official JPS state (water level only)</h3>
      <ul className="space-y-2">
        {OFFICIAL_STATES.map((s) => (
          <li key={s} className="grid grid-cols-[88px_1fr] items-start gap-2">
            <OfficialStateChip state={s} />
            <span className="text-ink-2">{OFFICIAL_STATE[s].description}</span>
          </li>
        ))}
      </ul>
      <h3 className="mt-4 mb-2 border-t border-line pt-4 text-xs font-medium text-ink-3">FloodGuard freshness</h3>
      <ul className="space-y-2">
        {FRESHNESS_STATES.map((f) => (
          <li key={f} className="grid grid-cols-[88px_1fr] items-start gap-2">
            <FreshnessChip freshness={f} />
            <span className="text-ink-2">{freshnessRuleText(f, rule)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StackedBar({ parts, total }: { parts: { n: number; cls: string; label: string }[]; total: number }) {
  return (
    <div
      role="img"
      aria-label={parts.map((p) => `${p.label} ${p.n}`).join(", ")}
      className="flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-sunken"
    >
      {parts
        .filter((p) => p.n > 0)
        .map((p) => (
          <span key={p.label} className={p.cls} style={{ width: `${(p.n / Math.max(total, 1)) * 100}%` }} />
        ))}
    </div>
  );
}
