"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createAnalysis,
  formatProblemLoc,
  getPublicConfigCached,
  getRegions,
} from "@/lib/api";
import { addDays, todayIsoDate, validateDateRange } from "@/lib/dates";
import { formatKm2 } from "@/lib/format";
import {
  bboxIsValid,
  estimateBboxAreaKm2,
  parseBboxInputs,
} from "@/lib/geo";
import type {
  Bbox,
  CreateAnalysisRequest,
  Problem,
  PublicConfig,
  Region,
} from "@/lib/schemas";
import { useFetch } from "@/lib/useFetch";
import { ErrorBox, LoadingBox } from "./FetchStates";
import MapPanel from "./MapPanel";
import RegionPicker from "./RegionPicker";

type AoiMode = "region" | "custom";

interface BboxInputs {
  minLon: string;
  minLat: string;
  maxLon: string;
  maxLat: string;
}

const BBOX_FIELDS: { key: keyof BboxInputs; label: string }[] = [
  { key: "minLon", label: "Min longitude" },
  { key: "minLat", label: "Min latitude" },
  { key: "maxLon", label: "Max longitude" },
  { key: "maxLat", label: "Max latitude" },
];

export default function NewAnalysisForm() {
  const config = useFetch(() => getPublicConfigCached(), []);
  const regions = useFetch(() => getRegions(), []);

  if (config.state.status === "loading" || regions.state.status === "loading") {
    return <LoadingBox label="Loading platform configuration…" />;
  }
  if (config.state.status === "error") {
    return <ErrorBox message={config.state.error} onRetry={config.reload} />;
  }
  if (regions.state.status === "error") {
    return <ErrorBox message={regions.state.error} onRetry={regions.reload} />;
  }
  if (config.state.status !== "ok" || regions.state.status !== "ok") {
    return <LoadingBox label="Loading platform configuration…" />;
  }
  return <FormInner config={config.state.data} regions={regions.state.data} />;
}

