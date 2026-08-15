import type { Artifact } from "./schemas";

/**
 * FIRMS active-fire overlay support. The worker archives fire detections as a
 * GeoJSON artifact when the deployment configures a FIRMS key; most analyses
 * never have one. The overlay is context, not core data — every helper here
 * fails soft (null), so a missing artifact, a fetch failure, or an empty
 * collection simply omits the layer.
 */

/** The archived fire-detections artifact, when the analysis produced one. */
export function findFireDetectionsArtifact(
  artifacts: Artifact[],
): Artifact | null {
  return (
    artifacts.find((a) => a.artifact_type === "fire_detections") ?? null
  );
}

/**
 * Validate a fetched fire-detections payload: a FeatureCollection of Point
 * features (EPSG:4326). Returns null for anything else — and for an empty
 * collection — so the caller just omits the overlay.
 */
export function parseFireDetections(
  data: unknown,
): GeoJSON.FeatureCollection | null {
  if (typeof data !== "object" || data === null) return null;
  const fc = data as GeoJSON.FeatureCollection;
  if (fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) {
    return null;
  }
  const points = fc.features.filter(
    (feature) => feature?.geometry?.type === "Point",
  );
  if (points.length === 0) return null;
  return { type: "FeatureCollection", features: points };
}

/**
 * Caption line for the NBR change panel: the detection count with the caveat
 * that detections are context, never mapped burn perimeters.
 */
export function fireDetectionsCaption(count: number): string {
  const noun = count === 1 ? "detection" : "detections";
  return (
    `${count} FIRMS active-fire ${noun} within this analysis's area and ` +
    "date window (context, not perimeters)."
  );
}
