import { lazy, Suspense, useMemo, useState } from "react";
import { useParams } from "react-router";
import { ArrowLeft, Calendar, ChartSpline, Clock, CloudRain, Database, FileText, GitBranch, Hash, Landmark, Layers, MapPin, MapPinOff, ShieldCheck, TrendingUp, Waves } from "lucide-react";
import { InfoTip } from "../components/InfoTip";
import { ThresholdMeter } from "../components/ThresholdMeter";
import { useObservations, usePredictions, useStation } from "../api/client";
import type { Sensor, Site, SitePrediction } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";
import { DefinitionList, Panel, PanelHeader } from "../components/Panel";
import { CollapsiblePanel } from "../components/CollapsiblePanel";
import { ButtonLink } from "../components/Button";
import { SegmentedControl } from "../components/Controls";
import { Measurement, TimeLabel } from "../components/Measurement";
import { FreshnessChip, OfficialStateChip, SourceLabel } from "../components/StatusChip";
import { EmptyState, QueryState, Skeleton, UnavailableFeature } from "../components/States";
import { ObservationChart, type ForecastPoint } from "../components/charts/ObservationChart";
import { toChartSeries } from "../components/charts/series";
import { PredictionHorizons } from "../features/predictions/PredictionHorizons";
import { formatAge, formatDateTime, formatMetres, formatMm, formatSignedMetres } from "../lib/format";
import { OFFICIAL_STATE, SITE_KIND_LABEL, sensorOf, siteSensorKind } from "../lib/status";

const StationMap = lazy(() => import("../components/map/StationMap"));

export default function StationDetail() {
  const { stationId = "" } = useParams();
  const station = useStation(stationId);
  const name = station.data?.name ?? "Station detail";
  return (
    <>
      <PageHeader
        title={name}
        breadcrumb={[{ label: "Stations", to: "/stations" }, { label: "Detail" }]}
        updatedAt={station.dataUpdatedAt || undefined}
        meta={station.data && <IdentityChips site={station.data} />}
      >
        <ButtonLink to="/stations" icon={ArrowLeft}>
          All stations
        </ButtonLink>
      </PageHeader>
      {station.error?.kind === "not_available" && !station.data ? (
        <Panel>
          <EmptyState icon={MapPinOff} title="Station not found" description="It may have been removed from the source listing." action={<ButtonLink to="/stations">Back to stations</ButtonLink>} />
        </Panel>
      ) : (
        <QueryState query={station} what="Station" loading={<Skeleton className="h-96 rounded-panel" />}>
          {(site) => <StationBody site={site} />}
        </QueryState>
      )}
    </>
  );
}

function IdentityChips({ site }: { site: Site }) {
  const chip = "inline-flex h-7 items-center gap-1.5 rounded-control bg-subtle px-2.5 text-xs font-medium text-ink-2";
  return (
    <ul className="flex flex-wrap gap-2">
      <li className={chip}>
        <MapPin aria-hidden className="size-3.5 text-ink-3" />
        {site.district}
      </li>
      <li className={chip}>
        {siteSensorKind(site) === "RAINFALL" ? <CloudRain aria-hidden className="size-3.5 text-telemetry-text" /> : <Waves aria-hidden className="size-3.5 text-telemetry-text" />}
        {SITE_KIND_LABEL[siteSensorKind(site)]}
      </li>
      <li className={chip}>
        <Landmark aria-hidden className="size-3.5 text-ink-3" />
        JPS Station
      </li>
    </ul>
  );
}

