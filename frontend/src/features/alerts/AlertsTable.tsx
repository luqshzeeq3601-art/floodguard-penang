import type { ReactNode } from "react";
import { Link } from "react-router";
import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import type { Alert } from "../../api/types";
import { DataTable, type Column } from "../../components/DataTable";
import { OfficialStateChip, RiskChip } from "../../components/StatusChip";
import { TimeLabel } from "../../components/Measurement";
import { ALERT_CATEGORY } from "../../lib/status";
import { formatDayLabel } from "../../lib/format";

/** Severity cell: official state chip, FloodGuard risk chip, or a neutral category chip. */
export function AlertSeverity({ alert }: { alert: Alert }) {
  if (alert.category === "OFFICIAL_THRESHOLD" && alert.official_state) return <OfficialStateChip state={alert.official_state} />;
  if (alert.category === "FLOODGUARD_PREDICTION" && alert.risk_level) return <RiskChip level={alert.risk_level} compact />;
  const c = ALERT_CATEGORY[alert.category];
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-chip bg-neutral-subtle px-2 text-xs font-medium text-neutral-text">
      <c.Icon aria-hidden className="size-3.5" />
      {c.label}
    </span>
  );
}

export function AlertCategoryLabel({ alert }: { alert: Alert }) {
  const c = ALERT_CATEGORY[alert.category];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink-2">
      <c.Icon aria-hidden className={clsx("size-4", c.source === "JPS" ? "text-telemetry-text" : "text-derived")} />
      <span>
        {c.label}
        <span className="block text-xs text-ink-3">{c.source === "JPS" ? "JPS official" : "FloodGuard"}</span>
      </span>
    </span>
  );
}

export function AlertStatus({ status }: { status: Alert["status"] }) {
  return (
    <span
      className={clsx(
        "inline-flex h-6 items-center rounded-chip px-2 text-xs font-medium",
        status === "ACTIVE" ? "bg-primary-subtle text-primary-hover" : "bg-neutral-subtle text-neutral-text",
      )}
    >
      {status === "ACTIVE" ? "Active" : "Resolved"}
    </span>
  );
}

interface Props {
  alerts: Alert[];
  compact?: boolean;
  empty: ReactNode;
  selectedId?: string | null;
  onSelect?: (a: Alert) => void;
  pageSize?: number;
  /** Group rows under "Today" / "Yesterday" / date headers (MYT). */
  groupByDay?: boolean;
}

export function AlertsTable({ alerts, compact = false, empty, selectedId, onSelect, pageSize, groupByDay = false }: Props) {
  const station = (a: Alert) => (
    <div className="min-w-32">
      {a.site_id ? (
        <Link to={`/stations/${encodeURIComponent(a.site_id)}`} onClick={(e) => e.stopPropagation()} className="font-medium text-ink hover:text-primary hover:underline">
          {a.site_name ?? "Station"}
        </Link>
      ) : (
        <span className="text-ink-3">—</span>
      )}
      {!compact && a.district && <p className="text-xs text-ink-3 3xl:hidden">{a.district}</p>}
    </div>
  );

  const columns: Column<Alert>[] = [
    { key: "time", header: "Time (MYT)", sortValue: (a) => Date.parse(a.created_at), cell: (a) => <TimeLabel iso={a.created_at} full={compact} className="whitespace-nowrap text-ink-2" /> },
    { key: "severity", header: "Severity", cell: (a) => <AlertSeverity alert={a} /> },
    { key: "station", header: "Station", sortValue: (a) => a.site_name ?? "", cell: station },
    { key: "district", header: "District", sortValue: (a) => a.district ?? "", cell: (a) => <span className="text-ink-2">{a.district ?? "—"}</span>, hideBelow: compact ? undefined : "3xl" },
    { key: "type", header: "Alert type", hideBelow: compact ? undefined : "3xl", cell: (a) => <AlertCategoryLabel alert={a} /> },
    { key: "message", header: "Message", cell: (a) => <span className="line-clamp-2 min-w-44 text-ink">{a.message}</span> },
  ];
  if (!compact) {
    columns.push({ key: "status", header: "Status", cell: (a) => <AlertStatus status={a.status} /> });
    if (onSelect) {
      columns.push({
        key: "open",
        header: <span className="sr-only">Details</span>,
        cell: (a) => (
          <button
            type="button"
            aria-label={`Show details: ${a.message}`}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(a);
            }}
            className="inline-flex size-9 items-center justify-center rounded-control text-ink-3 hover:bg-hover hover:text-ink"
          >
            <ChevronRight aria-hidden className="size-4" />
          </button>
        ),
      });
    }
  }

  return (
    <DataTable
      caption="Alerts, newest first"
      columns={columns}
      rows={alerts}
      rowKey={(a) => a.alert_id}
      selectedKey={selectedId}
      onRowClick={onSelect}
      initialSort={{ key: "time", dir: "desc" }}
      pageSize={pageSize}
      empty={empty}
      stickyHeader={!compact}
      groupBy={groupByDay ? (a) => formatDayLabel(a.created_at) : undefined}
      mobileCard={(a) => (
        <button type="button" onClick={() => onSelect?.(a)} disabled={!onSelect} className="block w-full px-1 py-3 text-left disabled:cursor-default">
          <div className="flex items-center justify-between gap-2">
            <AlertSeverity alert={a} />
            <TimeLabel iso={a.created_at} className="text-xs text-ink-3" />
          </div>
          <p className="mt-1.5 text-sm font-medium text-ink">{a.site_name ?? ALERT_CATEGORY[a.category].label}</p>
          <p className="text-sm text-ink-2">{a.message}</p>
          <p className="mt-1 text-xs text-ink-3">
            {ALERT_CATEGORY[a.category].label} · {ALERT_CATEGORY[a.category].source === "JPS" ? "JPS official" : "FloodGuard"}
            {!compact && ` · ${a.status === "ACTIVE" ? "Active" : "Resolved"}`}
          </p>
        </button>
      )}
    />
  );
}
