import { clsx } from "clsx";
import { CircleSlash, TriangleAlert } from "lucide-react";
import type { SitePrediction } from "../../api/types";
import { HORIZONS, horizonOf } from "./horizons";
import { RiskChip } from "../../components/StatusChip";
import { TimeLabel } from "../../components/Measurement";
import { formatAge, formatHorizon, formatMetres, formatProbability, formatSignedMetres } from "../../lib/format";
import { FRESHNESS, RISK } from "../../lib/status";
import { TONE } from "../../lib/tone";

export function UnavailablePrediction({ prediction }: { prediction: SitePrediction }) {
  return (
    <p className="flex items-start gap-2 text-sm text-ink-2">
      <CircleSlash aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-3" />
      <span>
        Prediction unavailable{prediction.unavailable_reason ? ` — ${prediction.unavailable_reason}` : ""}
      </span>
    </p>
  );
}

export function DegradedNote({ prediction }: { prediction: SitePrediction }) {
  if (prediction.status !== "DEGRADED") return null;
  return (
    <p className="flex items-center gap-1.5 text-xs font-medium text-caution-text">
      <TriangleAlert aria-hidden className="size-3.5" />
      Based on {FRESHNESS[prediction.input_freshness].label.toLowerCase()} data ({formatAge(prediction.input_age_minutes)})
    </p>
  );
}

/**
 * Compact 30/60/120-minute comparison. `currentLevel` (API value) lets forecasts show their change
 * from the latest observation; the subtraction is display arithmetic on two API numbers.
 */
export function PredictionHorizons({ prediction, currentLevel, layout = "grid" }: { prediction: SitePrediction; currentLevel?: number | null; layout?: "grid" | "rows" }) {
  if (prediction.status === "UNAVAILABLE") return <UnavailablePrediction prediction={prediction} />;
  return (
    <div className="space-y-2">
      <DegradedNote prediction={prediction} />
      <ul className={clsx(layout === "grid" ? "grid grid-cols-3 gap-2" : "divide-y divide-line")}>
        {HORIZONS.map((h) => {
          const hp = horizonOf(prediction, h);
          const level = hp?.predicted_water_level_m ?? null;
          const delta = level !== null && currentLevel !== null && currentLevel !== undefined ? level - currentLevel : null;
          return (
            <li
              key={h}
              className={clsx(
                layout === "grid" ? "rounded-control border border-dashed border-derived/40 p-2.5" : "grid grid-cols-[4.5rem_1fr] items-center gap-3 py-2.5",
                prediction.status === "DEGRADED" && "opacity-90",
              )}
            >
              <p className="text-xs font-medium text-ink-2">In {formatHorizon(h)}</p>
              {hp ? (
                <div className={clsx(layout === "grid" ? "mt-1 space-y-1" : "grid grid-cols-[auto_1fr_auto] items-center gap-3")}>
                  {level !== null && (
                    <p className="num text-md font-semibold whitespace-nowrap text-ink">
                      {formatMetres(level)}
                      {delta !== null && <span className="ml-1 text-xs font-normal whitespace-nowrap text-ink-3">{formatSignedMetres(delta)}</span>}
                    </p>
                  )}
                  <div title="Model estimate of threshold escalation within the horizon">
                    <p className="num text-sm text-ink-2">
                      {formatProbability(hp.risk_probability)} <span className={clsx("text-xs text-ink-3", layout === "rows" && "sr-only")}>probability</span>
                    </p>
                    <div aria-hidden className="mt-1 h-1 overflow-hidden rounded-full bg-sunken">
                      <div className={clsx("h-full rounded-full", TONE[RISK[hp.risk_level].tone].bar)} style={{ width: `${Math.round(hp.risk_probability * 100)}%` }} />
                    </div>
                  </div>
                  <RiskChip level={hp.risk_level} compact />
                </div>
              ) : (
                <p className="mt-1 text-sm text-ink-3">Not predicted</p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-ink-3">
        <TimeLabel iso={prediction.generated_at} prefix="Generated" /> · <TimeLabel iso={prediction.based_on_observation_time} prefix="based on obs" /> · model{" "}
        <span className="font-mono">{prediction.model_version}</span>
      </p>
    </div>
  );
}