function StationBody({ site }: { site: Site }) {
  const predictions = usePredictions();
  const prediction = predictions.data?.predictions.find((p) => p.site_id === site.site_id);
  const wl = sensorOf(site, "WATER_LEVEL");
  const rf = sensorOf(site, "RAINFALL");

  return (
    <div className="grid gap-5 xl:grid-cols-12">
      <CurrentObservation wl={wl} rf={rf} />
      <LocationPanel site={site} wl={wl} />

      <Panel className="xl:col-span-12" aria-labelledby="fg-pred">
        <PanelHeader
          id="fg-pred"
          title="FloodGuard predictions"
          icon={ChartSpline}
          actions={<SourceLabel source="FloodGuard">Model output · Not official warnings</SourceLabel>}
        />
        {prediction ? (
          <PredictionHorizons prediction={prediction} currentLevel={wl?.latest?.water_level_m} />
        ) : predictions.isPending ? (
          <Skeleton className="h-24" />
        ) : (
          <p className="text-sm text-ink-2">
            {predictions.error?.kind === "not_available"
              ? "Predictions are not available yet. They will appear here once the FloodGuard model service is running."
              : predictions.error
                ? "Couldn't load predictions."
                : "This station is not covered by the current model."}
          </p>
        )}
      </Panel>

      <div className="space-y-5 xl:col-span-8">
        {wl && <ChartPanel sensor={wl} prediction={prediction} />}
        {rf && <ChartPanel sensor={rf} />}
      </div>
      <div className="space-y-5 xl:col-span-4">
        <ContributorsPanel prediction={prediction} />
        <DataQualityPanel sensors={site.sensors} />
        <MetadataPanel site={site} />
      </div>
    </div>
  );
}

function LocationPanel({ site, wl }: { site: Site; wl: Sensor | null }) {
  const hasCoords = site.latitude !== null && site.longitude !== null;
  const sites = useMemo(() => [site], [site]);
  return (
    <Panel className="xl:col-span-5" aria-labelledby="loc-title">
      <PanelHeader id="loc-title" title="Location & River" icon={MapPin} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-[3fr_2fr]">
        <div className="relative h-64 overflow-hidden rounded-control border border-line bg-sunken">
          {hasCoords ? (
            <Suspense fallback={<Skeleton className="absolute inset-0 rounded-none" />}>
              <StationMap sites={sites} selectedId={site.site_id} onSelect={() => undefined} interactive={false} mode="3d" className="absolute inset-0" label={`Location of ${site.name}`} />
            </Suspense>
          ) : (
            <EmptyState icon={MapPinOff} title="No verified location" className="h-full py-4" />
          )}
        </div>
        <div className="min-w-0 space-y-3">
          <div className="rounded-control bg-subtle p-3 border border-line/60">
            <p className="text-xs font-medium text-ink-3">Official JPS Threshold State</p>
            <div className="mt-1.5">
              {wl?.official_state ? (
                <>
                  <OfficialStateChip state={wl.official_state} size="lg" />
                  <p className="mt-2 text-xs text-ink-2">{wl.threshold_context ?? OFFICIAL_STATE[wl.official_state].description}</p>
                </>
              ) : (
                <p className="text-xs text-ink-3">{wl ? "Not evaluated (no reading)" : "No official state for rainfall stations"}</p>
              )}
            </div>
          </div>
          <DefinitionList
            items={[
              { term: "Coordinates", icon: MapPin, value: hasCoords ? <span className="text-xs whitespace-nowrap">{`${site.latitude!.toFixed(4)}° N, ${site.longitude!.toFixed(4)}° E`}</span> : "—" },
              ...(site.main_basin ? [{ term: "Basin", icon: Waves, value: site.main_basin }] : []),
              ...(site.sub_basin ? [{ term: "Sub-basin", icon: GitBranch, value: site.sub_basin }] : []),
            ]}
          />
          {site.coordinate_note && <p className="text-xs text-ink-3">{site.coordinate_note}</p>}
        </div>
      </div>
    </Panel>
  );
}

