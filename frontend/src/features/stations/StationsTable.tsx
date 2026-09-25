import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Site } from "../../api/types";
import { DataTable, type Column } from "../../components/DataTable";
import { FreshnessChip, OfficialStateChip } from "../../components/StatusChip";
import { TimeLabel } from "../../components/Measurement";
import { ChevronRight } from "lucide-react";
import { MarkerGlyph } from "../../components/map/MarkerGlyph";
import { markerSpec } from "../../components/map/markerStyle";
import { formatNumber } from "../../lib/format";
import { FRESHNESS, OFFICIAL_STATE, SITE_KIND_LABEL, sensorOf, siteFreshness, siteOfficialState, siteSensorKind } from "../../lib/status";
import { SiteReading } from "../shared";

const href = (s: Site) => `/stations/${encodeURIComponent(s.site_id)}`;
const latestTime = (s: Site) => s.sensors.map((x) => x.latest?.observation_time).filter(Boolean).sort().at(-1) ?? null;
const stateRank = (s: Site) => {
  const st = siteOfficialState(s);
  return st ? OFFICIAL_STATE[st].rank : -1;
};

function StationName({ site, onSelect, showDistrict }: { site: Site; onSelect?: (id: string) => void; showDistrict?: boolean }) {
  const basin = [site.main_basin, site.sub_basin].filter(Boolean).join(" · ");
  return (
    <div className="min-w-40">
      {onSelect ? (
        <button type="button" onClick={(e) => { e.stopPropagation(); onSelect(site.site_id); }} className="text-left font-medium text-ink hover:text-primary hover:underline">
          {site.name}
        </button>
      ) : (
        <Link to={href(site)} className="font-medium text-ink hover:text-primary hover:underline">
          {site.name}
        </Link>
      )}
      {showDistrict ? <p className="text-xs text-ink-3 3xl:hidden">{site.district}</p> : basin && <p className="text-xs text-ink-3">{basin}</p>}
    </div>
  );
}

export function SiteType({ site }: { site: Site }) {
  const kind = siteSensorKind(site);
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap text-ink-2">
      <span className="inline-flex w-4 justify-center">
        <MarkerGlyph spec={{ ...markerSpec(site), fill: kind === "RAINFALL" ? "telemetry" : "neutral", muted: false, size: kind === "RAINFALL" ? 10 : 12 }} />
      </span>
      {kind === "SHARED" ? "WL + RF" : SITE_KIND_LABEL[kind]}
    </span>
  );
}

/** Official JPS state, or an explicit dash: rainfall has no official state; stale readings are not evaluated. */
export function Condition({ site }: { site: Site }) {
  const st = siteOfficialState(site);
  if (st) return <OfficialStateChip state={st} />;
  const reason = sensorOf(site, "WATER_LEVEL") ? "Not evaluated: no current reading" : "JPS publishes no rainfall state";
  return (
    <span className="text-ink-3" title={reason}>
      —<span className="sr-only">{reason}</span>
    </span>
  );
}

interface Props {
  sites: Site[];
  variant: "full" | "preview";
  caption: string;
  empty: ReactNode;
  selectedId?: string | null;
  onSelect?: (siteId: string) => void;
  pageSize?: number;
}

export function StationsTable({ sites, variant, caption, empty, selectedId, onSelect, pageSize }: Props) {
  const num: Column<Site> = { key: "rank", header: "#", cell: (_, i) => <span className="num text-ink-3">{i + 1}</span> };
  const name: Column<Site> = { key: "name", header: "Station name", sortValue: (s) => s.name, cell: (s) => <StationName site={s} onSelect={onSelect} showDistrict={variant === "full"} /> };
  const district: Column<Site> = { key: "district", header: "District", sortValue: (s) => s.district, cell: (s) => <span className="text-ink-2">{s.district}</span> };
  const type: Column<Site> = { key: "type", header: "Type", sortValue: (s) => siteSensorKind(s), cell: (s) => <SiteType site={s} /> };
  const condition: Column<Site> = { key: "condition", header: variant === "full" ? "Condition (JPS)" : "State (JPS)", sortValue: stateRank, cell: (s) => <Condition site={s} /> };
  const freshness: Column<Site> = {
    key: "freshness",
    header: "Freshness",
    sortValue: (s) => FRESHNESS[siteFreshness(s)].rank,
    cell: (s) => <FreshnessChip freshness={siteFreshness(s)} />,
  };

  const columns: Column<Site>[] =
    variant === "full"
      ? [
          num,
          name,
          { ...district, hideBelow: "3xl" },
          type,
          {
            key: "rain",
            header: "Rainfall 1 h (mm)",
            align: "right",
            sortValue: (s) => sensorOf(s, "RAINFALL")?.latest?.rainfall_1h_mm ?? -1,
            cell: (s) => (sensorOf(s, "RAINFALL") ? formatNumber(sensorOf(s, "RAINFALL")?.latest?.rainfall_1h_mm, 1) : <span className="text-ink-3">—</span>),
          },
          {
            key: "level",
            header: "Water level (m)",
            align: "right",
            sortValue: (s) => sensorOf(s, "WATER_LEVEL")?.latest?.water_level_m ?? -Infinity,
            cell: (s) => (sensorOf(s, "WATER_LEVEL") ? formatNumber(sensorOf(s, "WATER_LEVEL")?.latest?.water_level_m, 2) : <span className="text-ink-3">—</span>),
          },
          { key: "time", header: "Last observation (MYT)", sortValue: (s) => latestTime(s) ?? "", cell: (s) => <TimeLabel iso={latestTime(s)} className="whitespace-nowrap text-ink-2" />, hideBelow: "3xl" },
          {
            ...freshness,
            cell: (s) => (
              <div className="flex flex-col gap-0.5">
                <FreshnessChip freshness={siteFreshness(s)} />
                <TimeLabel iso={latestTime(s)} prefix="Obs" className="text-xs whitespace-nowrap text-ink-3 3xl:hidden" />
              </div>
            ),
          },
          condition,
          {
            key: "open",
            header: <span className="sr-only">Open</span>,
            cell: () => <ChevronRight aria-hidden className="size-4 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" />,
          },
        ]
      : [num, name, { ...district, hideBelow: "2xl" }, type, { key: "reading", header: "Current reading", cell: (s) => <SiteReading site={s} /> }, condition, freshness];

  return (
    <DataTable
      caption={caption}
      columns={columns}
      rows={sites}
      rowKey={(s) => s.site_id}
      selectedKey={selectedId}
      onRowClick={onSelect ? (s) => onSelect(s.site_id) : undefined}
      pageSize={pageSize}
      empty={empty}
      mobileCard={(s, i) => (
        <div className="flex items-start gap-3 px-1 py-3">
          <span className="num w-5 pt-0.5 text-xs text-ink-3">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <Link to={href(s)} className="font-medium text-ink hover:text-primary">
                {s.name}
              </Link>
              <Condition site={s} />
            </div>
            <p className="text-xs text-ink-3">
              {s.district} · {SITE_KIND_LABEL[siteSensorKind(s)]}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 text-sm">
              <SiteReading site={s} />
              <span className="flex flex-col items-end gap-0.5">
                <TimeLabel iso={latestTime(s)} prefix="Obs" className="text-xs text-ink-3" />
                <FreshnessChip freshness={siteFreshness(s)} />
              </span>
            </div>
          </div>
        </div>
      )}
    />
  );
}
