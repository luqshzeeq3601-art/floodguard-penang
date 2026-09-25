import { useMemo } from "react";
import { clsx } from "clsx";
import { ChartSpline, Clock3, CloudRain, Database, Info, Landmark, Server, ShieldAlert, Waves } from "lucide-react";
import { useHealth, useMonitoring, useReady, useStations } from "../api/client";
import type { QualityIssue, ServiceInfo, SourceStatus } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel, PanelHeader } from "../components/Panel";
import { CollapsiblePanel } from "../components/CollapsiblePanel";
import { DataTable, type Column } from "../components/DataTable";
import { FreshnessChip, ServiceStatusLabel, StatusDot } from "../components/StatusChip";
import { TimeLabel } from "../components/Measurement";
import { EmptyState, QueryState } from "../components/States";
import { InfoTip } from "../components/InfoTip";
import { freshnessRuleText } from "../features/freshnessRule";
import { formatAge, formatPercent } from "../lib/format";
import { FRESHNESS, FRESHNESS_STATES } from "../lib/status";
import { TONE } from "../lib/tone";

const minutesSince = (iso: string | null) => (iso ? Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000)) : null);

export default function DataStatus() {
  const monitoring = useMonitoring();
  return (
    <>
      <PageHeader title="Data Status" updatedAt={monitoring.dataUpdatedAt || undefined} />
      <div className="grid gap-5 xl:grid-cols-12">
        <Panel className="xl:col-span-6" aria-labelledby="src-status">
          <PanelHeader id="src-status" title="Data Sources" />
          <QueryState query={monitoring} what="Source status">
            {(d) => (
              <ul className="stagger-in grid gap-3 sm:grid-cols-2">
                {d.sources.map((s) => (
                  <SourceCard key={s.source_id} source={s} />
                ))}
              </ul>
            )}
          </QueryState>
        </Panel>
        <ServiceHealth />

        <StationFreshness rule={monitoring.data?.freshness_rule} />
        <Panel className="min-w-0 xl:col-span-8" aria-labelledby="dq-issues">
          <PanelHeader id="dq-issues" title="Data quality issues" />
          <QueryState query={monitoring} what="Data quality issues">
            {(d) => <IssuesTable issues={d.quality_issues} />}
          </QueryState>
        </Panel>

        <Panel className="min-w-0 xl:col-span-12" aria-labelledby="services">
          <PanelHeader id="services" title="Services" />
          <QueryState query={monitoring} what="Services">
            {(d) => <ServicesTable services={d.services} />}
          </QueryState>
        </Panel>

        <div className="xl:col-span-12">
          <CollapsiblePanel title="Sources & Disclaimers" icon={Info} defaultOpen={false}>
            <ul className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
              <Disclaimer icon={Landmark} tone="bg-telemetry-subtle" iconClass="text-telemetry-text" title="JPS Observed Data">
                Rainfall and water-level readings and thresholds are published by Jabatan Pengairan dan Saliran (JPS) Malaysia and shown as received (UTC+8).
              </Disclaimer>
              <Disclaimer icon={Clock3} tone="bg-caution-subtle" iconClass="text-caution-text" title="Freshness Labels">
                Fresh, Delayed, Stale, No data and Invalid time are derived by FloodGuard from observation age. Not JPS statuses.
              </Disclaimer>
              <Disclaimer icon={ChartSpline} tone="bg-derived-subtle" iconClass="text-derived" title="FloodGuard Predictions">
                Machine learning model outputs for situational awareness. Not official forecasts or warnings.
              </Disclaimer>
              <Disclaimer icon={ShieldAlert} tone="bg-danger-subtle" iconClass="text-danger-text" title="Operational Prototype">
                For official flood information, refer to JPS Public Infobanjir and relevant Malaysian authorities.
              </Disclaimer>
            </ul>
          </CollapsiblePanel>
        </div>
      </div>
    </>
  );
}

