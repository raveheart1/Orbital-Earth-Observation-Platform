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

/** Pixel radius within which a click counts as hitting the first vertex. */
const CLOSE_VERTEX_PX = 12;

export type DrawMode = "rectangle" | "polygon";

export interface MapViewProps {
  center: [number, number];
  zoom: number;
  /** Bounding box to display (region or custom AOI). */
  bbox?: Bbox | null;
  /** Drawn-polygon AOI to display; takes precedence over bbox when present. */
  geometry?: GeoJSON.Polygon | null;
  /** Enable the manual drawing mode selected by drawMode. */
  drawEnabled?: boolean;
  /** Which drawing tool is active while drawEnabled. */
  drawMode?: DrawMode;
  /** Called with a normalized [minLon, minLat, maxLon, maxLat] after the second click. */
  onDrawComplete?: (bbox: Bbox) => void;
  /** Called with the ring's distinct [lon, lat] vertices (no closing repeat). */
  onDrawPolygonComplete?: (ring: [number, number][]) => void;
  /** Called with [lon, lat] whenever the visitor finishes moving the map. */
  onCenterChange?: (center: [number, number]) => void;
  /**
   * Minimum zoom to ease to when drawing is switched on — the config default
   * (~8.5) is far too wide to draw a box of a couple of km² by hand.
   */
  drawZoom?: number;
  /**
   * FIRMS active-fire detections to render as a circle layer. Null/absent
   * renders nothing; an empty collection renders nothing. Context only — the
   * map works identically without it.
   */
  fireDetections?: GeoJSON.FeatureCollection | null;
  ariaLabel: string;
  short?: boolean;
}

/**
 * MapLibre map with an AOI overlay (drawn polygon or rectangle) and two manual
 * drawing modes. Rectangle: first click anchors corner A, the preview follows
 * the pointer, a second click fixes corner B. Polygon: each click places a
 * vertex, the dashed preview trails the pointer, and clicking the first vertex
 * (or double-clicking) closes the ring once it has three vertices. Escape
 * cancels either shape in progress. The numeric bbox inputs beside the map
 * remain the keyboard-accessible alternative.
 */
