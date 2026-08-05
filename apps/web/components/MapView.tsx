"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Bbox } from "@/lib/schemas";
import { CUSTOM_DRAW_ZOOM } from "@/lib/aoi";
import { bboxToPolygonFeature, normalizeBbox } from "@/lib/geo";

/** Inline OSM raster style — no external style JSON, attribution always on. */
const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const EMPTY_FC: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

const ACCENT = "#0c5a63";

export interface MapViewProps {
  center: [number, number];
  zoom: number;
  /** Bounding box to display (region or custom AOI). */
  bbox?: Bbox | null;
  /** Enable the two-click rectangle drawing mode. */
  drawEnabled?: boolean;
  /** Called with a normalized [minLon, minLat, maxLon, maxLat] after the second click. */
  onDrawComplete?: (bbox: Bbox) => void;
  /** Called with [lon, lat] whenever the visitor finishes moving the map. */
  onCenterChange?: (center: [number, number]) => void;
  /**
   * Minimum zoom to ease to when drawing is switched on — the config default
   * (~8.5) is far too wide to draw a box of a couple of km² by hand.
   */
  drawZoom?: number;
  ariaLabel: string;
  short?: boolean;
}

/**
 * MapLibre map with an AOI rectangle overlay and a manual two-click
 * rectangle-draw mode: first click anchors corner A, the preview follows the
 * pointer, a second click fixes corner B, Escape cancels. The numeric bbox
 * inputs beside the map remain the keyboard-accessible alternative.
 */
export default function MapView({
  center,
  zoom,
  bbox,
  drawEnabled = false,
  onDrawComplete,
  onCenterChange,
  drawZoom = CUSTOM_DRAW_ZOOM,
  ariaLabel,
  short = false,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [drawing, setDrawing] = useState(false);

  const drawEnabledRef = useRef(drawEnabled);
  const anchorRef = useRef<[number, number] | null>(null);
  const onDrawRef = useRef(onDrawComplete);
  const onCenterRef = useRef(onCenterChange);
  const wasDrawEnabledRef = useRef(false);

  useEffect(() => {
    drawEnabledRef.current = drawEnabled;
    if (!drawEnabled) {
      anchorRef.current = null;
      setDrawing(false);
      const map = mapRef.current;
      if (map && map.isStyleLoaded()) {
        setSourceData(map, "draft", EMPTY_FC);
      }
    }
    const map = mapRef.current;
    if (map) {
      map.getCanvas().style.cursor = drawEnabled ? "crosshair" : "";
    }
  }, [drawEnabled]);

  useEffect(() => {
    onDrawRef.current = onDrawComplete;
  }, [onDrawComplete]);

  useEffect(() => {
    onCenterRef.current = onCenterChange;
  }, [onCenterChange]);

  /**
   * Entering draw mode: zoom in far enough that a ~1.4 km box is easy to draw.
   * Only ever zooms in, only on the transition, and leaves the visitor's own
   * panning and zooming alone afterwards. When an AOI already exists the
   * fitBounds below frames it instead, which is both closer and better placed.
   */
  useEffect(() => {
    if (!mapReady) return;
    const entered = drawEnabled && !wasDrawEnabledRef.current;
    wasDrawEnabledRef.current = drawEnabled;
    const map = mapRef.current;
    if (!entered || !map || bbox) return;
    if (map.getZoom() >= drawZoom) return;
    map.easeTo({ center: map.getCenter(), zoom: drawZoom, duration: 500 });
  }, [drawEnabled, drawZoom, mapReady, bbox]);

  // Initialize the map once.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = new maplibregl.Map({
      container,
      style: OSM_STYLE,
      center,
      zoom,
      attributionControl: { compact: false },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.getCanvas().style.cursor = drawEnabledRef.current ? "crosshair" : "";

    map.on("load", () => {
      map.addSource("aoi", { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "aoi-fill",
        type: "fill",
        source: "aoi",
        paint: { "fill-color": ACCENT, "fill-opacity": 0.08 },
      });
      map.addLayer({
        id: "aoi-line",
        type: "line",
        source: "aoi",
        paint: { "line-color": ACCENT, "line-width": 2 },
      });
      map.addSource("draft", { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "draft-line",
        type: "line",
        source: "draft",
        paint: {
          "line-color": ACCENT,
          "line-width": 2,
          "line-dasharray": [2, 2],
        },
      });
      setMapReady(true);
    });

    map.on("click", (e) => {
      if (!drawEnabledRef.current) return;
      const point: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (!anchorRef.current) {
        anchorRef.current = point;
        setDrawing(true);
        setSourceData(map, "draft", previewFc(point, point));
      } else {
        const box = normalizeBbox([
          anchorRef.current[0],
          anchorRef.current[1],
          point[0],
          point[1],
        ]);
        anchorRef.current = null;
        setDrawing(false);
        setSourceData(map, "draft", EMPTY_FC);
        onDrawRef.current?.(box);
      }
    });

    map.on("moveend", () => {
      const { lng, lat } = map.getCenter();
      onCenterRef.current?.([lng, lat]);
    });

    map.on("mousemove", (e) => {
      if (!drawEnabledRef.current || !anchorRef.current) return;
      setSourceData(
        map,
        "draft",
        previewFc(anchorRef.current, [e.lngLat.lng, e.lngLat.lat]),
      );
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && anchorRef.current) {
        anchorRef.current = null;
        setDrawing(false);
        if (map.isStyleLoaded()) setSourceData(map, "draft", EMPTY_FC);
      }
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      map.remove();
      mapRef.current = null;
    };
    // The map is created exactly once; center/zoom are initial values.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the AOI overlay in sync with the bbox prop.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (bbox) {
      setSourceData(map, "aoi", {
        type: "FeatureCollection",
        features: [bboxToPolygonFeature(bbox)],
      });
      map.fitBounds(
        [
          [bbox[0], bbox[1]],
          [bbox[2], bbox[3]],
        ],
        {
          padding: 48,
          duration: 500,
          // A custom AOI can be a couple of km across; the regional cap would
          // frame it as a dot.
          maxZoom: drawEnabled ? Math.max(drawZoom + 2, 15) : 12,
        },
      );
    } else {
      setSourceData(map, "aoi", EMPTY_FC);
    }
  }, [bbox, mapReady, drawEnabled, drawZoom]);

  return (
    <div className={`map-shell${short ? " map-short" : ""}`}>
      {drawEnabled ? (
        <p className="map-hint" aria-hidden="true">
          {drawing
            ? "Click to set the opposite corner — Esc cancels"
            : "Click the map to set the first corner of your area"}
        </p>
      ) : null}
      <div
        ref={containerRef}
        className="map-container"
        role="application"
        aria-label={ariaLabel}
      />
    </div>
  );
}

function setSourceData(
  map: maplibregl.Map,
  id: string,
  data: GeoJSON.FeatureCollection,
) {
  const source = map.getSource(id);
  if (source && "setData" in source) {
    (source as maplibregl.GeoJSONSource).setData(data);
  }
}

function previewFc(
  a: [number, number],
  b: [number, number],
): GeoJSON.FeatureCollection {
  const box = normalizeBbox([a[0], a[1], b[0], b[1]]);
  return { type: "FeatureCollection", features: [bboxToPolygonFeature(box)] };
}
