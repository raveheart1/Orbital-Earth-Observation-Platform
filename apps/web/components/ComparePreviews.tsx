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
import { operationUi } from "@/lib/operations";
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
export function AoiOverlay({
  grid,
  rings,
}: {
  grid: AnalysisGrid;
  rings: LonLatRing[];
}) {
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

/**
 * AOI outline rings in WGS84: prefer the request geometry, then the region's,
 * then fall back to the rectangular bbox.
 */
export function analysisAoiRings(analysis: Analysis): LonLatRing[] {
  const fromAnalysis = extractGeometryRings(analysis.geometry);
  if (fromAnalysis.length > 0) return fromAnalysis;
  const fromRegion = extractGeometryRings(analysis.region?.geometry ?? null);
  if (fromRegion.length > 0) return fromRegion;
  return [bboxRing(analysis.bbox)];
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
 * Swipe comparison: the earliest and latest previews of one kind stacked in
 * a single fixed-aspect viewport, with the earliest (left) layer clipped at
 * a draggable divider via CSS clip-path. The divider itself is a full-size
 * `<input type=range>`, so it is keyboard-operable (arrow keys) and needs no
 * pointer-event bookkeeping of our own. Only offered on canonical-grid
 * analyses: both layers are guaranteed to cover identical ground, which is
 * exactly what makes overlaying them meaningful.
 */
function SwipeViewport({
  before,
  after,
  beforeAlt,
  afterAlt,
  beforeDate,
  afterDate,
  grid,
  rings,
  showAoi,
  position,
  onPositionChange,
}: {
  before: Artifact | null;
  after: Artifact | null;
  beforeAlt: string;
  afterAlt: string;
  beforeDate: string;
  afterDate: string;
  grid: AnalysisGrid;
  rings: LonLatRing[];
  showAoi: boolean;
  position: number;
  onPositionChange: (value: number) => void;
}) {
  return (
    <figure className="swipe-frame">
      <div
        className="swipe-viewport"
        style={{ aspectRatio: `${grid.width} / ${grid.height}` }}
        data-testid="swipe-viewport"
      >
        {after ? (
          <img src={after.download_url} alt={afterAlt} />
        ) : (
          <div
            className="compare-missing"
            role="img"
            aria-label={`${afterAlt} (not available)`}
          >
            Preview not available
          </div>
        )}
        {before ? (
          <img
            src={before.download_url}
            alt={beforeAlt}
            style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
          />
        ) : (
          <div
            className="compare-missing"
            role="img"
            aria-label={`${beforeAlt} (not available)`}
            style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
          >
            Preview not available
          </div>
        )}
        {showAoi && rings.length > 0 ? (
          <AoiOverlay grid={grid} rings={rings} />
        ) : null}
        <span className="swipe-label swipe-label--left">
          <span className="mono">{beforeDate}</span> earliest
        </span>
        <span className="swipe-label swipe-label--right">
          <span className="mono">{afterDate}</span> latest
        </span>
        <div
          className="swipe-divider"
          style={{ left: `${position}%` }}
          aria-hidden="true"
        />
        <input
          className="swipe-range"
          type="range"
          min={0}
          max={100}
          step={1}
          value={position}
          onChange={(event) => onPositionChange(Number(event.target.value))}
          aria-label={`Comparison divider: percentage of the view showing the earliest observation (${beforeDate}) instead of the latest (${afterDate})`}
        />
      </div>
      <figcaption className="small muted" style={{ marginTop: "0.35rem" }}>
        Drag the divider — or focus it and use the arrow keys — to sweep
        between the <span className="mono">{beforeDate}</span> (left) and{" "}
        <span className="mono">{afterDate}</span> (right) observations.
      </figcaption>
    </figure>
  );
}

/**
 * Before/after comparison for the earliest and latest usable observations:
 * true-color previews on top, index previews (NDVI, NBR, …) below, with the
 * color legend. All four images render in an identically sized viewport derived
 * from the canonical analysis grid, and a grid-signature check warns loudly
 * if the artifacts were produced on different grids.
 *
 * A slider mode overlays the earliest and latest previews of one kind in a
 * single viewport. It is disabled on a grid-signature mismatch (overlaying
 * images of different ground would be actively misleading) and unavailable
 * for legacy grid-null analyses, which fall back to side-by-side.
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
  const [mode, setMode] = useState<"side-by-side" | "slider">("side-by-side");
  const [sliderKind, setSliderKind] = useState<"index" | "true_color">("index");
  const [sliderPosition, setSliderPosition] = useState(50);
  const toggleId = useId();
  const modeName = useId();
  const kindName = useId();
  const comparison = selectComparisonPoints(points);
  if (!comparison) {
    return (
      <p className="panel-note">
        A before/after comparison needs at least two usable observations; this
        analysis produced {points.length === 1 ? "only one" : "none"}.
      </p>
    );
  }

  const op = operationUi(analysis.processing.operation);
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
      key: "index-first",
      artifact: findSceneArtifact(artifacts, first.stac_item_id, op.previewArtifactType),
      alt: `${op.name} map of ${areaLabel} acquired ${firstDate}; ${op.previewAltHint}`,
      label: `${op.name} — earliest`,
      point: first,
    },
    {
      key: "index-last",
      artifact: findSceneArtifact(artifacts, last.stac_item_id, op.previewArtifactType),
      alt: `${op.name} map of ${areaLabel} acquired ${lastDate}; ${op.previewAltHint}`,
      label: `${op.name} — latest`,
      point: last,
    },
  ];

  const { mismatch, signatures } = detectGridMismatch(
    cells.map((cell) => cell.artifact),
    grid?.signature,
  );

  const rings = analysisAoiRings(analysis);
  const overlayAvailable = grid !== null && rings.length > 0;

  // The slider needs the canonical-grid guarantee (legacy analyses fall back
  // to side-by-side without offering it) and is disabled — alongside the loud
  // warning above — when the artifacts disagree on their grid.
  const sliderOffered = grid !== null;
  const sliderMode = mode === "slider" && sliderOffered && !mismatch;
  const sliderKeys =
    sliderKind === "index" ? ["index-first", "index-last"] : ["tc-first", "tc-last"];
  const [sliderBefore, sliderAfter] = sliderKeys.map(
    (key) => cells.find((cell) => cell.key === key) ?? null,
  );

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

      {sliderOffered || overlayAvailable ? (
        <div className="compare-controls">
          {sliderOffered ? (
            <div
              className="mode-toggle"
              role="radiogroup"
              aria-label="Comparison mode"
            >
              <label>
                <input
                  type="radio"
                  name={modeName}
                  value="side-by-side"
                  checked={!sliderMode}
                  onChange={() => setMode("side-by-side")}
                />
                Side by side
              </label>
              <label>
                <input
                  type="radio"
                  name={modeName}
                  value="slider"
                  checked={sliderMode}
                  onChange={() => setMode("slider")}
                  disabled={mismatch}
                />
                Slider
              </label>
            </div>
          ) : null}
          {sliderMode ? (
            <div
              className="mode-toggle"
              role="radiogroup"
              aria-label="Slider imagery"
            >
              <label>
                <input
                  type="radio"
                  name={kindName}
                  value="index"
                  checked={sliderKind === "index"}
                  onChange={() => setSliderKind("index")}
                />
                {op.name}
              </label>
              <label>
                <input
                  type="radio"
                  name={kindName}
                  value="true_color"
                  checked={sliderKind === "true_color"}
                  onChange={() => setSliderKind("true_color")}
                />
                True color
              </label>
            </div>
          ) : null}
          {overlayAvailable ? (
            <label className="aoi-toggle" htmlFor={toggleId}>
              <input
                id={toggleId}
                type="checkbox"
                checked={showAoi}
                onChange={(event) => setShowAoi(event.target.checked)}
              />
              Show AOI boundary on previews
            </label>
          ) : null}
        </div>
      ) : null}

      {sliderMode && grid !== null ? (
        <SwipeViewport
          before={sliderBefore?.artifact ?? null}
          after={sliderAfter?.artifact ?? null}
          beforeAlt={sliderBefore?.alt ?? ""}
          afterAlt={sliderAfter?.alt ?? ""}
          beforeDate={firstDate}
          afterDate={lastDate}
          grid={grid}
          rings={rings}
          showAoi={showAoi && overlayAvailable}
          position={sliderPosition}
          onPositionChange={(value) =>
            setSliderPosition(Math.min(100, Math.max(0, Math.round(value))))
          }
        />
      ) : (
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
      )}

      {analysis.summary?.comparison_note ? (
        <p className="panel-note" style={{ marginTop: "0.75rem" }}>
          {analysis.summary.comparison_note}
        </p>
      ) : null}

      <LegendBar legend={legend} />
    </div>
  );
}
