"use client";

import { useId, useState } from "react";
import type {
  Analysis,
  AnalysisGrid,
  Artifact,
  NdviLegend,
  TimeseriesPoint,
} from "@/lib/schemas";
import { detectGridMismatch } from "@/lib/grid";
import { bboxRing, extractGeometryRings, type LonLatRing } from "@/lib/geo";
import { findSceneArtifact, selectComparisonPoints } from "@/lib/timeseries";
import { formatDate, formatGranules, formatPct } from "@/lib/format";
import LegendBar from "./LegendBar";

/**
 * AOI outline drawn over a preview. Previews are rasterized exactly to the
 * canonical grid, whose geographic bounds are `grid.bounds_geographic`, so a
 * linear lon/lat → pixel-box mapping is used here. At AOI scale (tens of km)
 * the projection curvature this ignores is far below one preview pixel, so
 * the linear mapping is adequate.
 */
function AoiOverlay({ grid, rings }: { grid: AnalysisGrid; rings: LonLatRing[] }) {
  const [minLon, minLat, maxLon, maxLat] = grid.bounds_geographic;
  if (
    minLon === undefined ||
    minLat === undefined ||
    maxLon === undefined ||
    maxLat === undefined ||
    maxLon <= minLon ||
    maxLat <= minLat
  ) {
    return null;
  }
  const toX = (lon: number) => ((lon - minLon) / (maxLon - minLon)) * grid.width;
  const toY = (lat: number) => ((maxLat - lat) / (maxLat - minLat)) * grid.height;
  return (
    <svg
      className="aoi-overlay"
      viewBox={`0 0 ${grid.width} ${grid.height}`}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
      data-testid="aoi-overlay"
    >
      {rings.map((ring, i) => {
        const points = ring
          .map(([lon, lat]) => `${toX(lon).toFixed(1)},${toY(lat).toFixed(1)}`)
          .join(" ");
        return (
          <g key={i}>
            <polygon
              points={points}
              fill="none"
              stroke="rgba(20, 30, 32, 0.85)"
              strokeWidth={3.5}
              vectorEffect="non-scaling-stroke"
            />
            <polygon
              points={points}
              fill="none"
              stroke="#ffffff"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        );
      })}
    </svg>
  );
}

function PreviewCell({
  artifact,
  alt,
  label,
  point,
  grid,
  rings,
  showAoi,
}: {
  artifact: Artifact | null;
  alt: string;
  label: string;
  point: TimeseriesPoint;
  grid: AnalysisGrid | null;
  rings: LonLatRing[];
  showAoi: boolean;
}) {
  const date = formatDate(point.observed_at);
  // Fixed comparison viewport: with a canonical grid every cell gets the same
  // aspect ratio and images are letterboxed with object-fit: contain — never
  // stretched. Without a grid (legacy analysis) the image keeps its natural
  // ratio, which the legacy note explains.
  const viewportStyle = grid
    ? { aspectRatio: `${grid.width} / ${grid.height}` }
    : undefined;
  return (
    <figure className="compare-cell">
      <div
        className={
          grid ? "compare-viewport compare-viewport--fixed" : "compare-viewport"
        }
        style={viewportStyle}
        data-testid="compare-viewport"
      >
        {artifact ? (
          <img src={artifact.download_url} alt={alt} loading="lazy" />
        ) : (
          <div
            className="compare-missing"
            role="img"
            aria-label={`${alt} (not available)`}
          >
            Preview not available
          </div>
        )}
        {showAoi && grid && rings.length > 0 ? (
          <AoiOverlay grid={grid} rings={rings} />
        ) : null}
      </div>
      <figcaption>
        <span className="compare-title">{label}</span>
        <span className="compare-meta">
          <span>
            Acquired <span className="mono">{date}</span>{" "}
            <span className="muted">(sensing date)</span>
          </span>
          <span>
            AOI coverage{" "}
            <span className="mono">{formatPct(point.aoi_coverage_pct)}</span>
          </span>
          <span>
            Valid pixels{" "}
            <span className="mono">{formatPct(point.valid_pixel_pct)}</span>
          </span>
          <span>{formatGranules(point.granule_count, point.tile_ids)}</span>
        </span>
      </figcaption>
    </figure>
  );
}

/**
 * Before/after comparison for the earliest and latest usable observations:
 * true-color previews on top, NDVI previews below, with the NDVI color
 * legend. All four images render in an identically sized viewport derived
 * from the canonical analysis grid, and a grid-signature check warns loudly
 * if the artifacts were produced on different grids.
 */
