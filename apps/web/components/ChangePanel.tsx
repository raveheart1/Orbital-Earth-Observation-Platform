"use client";

import { useId, useState } from "react";
import type { Analysis, Artifact } from "@/lib/schemas";
import { fireDetectionsCaption } from "@/lib/fires";
import { formatChange, formatDate, formatPct } from "@/lib/format";
import { operationUi } from "@/lib/operations";
import { AoiOverlay, analysisAoiRings } from "./ComparePreviews";
import ChangeLegendBar from "./ChangeLegendBar";

/**
 * Per-pixel index change (ΔNDVI, ΔNBR, …) between the earliest and latest
 * usable observations: the change-map preview (both dates lie on the
 * canonical grid, so the subtraction is defined pixel-for-pixel), a diverging
 * legend centered at zero, and the change statistics in plain language.
 * Renders nothing when the analysis has neither a computed change block nor a
 * change preview — older analyses simply never see this section.
 */
export default function ChangePanel({
  analysis,
  artifacts,
  areaLabel,
  fireDetectionCount = null,
}: {
  analysis: Analysis;
  artifacts: Artifact[];
  areaLabel: string;
  /**
   * FIRMS active-fire detections archived with this run, when known. Shown as
   * a context line on NBR analyses only.
   */
  fireDetectionCount?: number | null;
}) {
  const [showAoi, setShowAoi] = useState(true);
  const toggleId = useId();
  const op = operationUi(analysis.processing.operation);
  const change = analysis.summary?.change;
  const preview =
    artifacts.find((a) => a.artifact_type === op.changePreviewArtifactType) ?? null;
  if (!change?.computed && !preview) return null;

  const grid = analysis.grid;
  const rings = analysisAoiRings(analysis);
  const overlayAvailable = grid !== null && rings.length > 0;
  const stats = change?.stats;
  const threshold = change?.delta_threshold;
  const earlierDate = formatDate(change?.earlier?.observed_at);
  const laterDate = formatDate(change?.later?.observed_at);
  const viewportStyle = grid
    ? { aspectRatio: `${grid.width} / ${grid.height}` }
    : undefined;
  const alt =
    `Per-pixel ${op.name} change map of ${areaLabel} between ${earlierDate} and ` +
    `${laterDate}; ${op.changeAltHint}`;

  return (
    <div>
      {overlayAvailable ? (
        <div className="compare-controls">
          <label className="aoi-toggle" htmlFor={toggleId}>
            <input
              id={toggleId}
              type="checkbox"
              checked={showAoi}
              onChange={(event) => setShowAoi(event.target.checked)}
            />
            Show AOI boundary on the change map
          </label>
        </div>
      ) : null}

      <figure className="compare-cell change-figure">
        <div
          className={
            grid ? "compare-viewport compare-viewport--fixed" : "compare-viewport"
          }
          style={viewportStyle}
          data-testid="change-viewport"
        >
          {preview ? (
            <img src={preview.download_url} alt={alt} loading="lazy" />
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
          <span className="compare-title">
            Δ{op.name} — <span className="mono">{earlierDate}</span> →{" "}
            <span className="mono">{laterDate}</span>
          </span>
          {stats ? (
            <span className="compare-meta" data-testid="change-stats">
              <span>
                Between <span className="mono">{earlierDate}</span> and{" "}
                <span className="mono">{laterDate}</span>: mean Δ{op.name}{" "}
                <span className="mono">{formatChange(stats.delta_mean)}</span>
              </span>
              <span>
                <span className="mono">{formatPct(stats.pct_increased)}</span>{" "}
                of observed area {op.changeIncreaseLabel} (Δ &gt;{" "}
                <span className="mono">{formatChange(threshold, 2)}</span>)
              </span>
              <span>
                <span className="mono">{formatPct(stats.pct_decreased)}</span>{" "}
                {op.changeDecreaseLabel} (Δ &lt;{" "}
                <span className="mono">
                  {formatChange(threshold === undefined ? undefined : -threshold, 2)}
                </span>
                )
              </span>
              <span>
                <span className="mono">{formatPct(stats.valid_both_pct)}</span>{" "}
                of the AOI observed cloud-free on both dates
              </span>
            </span>
          ) : null}
        </figcaption>
      </figure>

      {change?.display_range !== undefined ? (
        <ChangeLegendBar displayRange={change.display_range} op={op} />
      ) : null}

      {op.id === "nbr" && fireDetectionCount !== null ? (
        <p className="small muted" data-testid="fire-context" style={{ marginTop: "0.5rem" }}>
          {fireDetectionsCaption(fireDetectionCount)}
        </p>
      ) : null}

      <p className="panel-note" style={{ marginTop: "0.75rem" }}>
        {change?.note ? `${change.note} ` : ""}
        Per-pixel comparisons are sensitive to residual cloud and shadow
        leaking through the mask on either date, so treat this map as a
        screening instrument: it shows where and when to look closer, not
        what happened.
      </p>
    </div>
  );
}
