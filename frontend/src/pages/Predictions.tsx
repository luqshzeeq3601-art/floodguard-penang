import { useMemo } from "react";
import { Link } from "react-router";
import { ChartSpline, ChevronRight, CircleSlash, SearchX, TriangleAlert } from "lucide-react";
import { usePredictions, useStations } from "../api/client";
import type { ModelInfo, Site, SitePrediction } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel, PanelHeader } from "../components/Panel";
import { SearchInput, Select } from "../components/Controls";
import { Button } from "../components/Button";
import { DataTable, type Column } from "../components/DataTable";
import { FreshnessChip, RiskChip, StatusDot } from "../components/StatusChip";
import { TimeLabel } from "../components/Measurement";
import { EmptyState, QueryState, SkeletonRows } from "../components/States";
import { SourceExplainer } from "../features/shared";
import { SiteType } from "../features/stations/StationsTable";
import { FRESHNESS_OPTIONS, RISK_OPTIONS, TYPE_OPTIONS, matchesType } from "../features/stations/filters";
import { HORIZONS, horizonOf, maxRisk } from "../features/predictions/horizons";
import { formatAge, formatHorizon, formatMetres, formatPercent, formatProbability } from "../lib/format";
import { RISK, RISK_LEVELS } from "../lib/status";
import { TONE } from "../lib/tone";
import { ALL, districtOptions, matchesDistrict, matchesSearch, useSetParams, useUrlParam } from "../lib/useUrlState";

interface Row {
  p: SitePrediction;
  site: Site | undefined;
}

const riskScore = (r: Row) => {
  const m = maxRisk(r.p);
  return m ? RISK[m.risk_level].rank * 10 + m.risk_probability : -1;
};

export default function Predictions() {
  const predictions = usePredictions();
  const stations = useStations();
  const model = predictions.data?.model;

  return (
    <>
      <PageHeader
        title="FloodGuard predictions"
        subtitle="Model outputs for situational awareness only. Not official JPS warnings."
        updatedAt={model?.last_run_at ? Date.parse(model.last_run_at) : undefined}
        updatedLabel="Last model run"
      />
      <QueryState query={predictions} what="Predictions" loading={<SkeletonRows rows={8} label="Loading predictions" />}>
        {(d) => <PredictionsBody model={d.model} list={d.predictions} sites={stations.data?.sites ?? []} />}
      </QueryState>
      {predictions.error?.kind === "not_available" && (
        <Panel className="mt-5" aria-labelledby="src-na">
          <PanelHeader id="src-na" title="Data sources" />
          <SourceExplainer layout="row" />
        </Panel>
      )}
    </>
  );
}

