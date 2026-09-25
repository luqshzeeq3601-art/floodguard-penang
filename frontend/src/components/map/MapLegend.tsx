import { clsx } from "clsx";
import { OFFICIAL_STATE, OFFICIAL_STATES } from "../../lib/status";
import { MarkerGlyph } from "./MarkerGlyph";

const TYPES = [
  { spec: { kind: "WATER_LEVEL", fill: "neutral", muted: false, size: 14 }, label: "Water-level station" },
  { spec: { kind: "RAINFALL", fill: "telemetry", muted: false, size: 12 }, label: "Rainfall station" },
  { spec: { kind: "SHARED", fill: "neutral", muted: false, size: 14 }, label: "Shared site (water level + rainfall)" },
  { spec: { kind: "WATER_LEVEL", fill: "neutral", muted: true, size: 14 }, label: "Not reporting (stale / no data)" },
] as const;

/** Legend for the marker encoding. `inline` renders a single compact row (map overlay). */
export function MapLegend({ inline = false, className }: { inline?: boolean; className?: string }) {
  if (inline) {
    return (
      <ul aria-label="Map legend" className={clsx("flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-2", className)}>
        {TYPES.slice(0, 3).map((t) => (
          <li key={t.label} className="inline-flex items-center gap-1.5">
            <MarkerGlyph spec={t.spec} />
            {t.label.replace(" (water level + rainfall)", "")}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className={clsx("grid gap-5 text-sm sm:grid-cols-2", className)}>
      <div>
        <h3 className="mb-2 text-xs font-medium text-ink-3">Station type (shape)</h3>
        <ul className="space-y-2">
          {TYPES.map((t) => (
            <li key={t.label} className="flex items-center gap-2.5 text-ink-2">
              <span className="inline-flex w-5 justify-center">
                <MarkerGlyph spec={t.spec} />
              </span>
              {t.label}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="mb-2 text-xs font-medium text-ink-3">Official JPS state (water level, fill)</h3>
        <ul className="space-y-2">
          {OFFICIAL_STATES.map((st) => {
            const s = OFFICIAL_STATE[st];
            return (
              <li key={st} className="flex items-center gap-2.5 text-ink-2">
                <span className="inline-flex w-5 justify-center">
                  <MarkerGlyph spec={{ kind: "WATER_LEVEL", fill: s.tone, muted: false, size: 14 + s.rank * 2 }} />
                </span>
                <span lang="ms" className="font-medium text-ink">
                  {s.label}
                </span>
                <span className="text-ink-3">({s.gloss})</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
