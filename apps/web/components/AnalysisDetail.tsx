"use client";

import { useEffect, useState } from "react";
import {
  getAnalysis,
  getArtifacts,
  getProvenance,
  getPublicConfigCached,
  getScenes,
  getTimeseries,
} from "@/lib/api";
import {
  formatChange,
  formatDate,
  formatDateTime,
  formatKm2,
  formatNumber,
  formatPct,
  shortSha,
} from "@/lib/format";
import { isTerminalStatus, nextPollDelayMs } from "@/lib/polling";
import type { Analysis } from "@/lib/schemas";
import { useFetch, type FetchState } from "@/lib/useFetch";
import ArtifactList from "./ArtifactList";
import ComparePreviews from "./ComparePreviews";
import { ErrorBox, LoadingBox } from "./FetchStates";
import LimitationsNote from "./LimitationsNote";
import MapPanel from "./MapPanel";
import NdviChart from "./NdviChart";
import ProvenancePanel from "./ProvenancePanel";
import SceneTable from "./SceneTable";
import StatusBadge from "./StatusBadge";

/** Render a gated section uniformly: loading box, error + retry, or content. */
function Section<T>({
  state,
  reload,
  loadingLabel,
  children,
}: {
  state: FetchState<T>;
  reload: () => void;
  loadingLabel: string;
  children: (data: T) => React.ReactNode;
}) {
  if (state.status === "idle") return null;
  if (state.status === "loading") return <LoadingBox label={loadingLabel} />;
  if (state.status === "error") {
    return <ErrorBox message={state.error} onRetry={reload} />;
  }
  return <>{children(state.data)}</>;
}