function PredictionsBody({ model, list, sites }: { model: ModelInfo; list: SitePrediction[]; sites: Site[] }) {
  const [district, setDistrict] = useUrlParam("district");
  const [type, setType] = useUrlParam("type");
  const [risk, setRisk] = useUrlParam("risk");
  const [quality, setQuality] = useUrlParam("quality");
  const [q, setQ] = useUrlParam("q", "");

  const bySite = useMemo(() => new Map(sites.map((s) => [s.site_id, s])), [sites]);
  const rows: Row[] = useMemo(() => list.map((p) => ({ p, site: bySite.get(p.site_id) })), [list, bySite]);
  const filtered = useMemo(
    () =>
      rows
        .filter(({ p, site }) => {
          if (site && !matchesDistrict(site, district)) return false;
          if (site && !matchesType(site, type)) return false;
          if (site && !matchesSearch(site, q)) return false;
          if (quality !== ALL && p.input_freshness !== quality) return false;
          if (risk !== ALL) {
            const r = maxRisk(p)?.risk_level ?? null;
            if (risk === "NONE" ? r !== null : r !== risk) return false;
          }
          return true;
        })
        .sort((a, b) => riskScore(b) - riskScore(a)),
    [rows, district, type, q, quality, risk],
  );
  const setParams = useSetParams();
  const clear = () => setParams({ district: null, type: null, risk: null, quality: null, q: null });

  const columns: Column<Row>[] = [
    { key: "rank", header: "#", cell: (_, i) => <span className="num text-ink-3">{i + 1}</span> },
    {
      key: "station",
      header: "Station name",
      sortValue: (r) => r.site?.name ?? r.p.site_id,
      cell: (r) => (
        <div className="min-w-36">
          <Link to={`/stations/${encodeURIComponent(r.p.site_id)}`} className="font-medium text-ink hover:text-primary hover:underline">
            {r.site?.name ?? "Unknown station"}
          </Link>
          <p className="text-xs text-ink-3 3xl:hidden">{r.site?.district}</p>
        </div>
      ),
    },
    { key: "district", header: "District", hideBelow: "3xl", sortValue: (r) => r.site?.district ?? "", cell: (r) => <span className="text-ink-2">{r.site?.district ?? "—"}</span> },
    { key: "type", header: "Type", hideBelow: "3xl", cell: (r) => (r.site ? <SiteType site={r.site} /> : "—") },
    ...HORIZONS.map<Column<Row>>((h) => ({
      key: `h${h}`,
      header: formatHorizon(h),
      sortValue: (r) => (r.p.status === "UNAVAILABLE" ? -1 : (horizonOf(r.p, h)?.risk_probability ?? -1)),
      cell: (r) => <HorizonCell row={r} h={h} />,
    })),
    { key: "time", header: "Prediction time (MYT)", hideBelow: "3xl", sortValue: (r) => r.p.generated_at, cell: (r) => <TimeLabel iso={r.p.generated_at} className="whitespace-nowrap text-ink-2" /> },
    {
      key: "quality",
      header: "Input data",
      cell: (r) => (
        <div className="flex flex-col gap-0.5">
          <FreshnessChip freshness={r.p.input_freshness} />
          <TimeLabel iso={r.p.generated_at} prefix="Generated" className="text-xs whitespace-nowrap text-ink-3 3xl:hidden" />
          {r.p.status === "DEGRADED" && (
            <span className="inline-flex items-center gap-1 text-xs text-caution-text">
              <TriangleAlert aria-hidden className="size-3" />
              {formatAge(r.p.input_age_minutes)}
            </span>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-5 xl:grid-cols-12">
      <SummaryPanel rows={rows} />
      <GuidePanel />
      <FreshnessPanel model={model} rows={rows} />

      <Panel className="min-w-0 xl:col-span-8 3xl:col-span-9" aria-labelledby="station-predictions">
        <PanelHeader id="station-predictions" title="Station predictions" />
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 3xl:grid-cols-5">
          <Select label="District" hideLabel value={district} onChange={setDistrict} options={districtOptions(sites)} />
          <Select label="Sensor type" hideLabel value={type} onChange={setType} options={TYPE_OPTIONS} />
          <Select label="Risk level" hideLabel value={risk} onChange={setRisk} options={RISK_OPTIONS} />
          <Select label="Input data quality" hideLabel value={quality} onChange={setQuality} options={FRESHNESS_OPTIONS.map((o) => (o.value === ALL ? { ...o, label: "All data quality" } : o))} />
          <SearchInput label="Search stations" placeholder="Search stations" value={q} onChange={setQ} />
        </div>
        <DataTable
          caption="FloodGuard predictions by station and horizon, highest model risk first"
          columns={columns}
          rows={filtered}
          rowKey={(r) => r.p.site_id}
          pageSize={20}
          empty={<EmptyState icon={SearchX} title="No predictions match these filters" action={<Button onClick={clear}>Clear filters</Button>} />}
          mobileCard={(r) => (
            <div className="px-1 py-3">
              <Link to={`/stations/${encodeURIComponent(r.p.site_id)}`} className="font-medium text-ink hover:text-primary">
                {r.site?.name ?? "Unknown station"}
              </Link>
              <p className="text-xs text-ink-3">{r.site?.district}</p>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {HORIZONS.map((h) => (
                  <div key={h}>
                    <p className="text-xs text-ink-3">{formatHorizon(h)}</p>
                    <HorizonCell row={r} h={h} />
                  </div>
                ))}
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-ink-3">
                <TimeLabel iso={r.p.generated_at} prefix="Generated" />
                <FreshnessChip freshness={r.p.input_freshness} />
              </div>
            </div>
          )}
        />
      </Panel>

      <div className="grid content-start gap-5 md:grid-cols-2 xl:col-span-4 xl:grid-cols-1 3xl:col-span-3">
        <TopRiskPanel rows={rows} />
        <Panel aria-labelledby="pred-sources">
          <PanelHeader id="pred-sources" title="Data sources" />
          <SourceExplainer />
        </Panel>
      </div>
    </div>
  );
}

function HorizonCell({ row, h }: { row: Row; h: number }) {
  if (row.p.status === "UNAVAILABLE") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-ink-3" title={row.p.unavailable_reason ?? "Prediction unavailable"}>
        <CircleSlash aria-hidden className="size-3.5" />
        Unavailable
      </span>
    );
  }
  const hp = horizonOf(row.p, h);
  if (!hp) return <span className="text-ink-3">—</span>;
  return (
    <div className={row.p.status === "DEGRADED" ? "opacity-80" : undefined}>
      <RiskChip level={hp.risk_level} compact value={formatProbability(hp.risk_probability)} />
      {hp.predicted_water_level_m !== null && <p className="num mt-0.5 text-xs text-ink-3">{formatMetres(hp.predicted_water_level_m)}</p>}
    </div>
  );
}

function SummaryPanel({ rows }: { rows: Row[] }) {
  const counted = rows.filter((r) => r.p.status !== "UNAVAILABLE");
  return (
    <Panel className="xl:col-span-5 3xl:col-span-6" aria-labelledby="pred-summary">
      <PanelHeader id="pred-summary" title="Prediction Summary" qualifier="(highest in next 2 h)" />
      <ul className="stagger-in grid gap-3 sm:grid-cols-3">
        {RISK_LEVELS.map((level) => {
          const n = counted.filter((r) => maxRisk(r.p)?.risk_level === level).length;
          const r = RISK[level];
          return (
            <li key={level} className={`rounded-control border border-dashed p-3.5 transition-ui hover:shadow-xs ${TONE[r.tone].outlineChip.split(" ")[0]} ${TONE[r.tone].subtle}`}>
              <p className={`flex items-center gap-1.5 text-xs font-semibold ${TONE[r.tone].text}`}>
                <r.Icon aria-hidden className="size-4" />
                {r.label}
              </p>
              <p className="num mt-1 text-metric font-bold text-ink">{n}</p>
              <p className="num text-2xs text-ink-3">{formatPercent(n, counted.length)} of modeled sites</p>
            </li>
          );
        })}
      </ul>
      {rows.length > counted.length && (
        <p className="num mt-2.5 text-xs text-ink-3">
          {rows.length - counted.length} {rows.length - counted.length === 1 ? "station has" : "stations have"} no prediction.
        </p>
      )}
    </Panel>
  );
}

function GuidePanel() {
  return (
    <Panel className="xl:col-span-4 3xl:col-span-3" aria-labelledby="pred-guide">
      <PanelHeader id="pred-guide" title="Risk Levels" />
      <ul className="space-y-2.5 text-xs">
        {RISK_LEVELS.map((l) => (
          <li key={l} className="grid grid-cols-[auto_1fr] items-center gap-2.5">
            <RiskChip level={l} compact />
            <span className="text-ink-2">{RISK[l].description}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function FreshnessPanel({ model, rows }: { model: ModelInfo; rows: Row[] }) {
  const n = (s: SitePrediction["status"]) => rows.filter((r) => r.p.status === s).length;
  return (
    <Panel className="xl:col-span-3" aria-labelledby="pred-fresh">
      <PanelHeader
        id="pred-fresh"
        title="Model Status"
        actions={
          <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${model.ready ? "text-normal-text" : "text-danger-text"}`}>
            <StatusDot tone={model.ready ? "normal" : "danger"} />
            {model.ready ? "Ready" : "Unavailable"}
          </span>
        }
      />
      {!model.ready && model.unavailable_reason && <p className="mb-2 text-xs text-ink-2">{model.unavailable_reason}</p>}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        {[
          { term: "Last run", value: <TimeLabel iso={model.last_run_at} /> },
          { term: "Next run", value: <TimeLabel iso={model.next_run_at} /> },
          { term: "Current", value: n("AVAILABLE") },
          { term: "Delayed", value: n("DEGRADED") },
          { term: "Version", value: <span className="font-mono text-xs">{model.model_version ?? "—"}</span> },
        ].map((it) => (
          <div key={it.term}>
            <dt className="text-2xs text-ink-3">{it.term}</dt>
            <dd className="num font-medium text-ink">{it.value}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function TopRiskPanel({ rows }: { rows: Row[] }) {
  const top = [...rows].filter((r) => maxRisk(r.p)).sort((a, b) => riskScore(b) - riskScore(a)).slice(0, 5);
  return (
    <Panel aria-labelledby="top-risk">
      <PanelHeader id="top-risk" title="Top Stations by Risk" icon={ChartSpline} />
      {top.length === 0 ? (
        <EmptyState title="No current predictions" />
      ) : (
        <ol className="stagger-in divide-y divide-line">
          {top.map((r, i) => {
            const m = maxRisk(r.p)!;
            return (
              <li key={r.p.site_id}>
                <Link to={`/stations/${encodeURIComponent(r.p.site_id)}`} className="group flex items-center gap-3 py-2.5 hover:bg-subtle focus-visible:outline-offset-[-2px]">
                  <span className="num inline-flex size-6 shrink-0 items-center justify-center rounded-md bg-subtle text-xs font-semibold text-ink-2">{i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-1 block text-sm font-medium text-ink group-hover:text-primary">{r.site?.name ?? "Unknown station"}</span>
                    <span className="block text-2xs text-ink-3">{r.site?.district}</span>
                  </span>
                  <span className="flex flex-col items-end gap-0.5">
                    <RiskChip level={m.risk_level} compact />
                    <span className="num text-2xs text-ink-3">
                      {formatProbability(m.risk_probability)} in {formatHorizon(m.horizon_minutes)}
                    </span>
                  </span>
                  <ChevronRight aria-hidden className="size-4 text-ink-3 opacity-60 group-hover:opacity-100" />
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
