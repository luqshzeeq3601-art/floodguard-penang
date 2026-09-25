import { useMemo } from "react";
import { Link } from "react-router";
import { clsx } from "clsx";
import { ArrowRight, BellOff, CircleCheck, Database, SearchX, X, ChartSpline, Info, type LucideIcon } from "lucide-react";
import { useAlerts } from "../api/client";
import type { Alert, AlertCategory } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { DefinitionList, Panel, PanelHeader } from "../components/Panel";
import { CollapsiblePanel } from "../components/CollapsiblePanel";
import { SearchInput, Select } from "../components/Controls";
import { Button, IconButton, TextLink } from "../components/Button";
import { SourceLabel } from "../components/StatusChip";
import { TimeLabel } from "../components/Measurement";
import { EmptyState, QueryState, SkeletonRows } from "../components/States";
import { AlertCategoryLabel, AlertSeverity, AlertStatus, AlertsTable } from "../features/alerts/AlertsTable";
import { formatHorizon, formatMetres, formatMm, formatProbability } from "../lib/format";
import { ALERT_CATEGORY, OFFICIAL_STATE, RISK, type Tone } from "../lib/status";
import { TONE } from "../lib/tone";
import { useMediaQuery } from "../lib/useMediaQuery";
import { Drawer } from "../components/Drawer";
import { ALL, useSetParams, useUrlParam } from "../lib/useUrlState";

const RANGE_OPTIONS = [
  { value: "24", label: "Last 24 hours" },
  { value: "72", label: "Last 3 days" },
  { value: "168", label: "Last 7 days" },
];

const SEVERITY_OPTIONS = [
  { value: ALL, label: "All severity" },
  { value: "BAHAYA", label: "Bahaya (JPS)" },
  { value: "AMARAN", label: "Amaran (JPS)" },
  { value: "WASPADA", label: "Waspada (JPS)" },
  { value: "HIGH", label: "High risk (FloodGuard)" },
  { value: "MEDIUM", label: "Medium risk (FloodGuard)" },
  { value: "LOW", label: "Low risk (FloodGuard)" },
];

const TYPE_OPTIONS = [{ value: ALL, label: "All types" }, ...(Object.keys(ALERT_CATEGORY) as AlertCategory[]).map((c) => ({ value: c, label: ALERT_CATEGORY[c].label }))];
const STATUS_OPTIONS = [
  { value: ALL, label: "All statuses" },
  { value: "ACTIVE", label: "Active" },
  { value: "RESOLVED", label: "Resolved" },
];

const severityKey = (a: Alert) => a.official_state ?? a.risk_level ?? null;

export default function Alerts() {
  const [range, setRange] = useUrlParam("range", "24");
  const alerts = useAlerts(Number(range));
  return (
    <>
      <PageHeader title="Alerts" updatedAt={alerts.dataUpdatedAt || undefined}>
        <Select label="Time range" hideLabel value={range} onChange={setRange} options={RANGE_OPTIONS} className="w-44" />
      </PageHeader>
      <QueryState query={alerts} what="Alerts" loading={<SkeletonRows rows={8} label="Loading alerts" />}>
        {(d) => <AlertsBody alerts={d.alerts} />}
      </QueryState>
    </>
  );
}

