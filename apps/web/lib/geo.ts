import type { Bbox } from "./schemas";

/**
 * Approximate area of a geographic bounding box in km², using a spherical
 * small-area approximation: one degree of longitude spans ~111.32 km at the
 * equator (scaled by cos of the mid latitude) and one degree of latitude
 * spans ~110.57 km.
 */
export function estimateBboxAreaKm2(bbox: Bbox): number {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const midLatRad = (((minLat + maxLat) / 2) * Math.PI) / 180;
  const widthKm = Math.abs(maxLon - minLon) * 111.32 * Math.cos(midLatRad);
  const heightKm = Math.abs(maxLat - minLat) * 110.57;
  return widthKm * heightKm;
}

/** Order an arbitrary pair of corners into [minLon, minLat, maxLon, maxLat]. */
export function normalizeBbox(bbox: Bbox): Bbox {
  const [aLon, aLat, bLon, bLat] = bbox;
  return [
    Math.min(aLon, bLon),
    Math.min(aLat, bLat),
    Math.max(aLon, bLon),
    Math.max(aLat, bLat),
  ];
}

/** True when the bbox is well-formed and inside valid lon/lat ranges. */
export function bboxIsValid(bbox: Bbox): boolean {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  if (![minLon, minLat, maxLon, maxLat].every(Number.isFinite)) return false;
  if (minLon < -180 || maxLon > 180) return false;
  if (minLat < -90 || maxLat > 90) return false;
  return minLon < maxLon && minLat < maxLat;
}

/** Parse the four bbox text inputs; returns null unless all parse to numbers. */
export function parseBboxInputs(values: {
  minLon: string;
  minLat: string;
  maxLon: string;
  maxLat: string;
}): Bbox | null {
  const parts = [values.minLon, values.minLat, values.maxLon, values.maxLat].map(
    (v) => Number.parseFloat(v),
  );
  if (parts.some((n) => Number.isNaN(n))) return null;
  return parts as unknown as Bbox;
}

/** GeoJSON polygon feature covering a bbox, for MapLibre sources. */
export function bboxToPolygonFeature(bbox: Bbox): GeoJSON.Feature<GeoJSON.Polygon> {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [minLon, minLat],
          [maxLon, minLat],
          [maxLon, maxLat],
          [minLon, maxLat],
          [minLon, minLat],
        ],
      ],
    },
  };
}
