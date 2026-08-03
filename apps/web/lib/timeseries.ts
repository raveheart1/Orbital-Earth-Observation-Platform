import type { Artifact, ArtifactType, TimeseriesPoint } from "./schemas";

/** A timeseries point reshaped for the recharts chart and the data table. */
export interface ChartPoint {
  /** Epoch ms of the observation — the numeric x value (true time axis). */
  t: number;
  /** YYYY-MM-DD label. */
  date: string;
  stacItemId: string;
  mean: number | null;
  median: number | null;
  p25: number | null;
  p75: number | null;
  /** [p25, p75] range for the shaded band; null when either is missing. */
  band: [number, number] | null;
  validPixelPct: number;
  cloudPct: number | null;
  /** Geometric AOI coverage by the source granules (null on legacy points). */
  aoiCoveragePct: number | null;
  /** Number of source granules mosaicked into this observation. */
  granuleCount: number;
  tileIds: string[];
}

/**
 * Transform API timeseries points into chart rows: sorted by observation
 * time ascending, with a numeric time axis and a p25–p75 band.
 */
export function toChartPoints(points: TimeseriesPoint[]): ChartPoint[] {
  return [...points]
    .sort(
      (a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at),
    )
    .map((p) => ({
      t: Date.parse(p.observed_at),
      date: p.observed_at.slice(0, 10),
      stacItemId: p.stac_item_id,
      mean: p.ndvi_mean,
      median: p.ndvi_median,
      p25: p.ndvi_p25,
      p75: p.ndvi_p75,
      band:
        p.ndvi_p25 !== null && p.ndvi_p75 !== null
          ? ([p.ndvi_p25, p.ndvi_p75] as [number, number])
          : null,
      validPixelPct: p.valid_pixel_pct,
      cloudPct: p.stac_cloud_cover_pct,
      aoiCoveragePct: p.aoi_coverage_pct,
      granuleCount: p.granule_count,
      tileIds: p.tile_ids,
    }));
}

/**
 * Earliest and latest usable observations (a scene is usable exactly when it
 * appears in the timeseries). Returns null when fewer than two observations
 * exist, since a before/after comparison needs both ends.
 */
export function selectComparisonPoints(
  points: TimeseriesPoint[],
): { first: TimeseriesPoint; last: TimeseriesPoint } | null {
  if (points.length < 2) return null;
  const sorted = [...points].sort(
    (a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at),
  );
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (!first || !last) return null;
  return { first, last };
}

/** Find an artifact of a given type belonging to a STAC item. */
export function findSceneArtifact(
  artifacts: Artifact[],
  stacItemId: string,
  type: ArtifactType,
): Artifact | null {
  return (
    artifacts.find(
      (a) => a.stac_item_id === stacItemId && a.artifact_type === type,
    ) ?? null
  );
}