function CurrentObservation({ wl, rf }: { wl: Sensor | null; rf: Sensor | null }) {
  const first = wl ?? rf;
  return (
    <Panel variant="raised" className="xl:col-span-7" aria-labelledby="obs-title">
      <PanelHeader id="obs-title" title="Current observation" qualifier="(JPS)" actions={<SourceLabel source="JPS">Source: JPS</SourceLabel>} />
      <div className="grid gap-4 sm:grid-cols-2">
        {wl && (
          <div className="rounded-control border border-line p-4">
            <Measurement
              label="Water level"
              icon={Waves}
              value={formatMetres(wl.latest?.water_level_m)}
              detail={
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {wl.official_state && <OfficialStateChip state={wl.official_state} />}
                  {wl.latest?.water_level_change_1h_m !== undefined && wl.latest?.water_level_change_1h_m !== null && (
                    <span className="num">{formatSignedMetres(wl.latest.water_level_change_1h_m)} vs 1 h ago</span>
                  )}
                </span>
              }
              freshness={wl.latest?.freshness ?? "NO_DATA"}
              ageMinutes={wl.latest?.age_minutes}
            />
          </div>
        )}
        {rf && (
          <div className="rounded-control border border-line p-4">
            <Measurement
              label="Rainfall (1 h)"
              icon={CloudRain}
              value={formatMm(rf.latest?.rainfall_1h_mm)}
              detail={rf.latest && rf.latest.rainfall_since_midnight_mm !== undefined ? <span className="num">Since midnight {formatMm(rf.latest.rainfall_since_midnight_mm)}</span> : undefined}
              freshness={rf.latest?.freshness ?? "NO_DATA"}
              ageMinutes={rf.latest?.age_minutes}
            />
          </div>
        )}
      </div>

      <section aria-labelledby="thr-title" className="mt-5 border-t border-line pt-4">
        <div className="flex items-center gap-1">
          <h3 id="thr-title" className="flex items-center gap-2 text-md font-semibold text-ink">
            <Landmark aria-hidden className="size-[18px] text-ink-2" />
            Official JPS thresholds
          </h3>
          {wl && wl.thresholds.length > 0 && (
            <InfoTip label="About these thresholds">
              Water-level thresholds published by JPS, captured <TimeLabel iso={wl.thresholds[0]?.captured_at} full />.
            </InfoTip>
          )}
        </div>
        {!wl ? (
          <p className="mt-2 text-xs text-ink-3">JPS publishes no rainfall thresholds for this station.</p>
        ) : wl.thresholds.length === 0 ? (
          <p className="mt-2 text-xs text-ink-3">No thresholds returned for this station.</p>
        ) : (
          <>
            <ThresholdMeter value={wl.latest?.water_level_m} thresholds={wl.thresholds} className="mt-2" />
            {wl.thresholds.some((t) => t.threshold_type === "NORMAL") && (
              <p className="mt-2 flex items-center gap-2 text-xs text-ink-3">
                <OfficialStateChip state="NORMAL" />
                <span className="num font-medium text-ink">{formatMetres(wl.thresholds.find((t) => t.threshold_type === "NORMAL")!.value_m)}</span>
                <span>(Normal reference level)</span>
              </p>
            )}
          </>
        )}
      </section>

      <DefinitionList
        className="mt-5 border-t border-line pt-4"
        items={[
          { term: "Last observation", icon: Clock, value: <TimeLabel iso={first?.latest?.observation_time} full /> },
          { term: "Retrieved by FloodGuard", icon: Database, value: <TimeLabel iso={first?.latest?.retrieved_at} full /> },
        ]}
      />
    </Panel>
  );
}

const RANGES = [
  { value: "24", label: "24 hours" },
  { value: "72", label: "3 days" },
  { value: "168", label: "7 days" },
] as const;

function ChartPanel({ sensor, prediction }: { sensor: Sensor; prediction?: SitePrediction }) {
  const [hours, setHours] = useState<"24" | "72" | "168">("24");
  const series = useObservations(sensor.sensor_id, Number(hours));
  const isLevel = sensor.sensor_type === "WATER_LEVEL";
  const forecast: ForecastPoint[] = useMemo(() => {
    if (!isLevel || !prediction || prediction.status === "UNAVAILABLE" || !prediction.based_on_observation_time) return [];
    const base = Date.parse(prediction.based_on_observation_time);
    return prediction.horizons
      .filter((h) => h.predicted_water_level_m !== null)
      .map((h) => ({ t: new Date(base + h.horizon_minutes * 60_000).toISOString(), value: h.predicted_water_level_m! }));
  }, [isLevel, prediction]);

  return (
    <Panel aria-labelledby={`chart-${sensor.sensor_id}`}>
      <PanelHeader
        id={`chart-${sensor.sensor_id}`}
        title={isLevel ? "Water level history" : "Rainfall history"}
        qualifier="(JPS)"
        icon={isLevel ? Waves : CloudRain}
        actions={<SegmentedControl label="Time range" size="sm" value={hours} onChange={setHours} segments={RANGES.map((r) => ({ ...r }))} />}
      />
      <QueryState query={series} what={`${isLevel ? "Water-level" : "Rainfall"} history`} loading={<Skeleton className="h-64" />}>
        {(data) => <ObservationChart series={data} thresholds={isLevel ? sensor.thresholds : []} forecast={forecast} height={isLevel ? 280 : 200} />}
      </QueryState>
    </Panel>
  );
}

