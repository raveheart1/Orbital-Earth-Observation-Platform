import { describe, expect, it } from "vitest";
import { humanizeExclusionReason } from "@/lib/reasons";

describe("humanizeExclusionReason", () => {
  it("maps insufficient_aoi_coverage to text mentioning the coverage percentage", () => {
    const text = humanizeExclusionReason("insufficient_aoi_coverage", 56.2);
    expect(text).toBe(
      "Source granules covered only 56.2% of the area of interest",
    );
  });

  it("still mentions coverage when the percentage is unknown", () => {
    const text = humanizeExclusionReason("insufficient_aoi_coverage", null);
    expect(text).toMatch(/cover/i);
    expect(text).toMatch(/area of interest/i);
  });

  it("maps the known machine codes to friendly text", () => {
    expect(humanizeExclusionReason("cloud_cover_above_threshold")).toBe(
      "Cloud cover above the configured threshold",
    );
    expect(humanizeExclusionReason("not_selected_temporal_sampling")).toMatch(
      /temporal sampling/i,
    );
    expect(humanizeExclusionReason("insufficient_valid_pixels")).toMatch(
      /valid/i,
    );
    expect(humanizeExclusionReason("all_pixels_masked")).toMatch(/masked/i);
    expect(humanizeExclusionReason("no_raster_overlap_with_aoi")).toMatch(
      /overlap/i,
    );
  });

  it("degrades unknown codes to readable text and passes through null", () => {
    expect(humanizeExclusionReason("some_future_reason")).toBe(
      "some future reason",
    );
    expect(humanizeExclusionReason(null)).toBeNull();
    expect(humanizeExclusionReason(undefined)).toBeNull();
  });
});