function AlertsBody({ alerts }: { alerts: Alert[] }) {
  const [severity, setSeverity] = useUrlParam("severity");
  const [type, setType] = useUrlParam("type");
  const [status, setStatus] = useUrlParam("status");
  const [district, setDistrict] = useUrlParam("district");
  const [q, setQ] = useUrlParam("q", "");
  const [selectedId, setSelectedId] = useUrlParam("alert", "");

  const districts = useMemo(() => [ALL, ...new Set(alerts.map((a) => a.district).filter((d): d is string => !!d))], [alerts]);
  const filtered = useMemo(
    () =>
      alerts.filter((a) => {
        if (severity !== ALL && severityKey(a) !== severity) return false;
        if (type !== ALL && a.category !== type) return false;
        if (status !== ALL && a.status !== status) return false;
        if (district !== ALL && a.district !== district) return false;
        const needle = q.trim().toLowerCase();
        if (needle && ![a.site_name, a.district, a.message].some((v) => v?.toLowerCase().includes(needle))) return false;
        return true;
      }),
    [alerts, severity, type, status, district, q],
  );
  const selected = alerts.find((a) => a.alert_id === selectedId) ?? null;
  // Side panel only where the table keeps its width; a drawer everywhere else.
  const wide = useMediaQuery("(min-width: 120rem)");
  const active = alerts.filter((a) => a.status === "ACTIVE");
  const setParams = useSetParams();
  const clear = () => setParams({ severity: null, type: null, status: null, district: null, q: null });
  const apply = (sev: string, cat: string, st: string) => setParams({ severity: sev, type: cat, status: st, district: null, q: null });

  const isActive = (sev: string, cat: string, st: string) => severity === sev && type === cat && status === st && district === ALL && !q;
  const summary: { label: string; n: number; tone: Tone; icon: LucideIcon; note: string; onClick: () => void; active: boolean }[] = [
    ...(["BAHAYA", "AMARAN", "WASPADA"] as const).map((s) => ({
      label: OFFICIAL_STATE[s].label,
      n: active.filter((a) => a.category === "OFFICIAL_THRESHOLD" && a.official_state === s).length,
      tone: OFFICIAL_STATE[s].tone,
      icon: OFFICIAL_STATE[s].Icon,
      note: "Active · JPS official",
      onClick: () => apply(s, "OFFICIAL_THRESHOLD", "ACTIVE"),
      active: isActive(s, "OFFICIAL_THRESHOLD", "ACTIVE"),
    })),
    { label: "FloodGuard prediction", n: active.filter((a) => a.category === "FLOODGUARD_PREDICTION").length, tone: "neutral", icon: ChartSpline, note: "Active · model output", onClick: () => apply(ALL, "FLOODGUARD_PREDICTION", "ACTIVE"), active: isActive(ALL, "FLOODGUARD_PREDICTION", "ACTIVE") },
    { label: "Data quality", n: active.filter((a) => a.category === "DATA_QUALITY").length, tone: "info", icon: Database, note: "Active · FloodGuard-derived", onClick: () => apply(ALL, "DATA_QUALITY", "ACTIVE"), active: isActive(ALL, "DATA_QUALITY", "ACTIVE") },
    { label: "Resolved", n: alerts.filter((a) => a.status === "RESOLVED").length, tone: "normal", icon: CircleCheck, note: "In this time range", onClick: () => apply(ALL, ALL, "RESOLVED"), active: isActive(ALL, ALL, "RESOLVED") },
  ];

  if (alerts.length === 0) {
    return (
      <Panel>
        <EmptyState icon={BellOff} title="No alerts in this period" description="No official threshold, FloodGuard, data-quality or system alerts were raised in the selected time range." />
      </Panel>
    );
  }

  return (
    <div className="space-y-5">
      <ul aria-label="Alert summary" className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-6">
        {summary.map((s) => (
          <li key={s.label}>
            <button
              type="button"
              aria-pressed={s.active}
              onClick={s.active ? clear : s.onClick}
              className={clsx(
                "lift flex w-full items-center gap-3 rounded-panel border bg-surface p-4 text-left",
                s.active ? "border-primary bg-primary-subtle shadow-raised" : "border-line hover:border-primary-line",
              )}
            >
              <span className={clsx("inline-flex size-10 shrink-0 items-center justify-center rounded-full", TONE[s.tone].subtle)}>
                <s.icon aria-hidden className={clsx("size-5", s.tone === "neutral" ? "text-derived" : TONE[s.tone].text)} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-ink" lang={["Bahaya", "Amaran", "Waspada"].includes(s.label) ? "ms" : undefined}>
                  {s.label}
                </span>
                <span className="num block text-xl font-semibold text-ink">{s.n}</span>
                <span className="block text-xs text-ink-3">{s.note}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>

      <div className="grid gap-5 xl:grid-cols-12">
        <Panel className={clsx("min-w-0", selected && wide ? "xl:col-span-8" : "xl:col-span-12")} aria-labelledby="all-alerts">
          <PanelHeader id="all-alerts" title="All alerts" qualifier={`(${filtered.length})`} />
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-5">
            <Select label="Severity" hideLabel value={severity} onChange={setSeverity} options={SEVERITY_OPTIONS} />
            <Select label="Alert type" hideLabel value={type} onChange={setType} options={TYPE_OPTIONS} />
            <Select label="Status" hideLabel value={status} onChange={setStatus} options={STATUS_OPTIONS} />
            <Select label="District" hideLabel value={district} onChange={setDistrict} options={districts.map((d) => ({ value: d, label: d === ALL ? "All districts" : d }))} />
            <SearchInput label="Search alerts" placeholder="Search stations or messages" value={q} onChange={setQ} />
          </div>
          <AlertsTable
            alerts={filtered}
            selectedId={selectedId || null}
            onSelect={(a) => setSelectedId(a.alert_id)}
            pageSize={20}
            groupByDay
            empty={<EmptyState icon={SearchX} title="No alerts match these filters" action={<Button onClick={clear}>Clear filters</Button>} />}
          />
        </Panel>
        {selected && wide && (
          <Panel as="aside" variant="raised" className="xl:col-span-4" aria-label="Alert details">
            <AlertDetail alert={selected} onClose={() => setSelectedId("")} />
          </Panel>
        )}
        {!wide && (
          <Drawer open={!!selected} onClose={() => setSelectedId("")} label="Alert details">
            {selected && <AlertDetail alert={selected} onClose={() => setSelectedId("")} />}
          </Drawer>
        )}
      </div>

      <CollapsiblePanel title="Alert Categories Reference" icon={Info} defaultOpen={false}>
        <ul className="grid gap-4 text-xs sm:grid-cols-2 2xl:grid-cols-4">
          <li className="rounded-control bg-subtle p-3">
            <p className="font-semibold text-ink">Official threshold (JPS)</p>
            <p className="mt-1 text-ink-2">Water level reached a JPS Waspada, Amaran or Bahaya threshold.</p>
          </li>
          <li className="rounded-control bg-subtle p-3">
            <p className="font-semibold text-ink">FloodGuard prediction</p>
            <p className="mt-1 text-ink-2">Model output about possible escalation. Not an official warning.</p>
          </li>
          <li className="rounded-control bg-subtle p-3">
            <p className="font-semibold text-ink">Data quality</p>
            <p className="mt-1 text-ink-2">Stale, missing or implausible readings detected by FloodGuard.</p>
          </li>
          <li className="rounded-control bg-subtle p-3">
            <p className="font-semibold text-ink">System</p>
            <p className="mt-1 text-ink-2">A FloodGuard service or data source is degraded or unavailable.</p>
          </li>
        </ul>
      </CollapsiblePanel>
    </div>
  );
}

function AlertDetail({ alert, onClose }: { alert: Alert; onClose: () => void }) {
  const isOfficial = alert.category === "OFFICIAL_THRESHOLD";
  const isPrediction = alert.category === "FLOODGUARD_PREDICTION";
  const fmtObs = alert.observed_unit === "mm" ? formatMm : formatMetres;
  const box = isOfficial && alert.official_state ? TONE[OFFICIAL_STATE[alert.official_state].tone].subtle : isPrediction ? "bg-derived-subtle" : "bg-subtle";
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <AlertSeverity alert={alert} />
          <AlertStatus status={alert.status} />
        </div>
        <IconButton icon={X} label="Close alert details" onClick={onClose} />
      </div>
      <h2 className="mt-3 text-lg font-semibold text-ink">{alert.site_name ?? ALERT_CATEGORY[alert.category].label}</h2>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-2">
        {alert.district && <span>{alert.district}</span>}
        <AlertCategoryLabel alert={alert} />
      </div>
      <div className="mt-2">
        <SourceLabel source={isOfficial ? "JPS" : "FloodGuard"}>{isOfficial ? "JPS official threshold" : isPrediction ? "FloodGuard model output · not official" : "FloodGuard-derived"}</SourceLabel>
      </div>

      <p className={clsx("mt-4 rounded-control p-3 text-sm text-ink", box)}>{alert.message}</p>

      {(alert.observed_value !== undefined && alert.observed_value !== null) || alert.threshold_value_m ? (
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-control border border-line p-3">
            <p className="text-xs text-ink-2">Observed {alert.observed_unit === "mm" ? "rainfall" : "water level"}</p>
            <p className="num mt-1 text-xl font-semibold text-ink">{fmtObs(alert.observed_value)}</p>
            <TimeLabel iso={alert.observation_time} prefix="Obs" full className="text-xs text-ink-3" />
          </div>
          {alert.threshold_value_m !== undefined && alert.threshold_value_m !== null && alert.official_state && (
            <div className="rounded-control border border-line p-3">
              <p className="text-xs text-ink-2">
                <span lang="ms">{OFFICIAL_STATE[alert.official_state].label}</span> threshold (JPS)
              </p>
              <p className="num mt-1 text-xl font-semibold text-ink">{formatMetres(alert.threshold_value_m)}</p>
            </div>
          )}
        </div>
      ) : null}

      <h3 className="mt-5 mb-2 text-md font-semibold text-ink">Alert details</h3>
      <DefinitionList
        items={[
          { term: "Category", value: ALERT_CATEGORY[alert.category].label },
          ...(isPrediction
            ? [
                { term: "Horizon", value: alert.horizon_minutes ? formatHorizon(alert.horizon_minutes) : "—" },
                { term: "Probability", value: formatProbability(alert.risk_probability) },
                { term: "Risk level", value: alert.risk_level ? RISK[alert.risk_level].label : "—" },
                { term: "Model version", value: <span className="font-mono text-xs">{alert.model_version ?? "—"}</span> },
              ]
            : []),
          { term: "Detected at", value: <TimeLabel iso={alert.created_at} full /> },
          { term: "Updated at", value: <TimeLabel iso={alert.updated_at} full /> },
          ...(alert.delivery_status ? [{ term: "Delivery", value: alert.delivery_status.charAt(0) + alert.delivery_status.slice(1).toLowerCase() }] : []),
        ]}
      />
      {alert.site_id && (
        <div className="mt-4 flex flex-wrap gap-4 border-t border-line pt-4">
          <TextLink to={`/stations/${encodeURIComponent(alert.site_id)}`} iconEnd={ArrowRight}>
            Open station detail
          </TextLink>
          <Link to={`/map?station=${encodeURIComponent(alert.site_id)}`} className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
            View on map
          </Link>
        </div>
      )}
    </div>
  );
}
