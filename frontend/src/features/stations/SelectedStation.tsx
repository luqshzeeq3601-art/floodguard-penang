import { ArrowLeft, ArrowRight, CloudRain, Info, Waves } from "lucide-react";
import type { Site, SitePrediction } from "../../api/types";
import type { ApiError } from "../../api/client";
import { IconButton, TextLink } from "../../components/Button";
import { Measurement } from "../../components/Measurement";
import { OfficialStateChip, SourceLabel } from "../../components/StatusChip";
import { EmptyState } from "../../components/States";
import { formatMetres, formatMm } from "../../lib/format";
import { sensorOf } from "../../lib/status";
import { PredictionHorizons } from "../predictions/PredictionHorizons";
import { SiteType } from "./StationsTable";

interface Props {
  site: Site | null;
  prediction: SitePrediction | undefined;
  predictionsError: ApiError | null;
  predictionsLoading: boolean;
  onClose: () => void;
}

/** Selected-station rail: JPS observed block and FloodGuard block, always separated. */
export function SelectedStation({ site, prediction, predictionsError, predictionsLoading, onClose }: Props) {
  if (!site) {
    return <EmptyState icon={Info} title="No station selected" description="Select a marker on the map or a row in the list to see its latest readings." />;
  }
  const wl = sensorOf(site, "WATER_LEVEL");
  const rf = sensorOf(site, "RAINFALL");
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-ink">{site.name}</h2>
          <p className="text-sm text-ink-2">{site.district}</p>
        </div>
        <IconButton icon={ArrowLeft} label="Back to station list" onClick={onClose} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <SiteType site={site} />
        {wl?.official_state && <OfficialStateChip state={wl.official_state} />}
      </div>

      <section aria-labelledby="sel-observed" className="mt-5 border-t border-line pt-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 id="sel-observed" className="text-md font-semibold text-ink">
            JPS observed data
          </h3>
          <SourceLabel source="JPS">Source: JPS</SourceLabel>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
          {wl && (
            <Measurement
              label="Water level"
              icon={Waves}
              value={formatMetres(wl.latest?.water_level_m)}
              observationTime={wl.latest?.observation_time ?? null}
              freshness={wl.latest?.freshness ?? "NO_DATA"}
              ageMinutes={wl.latest?.age_minutes}
              detail={wl.threshold_context}
              size="md"
            />
          )}
          {rf && (
            <Measurement
              label="Rainfall (1 h)"
              icon={CloudRain}
              value={formatMm(rf.latest?.rainfall_1h_mm)}
              observationTime={rf.latest?.observation_time ?? null}
              freshness={rf.latest?.freshness ?? "NO_DATA"}
              ageMinutes={rf.latest?.age_minutes}
              detail={rf.latest?.rainfall_since_midnight_mm !== undefined ? `Since midnight ${formatMm(rf.latest?.rainfall_since_midnight_mm)}` : undefined}
              size="md"
            />
          )}
        </div>
      </section>

      <section aria-labelledby="sel-fg" className="mt-5 border-t border-line pt-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 id="sel-fg" className="text-md font-semibold text-ink">
            FloodGuard predictions
          </h3>
          <SourceLabel source="FloodGuard">Model output</SourceLabel>
        </div>
        {prediction ? (
          <PredictionHorizons prediction={prediction} currentLevel={wl?.latest?.water_level_m} layout="rows" />
        ) : (
          <p className="text-sm text-ink-3">
            {predictionsLoading
              ? "Loading predictions…"
              : predictionsError?.kind === "not_available"
                ? "Predictions are not available yet."
                : predictionsError
                  ? "Couldn't load predictions."
                  : "No prediction for this station."}
          </p>
        )}
        <p className="mt-2 text-xs text-ink-3">Not an official JPS warning.</p>
      </section>

      <div className="mt-5 border-t border-line pt-4">
        <TextLink to={`/stations/${encodeURIComponent(site.site_id)}`} iconEnd={ArrowRight}>
          View details
        </TextLink>
      </div>
    </div>
  );
}
