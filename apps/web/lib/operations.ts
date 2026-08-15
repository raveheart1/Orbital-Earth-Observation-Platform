import type { ArtifactType, NdviLegend, PublicConfig } from "./schemas";

/**
 * Per-operation UI metadata: how each spectral-index operation is labeled and
 * phrased across the result pages. Keyed by the operation id the API persists
 * on the analysis (`analysis.processing.operation`). The NDVI wording is the
 * exact copy the components carried before operations existed — moved here,
 * not rewritten — so NDVI analyses render byte-identically to before.
 */
export interface OperationUi {
  /** Registry id, e.g. "ndvi". */
  id: string;
  /** Short display name used in labels, headings, and the chart axis. */
  name: string;
  /** Longer title matching the server's registry entry. */
  title: string;
  /** Short plain-language description of what the index shows. */
  description: string;
  /** Per-scene preview artifact type this operation produces. */
  previewArtifactType: ArtifactType;
  /** Analysis-level change-map preview artifact type. */
  changePreviewArtifactType: ArtifactType;
  /** Alt-text phrasing appended to per-scene preview descriptions. */
  previewAltHint: string;
  /** Alt-text phrasing describing the change map's diverging colors. */
  changeAltHint: string;
  /** Change-statistic wording for deltas beyond ±threshold. */
  changeIncreaseLabel: string;
  changeDecreaseLabel: string;
  /** Blurb under the change-map section heading. */
  changeSectionBlurb: string;
  /** Note under the change legend: the delta's sign convention. */
  changeLegendNote: string;
}

const NDVI_UI: OperationUi = {
  id: "ndvi",
  name: "NDVI",
  title: "NDVI — vegetation health",
  description:
    "Higher values indicate denser, healthier green vegetation; negative " +
    "values indicate water, bare soil, or non-vegetated surfaces.",
  previewArtifactType: "ndvi_preview",
  changePreviewArtifactType: "ndvi_change_preview",
  previewAltHint: "greener shades indicate denser, healthier vegetation",
  changeAltHint: "brown shades lost vegetation greenness, blue-green shades gained",
  changeIncreaseLabel: "greener",
  changeDecreaseLabel: "browner",
  changeSectionBlurb:
    "Per-pixel difference between the earliest and latest usable " +
    "observations; blue-green means greener, brown means browner.",
  changeLegendNote:
    "Delta is the later minus the earlier NDVI; positive is greening. The " +
    "analytical COG retains full delta values beyond the display range.",
};

const NBR_UI: OperationUi = {
  id: "nbr",
  name: "NBR",
  title: "NBR — burn severity",
  description:
    "Healthy vegetation scores high; recently burned or bare surfaces drop " +
    "low or negative, so a negative change between dates is consistent with " +
    "burning. NBR is a spectral signal only — it does not by itself confirm fire.",
  previewArtifactType: "nbr_preview",
  changePreviewArtifactType: "nbr_change_preview",
  previewAltHint:
    "dark brown shades indicate low NBR, consistent with burned or bare surfaces",
  changeAltHint:
    "brown shades indicate burn severity increase (NBR loss), blue-green " +
    "shades recovery or regrowth",
  changeIncreaseLabel: "recovered",
  changeDecreaseLabel: "burn severity increase",
  changeSectionBlurb:
    "Per-pixel difference between the earliest and latest usable " +
    "observations; blue-green means recovery or regrowth, brown means burn " +
    "severity increase.",
  changeLegendNote:
    "Delta is the later minus the earlier NBR; negative indicates burn " +
    "severity increase, positive recovery or regrowth. The analytical COG " +
    "retains full delta values beyond the display range.",
};

const OPERATION_UI: Record<string, OperationUi> = {
  ndvi: NDVI_UI,
  nbr: NBR_UI,
};

/**
 * UI metadata for an operation id. An unknown future operation still renders:
 * it gets the NDVI artifact types and phrasing under its own uppercased id,
 * which is honest for any normalized-difference index.
 */
export function operationUi(operation: string | null | undefined): OperationUi {
  if (!operation) return NDVI_UI;
  const known = OPERATION_UI[operation];
  if (known) return known;
  return {
    ...NDVI_UI,
    id: operation,
    name: operation.toUpperCase(),
    title: operation.toUpperCase(),
    description: "",
  };
}

/**
 * Preview legend for an operation, picked from the public config's
 * per-operation entries. Falls back to the legacy top-level `ndvi_legend`
 * when the server predates per-operation legends (or omits one), so an old
 * config still renders exactly as before.
 */
export function legendForOperation(
  config: PublicConfig,
  operation: string,
): NdviLegend {
  return (
    config.operations.find((entry) => entry.id === operation)?.legend ??
    config.ndvi_legend
  );
}
