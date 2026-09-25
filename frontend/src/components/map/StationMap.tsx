import { useEffect, useMemo, useRef, useState } from "react";
import { LngLatBounds, Map as MlMap, Marker, NavigationControl, Popup, setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { clsx } from "clsx";
import type { Site } from "../../api/types";
import { formatTime } from "../../lib/format";
import { FRESHNESS, OFFICIAL_STATE, siteFreshness, siteOfficialState } from "../../lib/status";
import { markerBodyClass, markerSpec, sensorLabel, SHARED_BADGE_CLASS } from "./markerStyle";
import { apply3d, type MapMode } from "./mode3d";

const STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL ?? "";
// MapLibre resolves its worker relative to its own module, which bundling breaks; point it at the bundled worker.
setWorkerUrl(workerUrl);

/** Used when no basemap is configured: markers on a plain background, never a fake basemap. */
const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2f6" } }],
};

export interface StationMapProps {
  sites: Site[];
  selectedId: string | null;
  onSelect: (siteId: string) => void;
  className?: string;
  /** Static snippet (station detail): no controls, no interaction. */
  interactive?: boolean;
  label?: string;
  /** `3d` tilts the camera and adds terrain/building context when the basemap supports it. */
  mode?: MapMode;
}

export default function StationMap({ sites, selectedId, onSelect, className, interactive = true, label = "Map of Pulau Pinang monitoring stations", mode = "2d" }: StationMapProps) {
  const [loaded, setLoaded] = useState(false);
  const modeRef = useRef(mode);
  const easedTo = useRef<string | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; el: HTMLButtonElement }>());
  const popup = useRef<Popup | null>(null);
  const fitted = useRef(false);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  const located = useMemo(() => sites.filter((s) => s.latitude !== null && s.longitude !== null), [sites]);

  useEffect(() => {
    if (!container.current) return;
    const m = new MlMap({
      container: container.current,
      style: STYLE_URL || BLANK_STYLE,
      center: [100.35, 5.35],
      zoom: 9.6,
      attributionControl: { compact: true, customAttribution: "Station data: JPS Public Infobanjir" },
      interactive,
      cooperativeGestures: interactive ? window.matchMedia("(pointer: coarse)").matches : false,
    });
    if (interactive) {
      m.addControl(new NavigationControl({ showCompass: false }), "top-left");
    }
    popup.current = new Popup({ closeButton: false, closeOnClick: false, offset: 14, maxWidth: "260px" });
    // style.load fires before tiles, so markers and camera are ready without waiting for the network.
    m.once("style.load", () => {
      apply3d(m, modeRef.current, false);
      setLoaded(true);
    });
    map.current = m;
    const registry = markers.current;
    return () => {
      registry.clear();
      m.remove();
      map.current = null;
      fitted.current = false;
    };
  }, [interactive]);

  useEffect(() => {
    modeRef.current = mode;
    const m = map.current;
    if (m && loaded) apply3d(m, mode, true);
  }, [mode, loaded]);

  // Rebuild markers when data changes; the map instance itself is kept across polls.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const registry = markers.current;
    for (const { marker } of registry.values()) marker.remove();
    registry.clear();

    for (const site of located) {
      const spec = markerSpec(site);
      const el = document.createElement("button");
      el.setAttribute("data-map-marker", "");
      el.type = "button";
      el.setAttribute("aria-label", spec.label);
      el.className = "group grid size-7 place-items-center rounded-full focus-visible:outline-2 focus-visible:outline-primary";
      el.tabIndex = interactive ? 0 : -1;
      const body = document.createElement("span");
      body.className = markerBodyClass(spec);
      body.style.width = body.style.height = `${spec.size}px`;
      if (spec.kind === "SHARED") {
        const badge = document.createElement("span");
        badge.className = SHARED_BADGE_CLASS;
        body.appendChild(badge);
      }
      el.appendChild(body);
      if (interactive) {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          onSelectRef.current(site.site_id);
        });
        const show = () => showPopup(m, popup.current!, site);
        el.addEventListener("mouseenter", show);
        el.addEventListener("focus", show);
        el.addEventListener("mouseleave", () => popup.current?.remove());
        el.addEventListener("blur", () => popup.current?.remove());
      }
      const marker = new Marker({ element: el }).setLngLat([site.longitude!, site.latitude!]).addTo(m);
      registry.set(site.site_id, { marker, el });
    }

    if (!fitted.current && located.length > 0) {
      const bounds = new LngLatBounds();
      located.forEach((s) => bounds.extend([s.longitude!, s.latitude!]));
      m.fitBounds(bounds, { padding: located.length === 1 ? 0 : 40, maxZoom: 13, duration: 0 });
      fitted.current = true;
    }
  }, [located, interactive]);

  // Selection ring + bring into view.
  useEffect(() => {
    for (const [id, { el }] of markers.current) {
      markSelected(el, id === selectedId);
    }
    const m = map.current;
    const sel = located.find((s) => s.site_id === selectedId);
    // Move the camera only when the selection itself changes, not on every data poll.
    if (m && sel && interactive && easedTo.current !== selectedId) {
      easedTo.current = selectedId;
      const ll: [number, number] = [sel.longitude!, sel.latitude!];
      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      m.easeTo({ center: ll, zoom: Math.max(m.getZoom(), 11), duration: still ? 0 : 500 });
    }
  }, [selectedId, located, interactive]);

  // MapLibre's unlayered CSS forces `position: relative` on its container, so sizing lives on a wrapper.
  return (
    <div role="region" aria-label={label} aria-busy={!loaded} className={clsx("overflow-hidden", className ?? "relative")}>
      <div ref={container} className="h-full w-full" />
      {!loaded && <div aria-hidden className="absolute inset-0 animate-pulse bg-sunken" />}
    </div>
  );
}

function showPopup(m: MlMap, p: Popup, site: Site) {
  const box = document.createElement("div");
  box.className = "text-sm";
  const name = document.createElement("p");
  name.className = "font-semibold text-ink";
  name.textContent = site.name;
  const meta = document.createElement("p");
  meta.className = "text-xs text-ink-2";
  const state = siteOfficialState(site);
  const fresh = FRESHNESS[siteFreshness(site)].label;
  const obs = site.sensors.map((s) => s.latest?.observation_time).find(Boolean);
  meta.textContent = [
    site.district,
    sensorLabel(markerSpec(site).kind),
    state ? `JPS ${OFFICIAL_STATE[state].label}` : null,
    `${fresh}${obs ? ` · Obs ${formatTime(obs)}` : ""}`,
  ]
    .filter(Boolean)
    .join(" · ");
  box.append(name, meta);
  p.setLngLat([site.longitude!, site.latitude!]).setDOMContent(box).addTo(m);
}

function markSelected(el: HTMLButtonElement, selected: boolean) {
  el.setAttribute("aria-pressed", String(selected));
  el.style.zIndex = selected ? "3" : "";
  el.firstElementChild?.classList.toggle("ring-2", selected);
  el.firstElementChild?.classList.toggle("ring-primary", selected);
  el.firstElementChild?.classList.toggle("ring-offset-2", selected);
}
