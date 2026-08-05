import { formatAreaLimitKm2, formatKm2 } from "./format";
import { bboxAroundCenterKm } from "./geo";
import type { Bbox } from "./schemas";

/**
 * Area-of-interest limits, mirroring the server-side checks in
 * POST /api/v1/analyses.
 *
 * Two *separate* upper bounds exist and must never be conflated:
 *   - `max_aoi_area_km2` governs PREDEFINED REGION submissions (curated areas,
 *     hundreds of km²);
 *   - `max_custom_aoi_area_km2` governs areas a visitor DRAWS themselves
 *     (250 km² by default). It is calibrated from measured processing cost, so
 *     the two ceilings now sit in the same range — but they remain independent
 *     settings and a deployment may tighten either one.
 * `min_aoi_area_km2` applies to both.
 */
export type AoiMode = "region" | "custom";

export interface AoiLimits {
  min_aoi_area_km2: number;
  max_aoi_area_km2: number;
  max_custom_aoi_area_km2: number;
}

/** Zoom level at which a ~1.4 km box is comfortable to draw by hand. */
export const CUSTOM_DRAW_ZOOM = 13.5;

/** Ground area we prefill a fresh custom box with, before clamping. */
const PREFERRED_DEFAULT_AREA_KM2 = 1;

/** Decimal places carried by the four numeric lon/lat inputs. */
export const BBOX_INPUT_DECIMALS = 5;

/** The upper area bound in force for the given selection mode. */
export function maxAreaKm2ForMode(mode: AoiMode, limits: AoiLimits): number {
  return mode === "custom"
    ? limits.max_custom_aoi_area_km2
    : limits.max_aoi_area_km2;
}

/**
 * Client-side mirror of the server's area checks. Returns null when the area
 * is acceptable, otherwise the message to show the visitor.
 */
export function validateAoiArea(
  areaKm2: number,
  mode: AoiMode,
  limits: AoiLimits,
): string | null {
  const max = maxAreaKm2ForMode(mode, limits);
  if (areaKm2 > max) {
    return mode === "custom"
      ? `Drawn area of ${formatKm2(areaKm2)} exceeds the maximum of ${formatAreaLimitKm2(max)} for custom areas. Draw a smaller box, or choose a predefined region to analyse a larger area.`
      : `This region covers ${formatKm2(areaKm2)}, above the ${formatAreaLimitKm2(max)} limit for predefined regions.`;
  }
  if (areaKm2 < limits.min_aoi_area_km2) {
    const noun = mode === "custom" ? "Drawn area" : "Region area";
    return `${noun} of ${formatKm2(areaKm2)} is below the ${formatAreaLimitKm2(limits.min_aoi_area_km2)} minimum. ${mode === "custom" ? "Draw a larger box." : "Choose another region."}`;
  }
  return null;
}

/**
 * Ground area used to prefill a fresh drawn box: ~1 km², pulled inside the
 * configured window so the prefilled form is immediately submittable even on
 * deployments with unusual limits.
 */
export function defaultCustomAreaKm2(limits: AoiLimits): number {
  const { min_aoi_area_km2: min, max_custom_aoi_area_km2: max } = limits;
  if (!(max > min)) return max;
  // Stay clear of both bounds so 5-decimal rounding cannot push it outside;
  // fall back to the middle of the window when it is too narrow for that.
  const target = Math.min(Math.max(PREFERRED_DEFAULT_AREA_KM2, min * 1.1), max * 0.9);
  return target >= min && target <= max ? target : (min + max) / 2;
}

const round = (value: number) =>
  Number(value.toFixed(BBOX_INPUT_DECIMALS));

/**
 * A square, valid-by-construction custom AOI centred on the map centre, at the
 * precision the numeric inputs carry. Used to prefill the form when the
 * visitor first switches to drawing, so they start from a compliant example.
 */
export function defaultCustomBbox(
  center: [number, number],
  limits: AoiLimits,
): Bbox {
  const sideKm = Math.sqrt(defaultCustomAreaKm2(limits));
  const bbox = bboxAroundCenterKm(center, sideKm);
  return [round(bbox[0]), round(bbox[1]), round(bbox[2]), round(bbox[3])];
}
