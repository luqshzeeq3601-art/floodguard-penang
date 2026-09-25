import { Box, Square } from "lucide-react";
import { SegmentedControl } from "../Controls";
import type { MapMode } from "./mode3d";

export function MapModeToggle({ mode, onChange, className }: { mode: MapMode; onChange: (m: MapMode) => void; className?: string }) {
  return (
    <SegmentedControl
      label="Map view"
      size="sm"
      value={mode}
      onChange={onChange}
      className={className ?? "bg-surface shadow-pop"}
      segments={[
        { value: "2d", label: "2D", icon: Square },
        { value: "3d", label: "3D", icon: Box },
      ]}
    />
  );
}