export default function MapView({
  center,
  zoom,
  bbox,
  geometry,
  drawEnabled = false,
  drawMode = "rectangle",
  onDrawComplete,
  onDrawPolygonComplete,
  onCenterChange,
  drawZoom = CUSTOM_DRAW_ZOOM,
  fireDetections = null,
  ariaLabel,
  short = false,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [drawing, setDrawing] = useState(false);

  const drawEnabledRef = useRef(drawEnabled);
  const drawModeRef = useRef(drawMode);
  const anchorRef = useRef<[number, number] | null>(null);
  const verticesRef = useRef<[number, number][]>([]);
  const onDrawRef = useRef(onDrawComplete);
  const onDrawPolygonRef = useRef(onDrawPolygonComplete);
  const onCenterRef = useRef(onCenterChange);
  const wasDrawEnabledRef = useRef(false);

  useEffect(() => {
    drawEnabledRef.current = drawEnabled;
    drawModeRef.current = drawMode;
    // Leaving draw mode or switching tools abandons any half-drawn shape.
    anchorRef.current = null;
    verticesRef.current = [];
    setDrawing(false);
    const map = mapRef.current;
    if (map && map.isStyleLoaded()) {
      setSourceData(map, "draft", EMPTY_FC);
    }
    if (map) {
      map.getCanvas().style.cursor = drawEnabled ? "crosshair" : "";
    }
  }, [drawEnabled, drawMode]);

  // Double-click closes the ring in polygon mode, so the zoom gesture must not
  // fire underneath it.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (drawEnabled && drawMode === "polygon") {
      map.doubleClickZoom.disable();
    } else {
      map.doubleClickZoom.enable();
    }
  }, [drawEnabled, drawMode]);

  useEffect(() => {
    onDrawRef.current = onDrawComplete;
  }, [onDrawComplete]);

  useEffect(() => {
    onDrawPolygonRef.current = onDrawPolygonComplete;
  }, [onDrawPolygonComplete]);

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
    if (!entered || !map || bbox || geometry) return;
    if (map.getZoom() >= drawZoom) return;
    map.easeTo({ center: map.getCenter(), zoom: drawZoom, duration: 500 });
  }, [drawEnabled, drawZoom, mapReady, bbox, geometry]);

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
    if (drawEnabledRef.current && drawModeRef.current === "polygon") {
      map.doubleClickZoom.disable();
    }

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
      map.addLayer({
        id: "draft-vertex",
        type: "circle",
        source: "draft",
        filter: ["==", "$type", "Point"],
        paint: {
          "circle-radius": 5,
          "circle-color": ACCENT,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      map.addSource("fires", { type: "geojson", data: EMPTY_FC });
      map.addLayer({
        id: "fires",
        type: "circle",
        source: "fires",
        filter: ["==", "$type", "Point"],
        paint: {
          "circle-radius": 5,
          // Fire-orange with a white halo; translucent enough that the
          // basemap stays readable under a dense cluster.
          "circle-color": "#e6550d",
          "circle-opacity": 0.75,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
        },
      });
      setMapReady(true);
    });

    const finishPolygon = () => {
      const ring = verticesRef.current;
      verticesRef.current = [];
      setDrawing(false);
      setSourceData(map, "draft", EMPTY_FC);
      onDrawPolygonRef.current?.(ring);
    };

    map.on("click", (e) => {
      if (!drawEnabledRef.current) return;
      const point: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (drawModeRef.current === "polygon") {
        const vertices = verticesRef.current;
        const first = vertices[0];
        // Clicking back on the first vertex closes the ring — but only once
        // there are enough vertices for a polygon.
        if (vertices.length >= 3 && first && withinClosePx(map, first, e.point)) {
          finishPolygon();
          return;
        }
        vertices.push(point);
        setDrawing(true);
        setSourceData(map, "draft", polygonDraftFc(vertices, point));
        return;
      }
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

    map.on("dblclick", (e) => {
      if (!drawEnabledRef.current || drawModeRef.current !== "polygon") return;
      e.preventDefault();
      // The double-click's own two clicks each placed a vertex; the second is
      // a duplicate of the first and is dropped before closing.
      const vertices = verticesRef.current;
      if (vertices.length > 0) vertices.pop();
      if (vertices.length >= 3) {
        finishPolygon();
      } else {
        // Too few vertices to close: keep drawing rather than discard them.
        setDrawing(vertices.length > 0);
        setSourceData(
          map,
          "draft",
          vertices.length > 0 ? polygonDraftFc(vertices, null) : EMPTY_FC,
        );
      }
    });

    map.on("moveend", () => {
      const { lng, lat } = map.getCenter();
      onCenterRef.current?.([lng, lat]);
    });

    map.on("mousemove", (e) => {
      if (!drawEnabledRef.current) return;
      const cursor: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (drawModeRef.current === "polygon") {
        if (verticesRef.current.length === 0) return;
        setSourceData(map, "draft", polygonDraftFc(verticesRef.current, cursor));
        return;
      }
      if (!anchorRef.current) return;
      setSourceData(map, "draft", previewFc(anchorRef.current, cursor));
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (!anchorRef.current && verticesRef.current.length === 0) return;
      anchorRef.current = null;
      verticesRef.current = [];
      setDrawing(false);
      if (map.isStyleLoaded()) setSourceData(map, "draft", EMPTY_FC);
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

  // Keep the fire-detections overlay in sync; toggling or a missing artifact
  // just empties the source.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    setSourceData(map, "fires", fireDetections ?? EMPTY_FC);
  }, [fireDetections, mapReady]);

  // Keep the AOI overlay in sync with the geometry/bbox props; a drawn polygon
  // takes precedence over the rectangle.
  useEffect(() => {    const map = mapRef.current;
    if (!map || !mapReady) return;
    const feature: GeoJSON.Feature<GeoJSON.Polygon> | null = geometry
      ? { type: "Feature", properties: {}, geometry }
      : bbox
        ? bboxToPolygonFeature(bbox)
        : null;
    const bounds = geometry ? polygonBounds(geometry) : (bbox ?? null);
    if (!feature || !bounds) {
      setSourceData(map, "aoi", EMPTY_FC);
      return;
    }
    setSourceData(map, "aoi", {
      type: "FeatureCollection",
      features: [feature],
    });
    map.fitBounds(
      [
        [bounds[0], bounds[1]],
        [bounds[2], bounds[3]],
      ],
      {
        padding: 48,
        duration: 500,
        // A custom AOI can be a couple of km across; the regional cap would
        // frame it as a dot.
        maxZoom: drawEnabled ? Math.max(drawZoom + 2, 15) : 12,
      },
    );
  }, [bbox, geometry, mapReady, drawEnabled, drawZoom]);

  return (
    <div className={`map-shell${short ? " map-short" : ""}`}>
      {drawEnabled ? (
        <p className="map-hint" aria-hidden="true">
          {drawMode === "polygon"
            ? drawing
              ? "Click to place vertices — click the first point to close, Esc cancels"
              : "Click the map to place the first vertex of your outline"
            : drawing
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

/**
 * Dashed preview of an in-progress ring: the placed vertices as points and the
 * path through them, extended to the cursor position when one is known.
 */
function polygonDraftFc(
  vertices: [number, number][],
  cursor: [number, number] | null,
): GeoJSON.FeatureCollection {
  const path = cursor ? [...vertices, cursor] : vertices;
  const features: GeoJSON.Feature[] = vertices.map((vertex) => ({
    type: "Feature",
    properties: {},
    geometry: { type: "Point", coordinates: vertex },
  }));
  if (path.length >= 2) {
    features.push({
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: path },
    });
  }
  return { type: "FeatureCollection", features };
}

/** True when the click landed within CLOSE_VERTEX_PX of the vertex on screen. */
function withinClosePx(
  map: maplibregl.Map,
  vertex: [number, number],
  point: { x: number; y: number },
): boolean {
  const projected = map.project(vertex);
  return Math.hypot(projected.x - point.x, projected.y - point.y) <= CLOSE_VERTEX_PX;
}

/** [minLon, minLat, maxLon, maxLat] over the polygon's exterior ring. */
function polygonBounds(polygon: GeoJSON.Polygon): Bbox | null {
  const ring = polygon.coordinates[0];
  if (!ring || ring.length === 0) return null;
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  for (const position of ring) {
    const [lon, lat] = position;
    if (typeof lon !== "number" || typeof lat !== "number") return null;
    minLon = Math.min(minLon, lon);
    minLat = Math.min(minLat, lat);
    maxLon = Math.max(maxLon, lon);
    maxLat = Math.max(maxLat, lat);
  }
  return [minLon, minLat, maxLon, maxLat];
}
