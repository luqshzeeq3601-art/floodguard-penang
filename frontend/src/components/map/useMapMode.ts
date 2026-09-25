import { useEffect, useState } from "react";
import type { MapMode } from "./mode3d";

const KEY = "fg.map.mode";

/** 2D/3D preference, remembered per browser (a convenience; nothing depends on it). */
export function useMapMode(): [MapMode, (m: MapMode) => void] {
  const [mode, setMode] = useState<MapMode>(() => {
    try {
      return localStorage.getItem(KEY) === "2d" ? "2d" : "3d";
    } catch {
      return "3d";
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* storage unavailable */
    }
  }, [mode]);
  return [mode, setMode];
}