function ContributorsPanel({ prediction }: { prediction?: SitePrediction }) {
  return (
    <CollapsiblePanel title="Model Contributors" icon={TrendingUp} defaultOpen={true}>
      {prediction && prediction.contributors.length > 0 ? (
        <>
          <ul className="divide-y divide-line text-sm">
            {prediction.contributors.slice(0, 5).map((c) => (
              <li key={c.label} className="flex items-center justify-between gap-3 py-2">
                <span className="text-ink">{c.label}</span>
                <span className="text-xs text-ink-3">{c.direction === "INCREASES" ? "Raised risk" : "Lowered risk"}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ink-3">Factors that most influenced this model output. They explain the model, not the cause of flooding.</p>
        </>
      ) : (
        <UnavailableFeature title="No model contributors" description="The API returns contributing factors with each prediction once the model service provides them." />
      )}
    </CollapsiblePanel>
  );
}

function DataQualityPanel({ sensors }: { sensors: Sensor[] }) {
  const primary = sensors.find((s) => s.sensor_type === "WATER_LEVEL") ?? sensors[0];
  const series = useObservations(primary?.sensor_id ?? null, 24);
  const gaps = series.data ? toChartSeries(series.data).gaps.length : null;
  return (
    <CollapsiblePanel title="Data Quality" icon={ShieldCheck} defaultOpen={false}>
      <DefinitionList
        items={[
          ...sensors.map((s) => ({
            term: `${s.sensor_type === "WATER_LEVEL" ? "WL" : "RF"} freshness`,
            icon: Clock,
            value: <FreshnessChip freshness={s.latest?.freshness ?? "NO_DATA"} />,
          })),
          { term: "Age", icon: Clock, value: formatAge(primary?.latest?.age_minutes) },
          { term: "Last received", icon: Calendar, value: primary?.latest?.retrieved_at ? formatDateTime(primary.latest.retrieved_at) : "—" },
          { term: "Missing periods (24 h)", icon: Database, value: gaps === null ? "—" : gaps },
        ]}
      />
    </CollapsiblePanel>
  );
}

function MetadataPanel({ site }: { site: Site }) {
  return (
    <CollapsiblePanel title="Station Details" icon={FileText} defaultOpen={false}>
      <DefinitionList
        items={[
          ...site.sensors.map((s) => ({ term: `Station ID (${s.sensor_type === "WATER_LEVEL" ? "WL" : "RF"})`, icon: Hash, value: s.display_station_id ?? "—" })),
          { term: "District", icon: MapPin, value: site.district },
          { term: "Type", icon: Layers, value: SITE_KIND_LABEL[siteSensorKind(site)] },
          { term: "Operator", icon: Landmark, value: "JPS" },
        ]}
      />
      <div className="mt-3 border-t border-line pt-2.5">
        <dl className="space-y-1 font-mono text-xs text-ink-3">
          <div>
            <dt className="inline text-ink-3">Site ID: </dt>
            <dd className="inline break-all text-ink-2">{site.site_id}</dd>
          </div>
          {site.jps_internal_id && (
            <div>
              <dt className="inline text-ink-3">JPS ID: </dt>
              <dd className="inline text-ink-2">{site.jps_internal_id}</dd>
            </div>
          )}
        </dl>
      </div>
    </CollapsiblePanel>
  );
}
