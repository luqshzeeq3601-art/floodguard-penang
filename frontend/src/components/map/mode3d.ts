import type { Map as MlMap } from "maplibre-gl";

export type MapMode = "2d" | "3d";

/** Optional raster-dem tiles (Terrarium encoding), e.g. AWS Terrain Tiles. Empty = no terrain. */
const TERRAIN_URL = import.meta.env.VITE_TERRAIN_URL ?? "";
const TERRAIN_ATTRIBUTION = import.meta.env.VITE_TERRAIN_ATTRIBUTION ?? "Elevation: Terrain Tiles";

const DEM = "fg-dem";
const HILLSHADE = "fg-hillshade";
const BUILDINGS = "fg-buildings-3d";
const PITCH = 50;
const BEARING = -15;

/**
 * Switches the map between flat and tilted views. 3D adds terrain + hillshade when VITE_TERRAIN_URL
 * is set and extruded buildings when the basemap has a `building` layer; otherwise it only tilts.
 * Context layers only — station data is never extruded (no 3D charts).
 */
export function apply3d(m: MlMap, mode: MapMode, animate: boolean) {
  const style = m.getStyle();
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const duration = animate && !still ? 600 : 0;

  if (mode === "3d") {
    if (TERRAIN_URL && !m.getSource(DEM)) {
      m.addSource(DEM, { type: "raster-dem", tiles: [TERRAIN_URL], encoding: "terrarium", tileSize: 256, maxzoom: 14, attribution: TERRAIN_ATTRIBUTION });
      const firstSymbol = style.layers.find((l) => l.type === "symbol")?.id;
      m.addLayer(
        { id: HILLSHADE, type: "hillshade", source: DEM, paint: { "hillshade-shadow-color": "#94a3b8", "hillshade-exaggeration": 0.35 } },
        firstSymbol,
      );
    }
    if (m.getSource(DEM)) m.setTerrain({ source: DEM, exaggeration: 1.3 });

    const building = style.layers.find((l) => "source-layer" in l && l["source-layer"] === "building");
    if (building && "source" in building && !m.getLayer(BUILDINGS)) {
      m.addLayer({
        id: BUILDINGS,
        type: "fill-extrusion",
        source: building.source,
        "source-layer": "building",
        minzoom: 13,
        paint: {
          "fill-extrusion-color": "#dde3ec",
          "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
          "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
          "fill-extrusion-opacity": 0.75,
        },
      });
    }
    setVisible(m, [HILLSHADE, BUILDINGS], true);
    m.easeTo({ pitch: PITCH, bearing: BEARING, duration });
  } else {
    if (m.getTerrain()) m.setTerrain(null);
    setVisible(m, [HILLSHADE, BUILDINGS], false);
    m.easeTo({ pitch: 0, bearing: 0, duration });
  }
}

function setVisible(m: MlMap, ids: string[], visible: boolean) {
  for (const id of ids) if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
}
