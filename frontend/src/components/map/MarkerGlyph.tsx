import { clsx } from "clsx";
import { markerBodyClass, SHARED_BADGE_CLASS, type MarkerSpec } from "./markerStyle";

export function MarkerGlyph({ spec, className }: { spec: Pick<MarkerSpec, "kind" | "fill" | "muted" | "size">; className?: string }) {
  return (
    <span aria-hidden className={clsx(markerBodyClass(spec), className)} style={{ width: spec.size, height: spec.size }}>
      {spec.kind === "SHARED" && <span className={SHARED_BADGE_CLASS} />}
    </span>
  );
}