function FormInner({
  config,
  regions,
}: {
  config: PublicConfig;
  regions: Region[];
}) {
  const router = useRouter();
  const today = todayIsoDate();

  const defaultSpanDays = Math.min(365, config.max_date_span_days);
  const defaultStart = (() => {
    const candidate = addDays(today, -defaultSpanDays);
    return candidate < config.min_start_date ? config.min_start_date : candidate;
  })();

  const [mode, setMode] = useState<AoiMode>("region");
  const [regionId, setRegionId] = useState<string | null>(
    regions[0]?.id ?? null,
  );
  const [bboxInputs, setBboxInputs] = useState<BboxInputs>({
    minLon: "",
    minLat: "",
    maxLon: "",
    maxLat: "",
  });
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(today);
  const [cloudPct, setCloudPct] = useState(config.default_cloud_cover_pct);
  const [sceneLimit, setSceneLimit] = useState(config.default_scene_limit);
  const [submitting, setSubmitting] = useState(false);
  const [serverProblem, setServerProblem] = useState<Problem | null>(null);
  const [serverMessage, setServerMessage] = useState<string | null>(null);

  const customAllowed = !config.demo_mode;
  const selectedRegion = regions.find((r) => r.id === regionId) ?? null;

  const customBbox: Bbox | null = useMemo(() => {
    const parsed = parseBboxInputs(bboxInputs);
    return parsed && bboxIsValid(parsed) ? parsed : null;
  }, [bboxInputs]);

  const activeBbox: Bbox | null =
    mode === "region" ? (selectedRegion?.bbox ?? null) : customBbox;

  const customArea = customBbox ? estimateBboxAreaKm2(customBbox) : null;

  // --- Validation ---------------------------------------------------------
  const aoiError: string | null = (() => {
    if (mode === "region") {
      return selectedRegion ? null : "Choose a region.";
    }
    const parsed = parseBboxInputs(bboxInputs);
    if (!parsed) {
      return "Enter all four bounding-box coordinates (or draw a rectangle on the map).";
    }
    if (!bboxIsValid(parsed)) {
      return "The bounding box is invalid: longitudes must be within ±180, latitudes within ±90, and minimums smaller than maximums.";
    }
    const area = estimateBboxAreaKm2(parsed);
    if (area > config.max_aoi_area_km2) {
      return `The area is ~${formatKm2(area)}, above the ${formatKm2(config.max_aoi_area_km2)} limit. Draw a smaller rectangle.`;
    }
    if (area < config.min_aoi_area_km2) {
      return `The area is ~${formatKm2(area)}, below the ${formatKm2(config.min_aoi_area_km2)} minimum. Draw a larger rectangle.`;
    }
    return null;
  })();

  const dateError = validateDateRange(startDate, endDate, {
    minStartDate: config.min_start_date,
    maxSpanDays: config.max_date_span_days,
    today,
  });

  const sceneLimitError =
    Number.isInteger(sceneLimit) &&
    sceneLimit >= 1 &&
    sceneLimit <= config.max_scene_limit
      ? null
      : `The scene limit must be a whole number between 1 and ${config.max_scene_limit}.`;

  const formValid =
    !aoiError && !dateError && !sceneLimitError && config.submissions_enabled;

  // --- Submit -------------------------------------------------------------
  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!formValid || submitting) return;
    setSubmitting(true);
    setServerProblem(null);
    setServerMessage(null);
    const payload: CreateAnalysisRequest = {
      ...(mode === "region"
        ? { region_id: selectedRegion?.id }
        : { bbox: customBbox ?? undefined }),
      start_date: startDate,
      end_date: endDate,
      max_cloud_cover_pct: cloudPct,
      scene_limit: sceneLimit,
    };
    try {
      const analysis = await createAnalysis(payload);
      router.push(`/analyses/${analysis.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setServerProblem(err.problem);
        setServerMessage(err.message);
      } else {
        setServerMessage("The submission failed unexpectedly. Please try again.");
      }
      setSubmitting(false);
    }
  }

  function setBboxFromDraw(bbox: Bbox) {
    setBboxInputs({
      minLon: bbox[0].toFixed(5),
      minLat: bbox[1].toFixed(5),
      maxLon: bbox[2].toFixed(5),
      maxLat: bbox[3].toFixed(5),
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {!config.submissions_enabled ? (
        <div className="alert alert-warn" role="status" style={{ marginBottom: "1.5rem" }}>
          Submissions are currently disabled on this deployment. You can browse
          existing analyses, but new ones cannot be started.
        </div>
      ) : null}

      {serverMessage ? (
        <div className="alert alert-error" role="alert" style={{ marginBottom: "1.5rem" }}>
          <p>
            <strong>The API rejected the submission.</strong> {serverMessage}
          </p>
          {serverProblem?.errors?.length ? (
            <ul>
              {serverProblem.errors.map((fieldError, index) => (
                <li key={index}>
                  <span className="mono">{formatProblemLoc(fieldError.loc)}</span>
                  : {fieldError.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <fieldset disabled={!config.submissions_enabled || submitting}>
        <legend>Area of interest</legend>

        <div className="field">
          <div className="mode-toggle" role="radiogroup" aria-label="Area selection mode">
            <label>
              <input
                type="radio"
                name="aoi-mode"
                value="region"
                checked={mode === "region"}
                onChange={() => setMode("region")}
              />
              Predefined region
            </label>
            <label>
              <input
                type="radio"
                name="aoi-mode"
                value="custom"
                checked={mode === "custom"}
                onChange={() => setMode("custom")}
                disabled={!customAllowed}
              />
              Draw a custom area
            </label>
          </div>
          {!customAllowed ? (
            <p className="hint">
              Custom areas are disabled in demonstration mode; choose one of the
              predefined regions below.
            </p>
          ) : null}
        </div>

        <div className="detail-grid">
          <div>
            {mode === "region" ? (
              <RegionPicker
                regions={regions}
                selectedId={regionId}
                onSelect={setRegionId}
              />
            ) : (
              <div>
                <p className="hint" style={{ marginBottom: "0.75rem" }}>
                  Click the map twice to draw a rectangle (first click sets one
                  corner, second click the opposite corner; Escape cancels), or
                  type the coordinates — the map and the fields stay in sync.
                </p>
                <div className="field-row">
                  {BBOX_FIELDS.map(({ key, label }) => (
                    <div className="field" key={key}>
                      <label htmlFor={`bbox-${key}`}>{label}</label>
                      <input
                        id={`bbox-${key}`}
                        type="number"
                        step="0.00001"
                        inputMode="decimal"
                        value={bboxInputs[key]}
                        onChange={(e) =>
                          setBboxInputs({ ...bboxInputs, [key]: e.target.value })
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p aria-live="polite" style={{ marginTop: "0.75rem" }}>
              Estimated area:{" "}
              <span className="num">
                {mode === "region"
                  ? formatKm2(selectedRegion?.area_km2 ?? null)
                  : formatKm2(customArea)}
              </span>
              <span className="small muted">
                {" "}
                (limit {formatKm2(config.min_aoi_area_km2)} –{" "}
                {formatKm2(config.max_aoi_area_km2)})
              </span>
            </p>
            {aoiError ? <p className="field-error">{aoiError}</p> : null}
          </div>

          <MapPanel
            center={config.map_default_center}
            zoom={config.map_default_zoom}
            bbox={activeBbox}
            drawEnabled={
              mode === "custom" && customAllowed && config.submissions_enabled
            }
            onDrawComplete={setBboxFromDraw}
            ariaLabel="Map of the area of interest. Use the coordinate fields to define a custom area with the keyboard."
          />
        </div>
      </fieldset>

      <fieldset disabled={!config.submissions_enabled || submitting}>
        <legend>Observation window & scene selection</legend>

        <div className="field-row">
          <div className="field">
            <label htmlFor="start-date">Start date</label>
            <input
              id="start-date"
              type="date"
              value={startDate}
              min={config.min_start_date}
              max={today}
              onChange={(e) => setStartDate(e.target.value)}
            />
            <span className="hint">Earliest: {config.min_start_date}</span>
          </div>
          <div className="field">
            <label htmlFor="end-date">End date</label>
            <input
              id="end-date"
              type="date"
              value={endDate}
              min={config.min_start_date}
              max={today}
              onChange={(e) => setEndDate(e.target.value)}
            />
            <span className="hint">
              Max span: {config.max_date_span_days} days
            </span>
          </div>
        </div>
        {dateError ? <p className="field-error">{dateError}</p> : null}

        <div className="field-row" style={{ marginTop: "1rem" }}>
          <div className="field">
            <label htmlFor="cloud-cover">
              Max scene cloud cover:{" "}
              <span className="num">{cloudPct}%</span>
            </label>
            <input
              id="cloud-cover"
              type="range"
              min={0}
              max={config.max_cloud_cover_pct}
              step={1}
              value={cloudPct}
              onChange={(e) => setCloudPct(Number(e.target.value))}
              aria-valuetext={`${cloudPct} percent`}
            />
            <span className="hint">
              Scenes reporting more cloud than this are never considered.
            </span>
          </div>
          <div className="field">
            <label htmlFor="scene-limit">Scene limit</label>
            <input
              id="scene-limit"
              type="number"
              min={1}
              max={config.max_scene_limit}
              step={1}
              value={sceneLimit}
              onChange={(e) => setSceneLimit(Number(e.target.value))}
            />
            <span className="hint">
              1–{config.max_scene_limit}; the clearest scenes are preferred.
            </span>
          </div>
        </div>
        {sceneLimitError ? <p className="field-error">{sceneLimitError}</p> : null}
      </fieldset>

      <aside className="panel-note" style={{ marginBottom: "1.5rem" }}>
        <strong>Scope & cost.</strong> Each analysis streams only the raster
        windows that cover your area of interest — never whole scenes — and
        processes at most {config.max_scene_limit} scenes per run. Areas are
        capped at {formatKm2(config.max_aoi_area_km2)} and date ranges at{" "}
        {config.max_date_span_days} days, which keeps every run small,
        predictable, and reproducible.
      </aside>

      <button
        type="submit"
        className="btn btn-primary"
        disabled={!formValid || submitting}
      >
        {submitting ? "Submitting…" : "Submit analysis"}
      </button>
      {!config.submissions_enabled ? null : !formValid ? (
        <span className="small muted" style={{ marginLeft: "0.75rem" }}>
          Fix the highlighted fields to enable submission.
        </span>
      ) : null}
    </form>
  );
}