export default function AnalysisDetail({ id }: { id: string }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  // Poll the analysis while it is queued/running: every 3 s for the first
  // 30 s, then every 10 s; stop permanently on a terminal state.
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const pollStart = Date.now();

    async function tick() {
      try {
        const next = await getAnalysis(id);
        if (stopped) return;
        setAnalysis(next);
        setLoadError(null);
        if (!isTerminalStatus(next.status)) {
          timer = window.setTimeout(
            () => void tick(),
            nextPollDelayMs(Date.now() - pollStart),
          );
        }
      } catch (err) {
        if (stopped) return;
        setLoadError(
          err instanceof Error ? err.message : "Failed to load the analysis.",
        );
      }
    }

    void tick();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [id, reloadTick]);

  const succeeded = analysis?.status === "succeeded";
  const config = useFetch(() => getPublicConfigCached(), []);
  const scenes = useFetch(() => getScenes(id), [id], succeeded);
  const timeseries = useFetch(() => getTimeseries(id), [id], succeeded);
  const artifacts = useFetch(() => getArtifacts(id), [id], succeeded);
  const provenance = useFetch(() => getProvenance(id), [id], succeeded);

  if (!analysis && loadError) {
    return (
      <ErrorBox message={loadError} onRetry={() => setReloadTick((t) => t + 1)} />
    );
  }
  if (!analysis) {
    return <LoadingBox label="Loading analysis…" />;
  }

  const areaLabel = analysis.region?.name ?? "the selected area";
  const inProgress = analysis.status === "queued" || analysis.status === "running";
  const bboxCenter: [number, number] = [
    (analysis.bbox[0] + analysis.bbox[2]) / 2,
    (analysis.bbox[1] + analysis.bbox[3]) / 2,
  ];

  return (
    <div>
      <header className="detail-head">
        <div className="title-row">
          <h1>
            {analysis.region?.name ?? "Custom area"}{" "}
            <span className="muted" style={{ fontSize: "0.6em" }}>
              analysis
            </span>
          </h1>
          <div aria-live="polite">
            <StatusBadge status={analysis.status} />
            {analysis.status_message ? (
              <span className="small muted" style={{ marginLeft: "0.6rem" }}>
                {analysis.status_message}
              </span>
            ) : null}
          </div>
        </div>
        <p className="meta-row">
          <span>
            Analysis <span className="mono">{analysis.id}</span>
          </span>
          <span>
            Submitted{" "}
            <span className="mono">{formatDateTime(analysis.submitted_at)}</span>
          </span>
          <span>
            Started{" "}
            <span className="mono">{formatDateTime(analysis.started_at)}</span>
          </span>
          <span>
            Completed{" "}
            <span className="mono">{formatDateTime(analysis.completed_at)}</span>
          </span>
          {analysis.retry_count > 0 ? (
            <span>
              Retries <span className="mono">{analysis.retry_count}</span>
            </span>
          ) : null}
          {analysis.is_demo ? <span>Demonstration analysis</span> : null}
        </p>
        {analysis.grid && analysis.summary?.identical_analytical_grid ? (
          <p className="grid-chip" data-testid="grid-chip">
            All observations on one analytical grid (
            <span className="mono">
              {analysis.grid.width}×{analysis.grid.height}
            </span>{" "}
            @{" "}
            <span className="mono">
              {Math.abs(analysis.grid.resolution[0] ?? 0)} m
            </span>
            , <span className="mono">{analysis.grid.crs}</span>)
          </p>
        ) : null}
        {analysis.status === "succeeded" && analysis.grid === null ? (
          <p className="small muted">
            Legacy analysis: processed before v2.0.0, so observations are not
            guaranteed to share one analytical grid and imagery extents may
            differ between dates.
          </p>
        ) : null}
        {loadError ? (
          <p className="field-error" role="alert">
            Live status updates are failing ({loadError}); showing the last
            known state.
          </p>
        ) : null}
      </header>

      {analysis.status === "failed" && analysis.failure ? (
        <div className="alert alert-error section" role="alert">
          <p>
            <strong>The analysis failed</strong> (category:{" "}
            <span className="mono">{analysis.failure.category}</span>).
          </p>
          {analysis.failure.detail ? <p>{analysis.failure.detail}</p> : null}
          <p style={{ marginTop: "0.5rem" }}>
            Common fixes: widen the date range, raise the cloud-cover
            threshold, or choose a different area — then submit a new analysis.
          </p>
        </div>
      ) : null}

      {analysis.status === "cancelled" ? (
        <div className="alert alert-warn section" role="status">
          This analysis was cancelled before it completed
          {analysis.status_message ? `: ${analysis.status_message}` : "."}
        </div>
      ) : null}

      {inProgress ? (
        <div className="panel-note section" role="status" aria-live="polite">
          <p>
            {analysis.status === "queued"
              ? "The analysis is waiting in the processing queue."
              : "The worker is processing Sentinel-2 scenes now."}{" "}
            This page checks for updates automatically — no need to reload.
          </p>
          <div
            className="skeleton"
            style={{ height: "0.75rem", marginTop: "0.75rem" }}
          />
        </div>
      ) : null}

      <section className="section detail-grid" aria-label="Request configuration">
        <div className="card">
          <h3>Request configuration</h3>
          <dl className="kv">
            <dt>Date range</dt>
            <dd>
              {formatDate(analysis.start_date)} → {formatDate(analysis.end_date)}
            </dd>
            <dt>Area of interest</dt>
            <dd>{analysis.region?.name ?? "Custom bounding box"}</dd>
            <dt>Area</dt>
            <dd>{formatKm2(analysis.area_km2)}</dd>
            <dt>Bounding box</dt>
            <dd>{analysis.bbox.map((v) => v.toFixed(4)).join(", ")}</dd>
            <dt>Collection</dt>
            <dd>{analysis.collection}</dd>
            <dt>Max cloud cover</dt>
            <dd>{formatPct(analysis.max_cloud_cover_pct)}</dd>
            <dt>Scene limit</dt>
            <dd>{analysis.scene_limit}</dd>
            <dt>Operation</dt>
            <dd>{analysis.processing.operation}</dd>
            <dt>Processing version</dt>
            <dd>
              {analysis.processing.version}
              {analysis.processing.git_commit_sha
                ? ` @ ${shortSha(analysis.processing.git_commit_sha)}`
                : ""}
            </dd>
          </dl>
        </div>
        <MapPanel
          center={bboxCenter}
          zoom={8}
          bbox={analysis.bbox}
          ariaLabel={`Map showing the analysed bounding box over ${areaLabel}`}
          short
        />
      </section>

      {analysis.summary ? (
        <section className="section" aria-labelledby="summary-heading">
          <div className="section-head">
            <h2 id="summary-heading">Summary statistics</h2>
          </div>
          <div className="stat-grid">
            <div className="stat">
              <p className="stat-label">Usable scenes</p>
              <p className="stat-value">{analysis.summary.usable_scene_count}</p>
              <p className="stat-note">
                {analysis.summary.unusable_scene_count} unusable
              </p>
            </div>
            <div className="stat">
              <p className="stat-label">First observation</p>
              <p className="stat-value">
                {formatDate(analysis.summary.first_observation)}
              </p>
            </div>
            <div className="stat">
              <p className="stat-label">Last observation</p>
              <p className="stat-value">
                {formatDate(analysis.summary.last_observation)}
              </p>
            </div>
            <div className="stat">
              <p className="stat-label">Mean NDVI, first</p>
              <p className="stat-value">
                {formatNumber(analysis.summary.ndvi_mean_first)}
              </p>
            </div>
            <div className="stat">
              <p className="stat-label">Mean NDVI, last</p>
              <p className="stat-value">
                {formatNumber(analysis.summary.ndvi_mean_last)}
              </p>
            </div>
            <div className="stat">
              <p className="stat-label">Observed change</p>
              <p className="stat-value">
                {formatChange(analysis.summary.ndvi_mean_change)}
              </p>
              <p className="stat-note">observation, not a causal claim</p>
            </div>
            <div className="stat">
              <p className="stat-label">Mean valid pixels</p>
              <p className="stat-value">
                {formatPct(analysis.summary.mean_valid_pixel_pct)}
              </p>
            </div>
          </div>
          {analysis.summary.interpretation_note ? (
            <p className="panel-note" style={{ marginTop: "1rem" }}>
              {analysis.summary.interpretation_note}
            </p>
          ) : null}
        </section>
      ) : null}

      {succeeded ? (
        <>
          <section className="section" aria-labelledby="compare-heading">
            <div className="section-head">
              <h2 id="compare-heading">Before & after</h2>
              <p className="muted small">
                Earliest and latest usable observations, as true-color imagery
                and NDVI maps.
              </p>
            </div>
            <Section
              state={timeseries.state}
              reload={timeseries.reload}
              loadingLabel="Loading observations…"
            >
              {(ts) => (
                <Section
                  state={artifacts.state}
                  reload={artifacts.reload}
                  loadingLabel="Loading preview imagery…"
                >
                  {(arts) =>
                    config.state.status === "ok" ? (
                      <ComparePreviews
                        analysis={analysis}
                        points={ts.points}
                        artifacts={arts.items}
                        legend={config.state.data.ndvi_legend}
                        areaLabel={areaLabel}
                      />
                    ) : (
                      <LoadingBox label="Loading NDVI legend…" />
                    )
                  }
                </Section>
              )}
            </Section>
          </section>

          <section className="section" aria-labelledby="timeseries-heading">
            <div className="section-head">
              <h2 id="timeseries-heading">NDVI time series</h2>
              <p className="muted small">
                Mean NDVI across the area for each usable scene; the shaded band
                spans the 25th–75th percentile of pixels.
              </p>
            </div>
            <Section
              state={timeseries.state}
              reload={timeseries.reload}
              loadingLabel="Loading time series…"
            >
              {(ts) => <NdviChart points={ts.points} />}
            </Section>
          </section>

          <section className="section" aria-labelledby="scenes-heading">
            <div className="section-head">
              <h2 id="scenes-heading">Scenes considered</h2>
            </div>
            <Section
              state={scenes.state}
              reload={scenes.reload}
              loadingLabel="Loading scenes…"
            >
              {(list) => <SceneTable scenes={list} />}
            </Section>
          </section>

          <section className="section" aria-labelledby="artifacts-heading">
            <div className="section-head">
              <h2 id="artifacts-heading">Artifacts & downloads</h2>
            </div>
            <Section
              state={artifacts.state}
              reload={artifacts.reload}
              loadingLabel="Loading artifacts…"
            >
              {(arts) => <ArtifactList artifacts={arts.items} />}
            </Section>
          </section>

          <section className="section" aria-labelledby="provenance-heading">
            <div className="section-head">
              <h2 id="provenance-heading">Provenance</h2>
              <p className="muted small">
                The complete reproducibility record for this analysis.
              </p>
            </div>
            <Section
              state={provenance.state}
              reload={provenance.reload}
              loadingLabel="Loading provenance…"
            >
              {(doc) => <ProvenancePanel provenance={doc} />}
            </Section>
          </section>
        </>
      ) : null}

      <section className="section" aria-label="Scientific limitations">
        <LimitationsNote headingLevel="h2" />
      </section>
    </div>
  );
}
