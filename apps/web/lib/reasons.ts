import { formatPct } from "./format";

/**
 * Human-readable text for machine exclusion/unusable reason codes reported
 * by the scenes endpoint. Unknown codes fall back to the code with the
 * underscores replaced, so new backend reasons degrade gracefully.
 */
const REASON_LABELS: Record<string, string> = {
  cloud_cover_above_threshold: "Cloud cover above the configured threshold",
  not_selected_temporal_sampling:
    "Not selected by temporal sampling within the scene limit",
  insufficient_valid_pixels:
    "Too few valid (unmasked) pixels for reliable statistics",
  all_pixels_masked: "All pixels were masked as cloud, shadow, or snow",
  no_raster_overlap_with_aoi:
    "The source imagery did not overlap the area of interest",
};

export function humanizeExclusionReason(
  reason: string | null | undefined,
  aoiCoveragePct?: number | null,
): string | null {
  if (!reason) return null;
  if (reason === "insufficient_aoi_coverage") {
    return aoiCoveragePct !== null && aoiCoveragePct !== undefined
      ? `Source granules covered only ${formatPct(aoiCoveragePct)} of the area of interest`
      : "Source granules did not cover enough of the area of interest";
  }
  return REASON_LABELS[reason] ?? reason.replaceAll("_", " ");
}