function SourceCard({ source }: { source: SourceStatus }) {
  const Icon = source.sensor_type === "RAINFALL" ? CloudRain : source.sensor_type === "WATER_LEVEL" ? Waves : Database;
  const hasCounts = source.sensors_expected !== null && source.sensors_reporting !== null;
  return (
    <li className="rounded-control border border-line p-4">
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 size-6 shrink-0 text-telemetry-text" />
        <div className="min-w-0">
          <p className="font-semibold text-ink">{source.name}</p>
          <ServiceStatusLabel status={source.status} />
        </div>
      </div>
      {hasCounts ? (
        <div className="mt-4 space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-ink-2">Reporting</span>
            <span className="num font-semibold text-ink">
              {source.sensors_reporting} / {source.sensors_expected}
              <span className="ml-1 font-normal text-ink-3">({formatPercent(source.sensors_reporting!, source.sensors_expected!)})</span>
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
            <div
              className="h-full rounded-full bg-telemetry transition-all duration-300"
              style={{ width: `${Math.round((source.sensors_reporting! / Math.max(source.sensors_expected!, 1)) * 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <p className="mt-4 text-sm text-ink-3">Reporting counts not provided.</p>
      )}
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-ink-3">Last retrieval</dt>
          <dd className="num text-ink">
            <TimeLabel iso={source.last_success_at} /> <span className="text-ink-3">· {formatAge(minutesSince(source.last_success_at))}</span>
          </dd>
        </div>
        <div>
          <dt className="text-ink-3">Newest observation</dt>
          <dd className="num text-ink">
            <TimeLabel iso={source.newest_observation_time} />
          </dd>
        </div>
      </dl>
    </li>
  );
}

function ServiceHealth() {
  const health = useHealth();
  const ready = useReady();
  const monitoring = useMonitoring();
  const apiOk = health.data?.status === "ok";
  const cells = [
    {
      name: "API service",
      icon: Server,
      status: health.data ? (apiOk ? "HEALTHY" : "DEGRADED") : health.isPending ? null : "UNAVAILABLE",
      detail: health.data ? "Responding" : health.isPending ? "Checking…" : "Not responding",
      last: null as string | null,
    },
    {
      name: "Readiness",
      icon: Clock3,
      status: ready.data ? (ready.data.ready ? "HEALTHY" : "DEGRADED") : ready.isPending ? null : "UNAVAILABLE",
      detail: ready.data ? (ready.data.ready ? "Ready to serve" : (ready.data.checks.find((c) => !c.ok)?.detail ?? "Not ready")) : ready.isPending ? "Checking…" : "Unknown",
      last: null as string | null,
    },
    ...(monitoring.data?.services ?? []).map((s) => ({ name: s.name, icon: s.service_id.includes("model") ? ChartSpline : s.service_id.includes("db") ? Database : Clock3, status: s.status, detail: s.detail, last: s.last_success_at })),
  ] as const;
  return (
    <Panel className="xl:col-span-6" aria-labelledby="svc-health">
      <PanelHeader id="svc-health" title="Service health" />
      <ul className="grid auto-rows-fr grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {cells.map((c) => (
          <li key={c.name} className="flex h-full gap-3 rounded-control border border-line p-3.5">
            <c.icon aria-hidden className="mt-0.5 size-5 shrink-0 text-ink-2" />
            <div className="min-w-0">
              <p className="font-medium text-ink">{c.name}</p>
              {c.status ? <ServiceStatusLabel status={c.status} /> : <span className="text-sm text-ink-3">Checking…</span>}
              {c.detail && <p className="mt-0.5 text-xs text-ink-3">{c.detail}</p>}
              {c.last && <TimeLabel iso={c.last} prefix="Last success" className="block text-xs text-ink-3" />}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function StationFreshness({ rule }: { rule?: { fresh_max_minutes: number; stale_after_minutes: number } }) {
  const stations = useStations();
  const counts = useMemo(() => {
    const sensors = (stations.data?.sites ?? []).flatMap((s) => s.sensors);
    return { total: sensors.length, by: FRESHNESS_STATES.map((f) => ({ f, n: sensors.filter((s) => (s.latest?.freshness ?? "NO_DATA") === f).length })) };
  }, [stations.data]);
  return (
    <Panel className="xl:col-span-4" aria-labelledby="st-fresh">
      <PanelHeader
        id="st-fresh"
        title="Station freshness"
        qualifier="(all sensors)"
        info={
          <InfoTip label="How freshness is derived">
            Derived by FloodGuard from each observation's age; it is not a JPS status.
            <span className="mt-2 block">{(["FRESH", "DELAYED", "STALE"] as const).map((f) => `${FRESHNESS[f].label}: ${freshnessRuleText(f, rule)}`).join(" ")}</span>
          </InfoTip>
        }
      />
      <QueryState query={stations} what="Station freshness">
        {() => (
          <>
            <p className="num text-metric font-semibold text-ink">
              {counts.total} <span className="text-base font-normal text-ink-2">sensors monitored</span>
            </p>
            <div role="img" aria-label={counts.by.map((b) => `${FRESHNESS[b.f].label} ${b.n}`).join(", ")} className="mt-3 flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-sunken">
              {counts.by
                .filter((b) => b.n > 0)
                .map((b) => (
                  <span key={b.f} className={TONE[FRESHNESS[b.f].tone].bar} style={{ width: `${(b.n / Math.max(counts.total, 1)) * 100}%` }} />
                ))}
            </div>
            <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {counts.by.map((b) => (
                <li key={b.f} className="rounded-control border border-line p-3" title={freshnessRuleText(b.f, rule)}>
                  <FreshnessChip freshness={b.f} />
                  <p className="mt-1 flex items-baseline gap-1.5">
                    <span className="num text-xl font-semibold text-ink">{b.n}</span>
                    <span className="num text-xs text-ink-3">{formatPercent(b.n, counts.total)}</span>
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </QueryState>
    </Panel>
  );
}

function IssuesTable({ issues }: { issues: QualityIssue[] }) {
  const sorted = [...issues].sort((a, b) => (a.status === b.status ? Date.parse(b.detected_at) - Date.parse(a.detected_at) : a.status === "OPEN" ? -1 : 1));
  const columns: Column<QualityIssue>[] = [
    { key: "time", header: "Time (MYT)", cell: (i) => <TimeLabel iso={i.detected_at} full className="whitespace-nowrap text-ink-2" /> },
    { key: "source", header: "Source", cell: (i) => <span className="text-ink-2">{i.source}</span> },
    { key: "station", header: "Station", cell: (i) => i.site_name ?? <span className="text-ink-3">—</span> },
    { key: "issue", header: "Issue", cell: (i) => i.issue },
    {
      key: "status",
      header: "Status",
      cell: (i) => (
        <span className={clsx("inline-flex items-center gap-1.5 text-sm font-medium", i.status === "OPEN" ? "text-caution-text" : "text-ink-2")}>
          <StatusDot tone={i.status === "OPEN" ? "caution" : "neutral"} />
          {i.status === "OPEN" ? "Open" : "Resolved"}
        </span>
      ),
    },
  ];
  return (
    <DataTable
      caption="Data quality issues, open first"
      columns={columns}
      rows={sorted}
      rowKey={(i) => i.issue_id}
      pageSize={sorted.length > 10 ? 10 : undefined}
      stickyHeader={false}
      empty={<EmptyState title="No data quality issues" description="FloodGuard's validation checks found no open problems." />}
      mobileCard={(i) => (
        <div className="px-1 py-3 text-sm">
          <p className="font-medium text-ink">{i.issue}</p>
          <p className="text-ink-2">{[i.source, i.site_name].filter(Boolean).join(" · ")}</p>
          <p className="mt-1 flex justify-between text-xs text-ink-3">
            <TimeLabel iso={i.detected_at} full />
            {i.status === "OPEN" ? "Open" : "Resolved"}
          </p>
        </div>
      )}
    />
  );
}

function ServicesTable({ services }: { services: ServiceInfo[] }) {
  const columns: Column<ServiceInfo>[] = [
    { key: "name", header: "Service", cell: (s) => <span className="font-medium text-ink">{s.name}</span> },
    { key: "desc", header: "Description", cell: (s) => <span className="text-ink-2">{s.description}</span> },
    { key: "status", header: "Status", cell: (s) => <ServiceStatusLabel status={s.status} /> },
    { key: "last", header: "Last successful run (MYT)", cell: (s) => <TimeLabel iso={s.last_success_at} full className="whitespace-nowrap text-ink-2" /> },
    { key: "next", header: "Next run", cell: (s) => <TimeLabel iso={s.next_run_at} className="text-ink-2" /> },
    { key: "detail", header: "Detail", hideBelow: "xl", cell: (s) => <span className="text-ink-2">{s.detail ?? "—"}</span> },
  ];
  return (
    <DataTable
      caption="FloodGuard services"
      columns={columns}
      rows={services}
      rowKey={(s) => s.service_id}
      stickyHeader={false}
      empty={<EmptyState title="No services reported" />}
      mobileCard={(s) => (
        <div className="px-1 py-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium text-ink">{s.name}</p>
            <ServiceStatusLabel status={s.status} />
          </div>
          <p className="text-ink-2">{s.description}</p>
          <TimeLabel iso={s.last_success_at} prefix="Last success" full className="text-xs text-ink-3" />
        </div>
      )}
    />
  );
}

function Disclaimer({ icon: Icon, tone, iconClass, title, children }: { icon: typeof Landmark; tone: string; iconClass: string; title: string; children: React.ReactNode }) {
  return (
    <li className={clsx("flex gap-3 rounded-control p-4", tone)}>
      <Icon aria-hidden className={clsx("mt-0.5 size-5 shrink-0", iconClass)} />
      <div className="text-sm">
        <p className="font-semibold text-ink">{title}</p>
        <p className="mt-1 text-ink-2">{children}</p>
      </div>
    </li>
  );
}