export default function ComparePreviews({
  analysis,
  points,
  artifacts,
  legend,
  areaLabel,
}: {
  analysis: Analysis;
  points: TimeseriesPoint[];
  artifacts: Artifact[];
  legend: NdviLegend;
  areaLabel: string;
}) {
  const [showAoi, setShowAoi] = useState(true);
  const toggleId = useId();
  const comparison = selectComparisonPoints(points);
  if (!comparison) {
    return (
      <p className="panel-note">
        A before/after comparison needs at least two usable observations; this
        analysis produced {points.length === 1 ? "only one" : "none"}.
      </p>
    );
  }

  const { first, last } = comparison;
  const firstDate = formatDate(first.observed_at);
  const lastDate = formatDate(last.observed_at);
  const grid = analysis.grid;

  const cells = [
    {
      key: "tc-first",
      artifact: findSceneArtifact(artifacts, first.stac_item_id, "true_color_preview"),
      alt: `True-color Sentinel-2 image of ${areaLabel} acquired ${firstDate}`,
      label: "True color — earliest",
      point: first,
    },
    {
      key: "tc-last",
      artifact: findSceneArtifact(artifacts, last.stac_item_id, "true_color_preview"),
      alt: `True-color Sentinel-2 image of ${areaLabel} acquired ${lastDate}`,
      label: "True color — latest",
      point: last,
    },
    {
      key: "ndvi-first",
      artifact: findSceneArtifact(artifacts, first.stac_item_id, "ndvi_preview"),
      alt: `NDVI map of ${areaLabel} acquired ${firstDate}; greener shades indicate denser, healthier vegetation`,
      label: "NDVI — earliest",
      point: first,
    },
    {
      key: "ndvi-last",
      artifact: findSceneArtifact(artifacts, last.stac_item_id, "ndvi_preview"),
      alt: `NDVI map of ${areaLabel} acquired ${lastDate}; greener shades indicate denser, healthier vegetation`,
      label: "NDVI — latest",
      point: last,
    },
  ];

  const { mismatch, signatures } = detectGridMismatch(
    cells.map((cell) => cell.artifact),
    grid?.signature,
  );

  // AOI outline in WGS84: prefer the request geometry, then the region's,
  // then fall back to the rectangular bbox.
  const rings: LonLatRing[] = (() => {
    const fromAnalysis = extractGeometryRings(analysis.geometry);
    if (fromAnalysis.length > 0) return fromAnalysis;
    const fromRegion = extractGeometryRings(analysis.region?.geometry ?? null);
    if (fromRegion.length > 0) return fromRegion;
    return [bboxRing(analysis.bbox)];
  })();
  const overlayAvailable = grid !== null && rings.length > 0;

  return (
    <div>
      {mismatch ? (
        <div className="alert alert-error" role="alert" style={{ marginBottom: "1rem" }}>
          <p>
            <strong>
              These images were produced on different analytical grids and are
              NOT directly comparable.
            </strong>{" "}
            Pixel extents and statistics may cover different ground.
          </p>
          <p className="small" style={{ marginTop: "0.4rem" }}>
            Grid signatures observed:{" "}
            {signatures.map((sig, i) => (
              <span key={sig}>
                {i > 0 ? " vs " : ""}
                <span className="mono">{sig}</span>
              </span>
            ))}
          </p>
        </div>
      ) : null}

      {grid === null ? (
        <p className="panel-note" style={{ marginBottom: "1rem" }}>
          This analysis predates the canonical-grid guarantee (processing
          v2.0.0), so the images below may cover slightly different ground
          extents and are shown at their natural aspect ratios. Re-run the
          analysis to get observations on a single shared grid.
        </p>
      ) : null}

      {overlayAvailable ? (
        <div className="compare-controls">
          <label className="aoi-toggle" htmlFor={toggleId}>
            <input
              id={toggleId}
              type="checkbox"
              checked={showAoi}
              onChange={(event) => setShowAoi(event.target.checked)}
            />
            Show AOI boundary on previews
          </label>
        </div>
      ) : null}

      <div className="compare-grid">
        {cells.map(({ key, ...cell }) => (
          <PreviewCell
            key={key}
            {...cell}
            grid={grid}
            rings={rings}
            showAoi={showAoi}
          />
        ))}
      </div>

      {analysis.summary?.comparison_note ? (
        <p className="panel-note" style={{ marginTop: "0.75rem" }}>
          {analysis.summary.comparison_note}
        </p>
      ) : null}

      <LegendBar legend={legend} />
    </div>
  );
}
