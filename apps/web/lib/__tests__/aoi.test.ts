import { describe, expect, it } from "vitest";
import {
  defaultCustomAreaKm2,
  defaultCustomBbox,
  maxAreaKm2ForMode,
  validateAoiArea,
  type AoiLimits,
} from "@/lib/aoi";
import { estimateBboxAreaKm2 } from "@/lib/geo";
import { PublicConfigSchema } from "@/lib/schemas";
import { configFixture } from "./fixtures";

/** Deployment defaults: drawn areas 2 km², predefined regions much larger. */
const limits: AoiLimits = PublicConfigSchema.parse(configFixture);

/** Michigan-ish; latitude matters for the degree↔km conversion. */
const CENTER: [number, number] = [-83.5, 42.35];

describe("maxAreaKm2ForMode", () => {
  it("uses the tight custom cap when drawing", () => {
    expect(maxAreaKm2ForMode("custom", limits)).toBe(2);
    expect(maxAreaKm2ForMode("custom", limits)).toBe(
      limits.max_custom_aoi_area_km2,
    );
  });

  it("uses the predefined-region cap when a region is selected", () => {
    expect(maxAreaKm2ForMode("region", limits)).toBe(600);
    expect(maxAreaKm2ForMode("region", limits)).toBe(limits.max_aoi_area_km2);
  });

  it("never conflates the two limits", () => {
    expect(maxAreaKm2ForMode("custom", limits)).not.toBe(
      maxAreaKm2ForMode("region", limits),
    );
  });
});

describe("validateAoiArea", () => {
  it("rejects a 2.5 km² drawn box against the 2 km² custom cap", () => {
    const error = validateAoiArea(2.5, "custom", limits);
    expect(error).not.toBeNull();
    // Mirrors the server's 422 detail, including the way out.
    expect(error).toContain("2.50 km²");
    expect(error).toContain("maximum of 2 km² for custom areas");
    expect(error).toContain("Draw a smaller box");
    expect(error).toContain("predefined region");
  });

  it("accepts a 1.0 km² drawn box", () => {
    expect(validateAoiArea(1.0, "custom", limits)).toBeNull();
  });

  it("accepts a 137 km² predefined region even though it dwarfs the custom cap", () => {
    expect(validateAoiArea(137, "region", limits)).toBeNull();
    // The same area drawn by hand is far too large.
    expect(validateAoiArea(137, "custom", limits)).not.toBeNull();
  });

  it("keeps the shared below-minimum check for both modes", () => {
    expect(validateAoiArea(0.2, "custom", limits)).toContain("0.5 km² minimum");
    expect(validateAoiArea(0.2, "region", limits)).toContain("0.5 km² minimum");
  });

  it("accepts areas exactly on either bound", () => {
    expect(validateAoiArea(2, "custom", limits)).toBeNull();
    expect(validateAoiArea(0.5, "custom", limits)).toBeNull();
    expect(validateAoiArea(600, "region", limits)).toBeNull();
  });
});

describe("defaultCustomBbox", () => {
  it("prefills a ~1 km² box that passes validation at input precision", () => {
    const bbox = defaultCustomBbox(CENTER, limits);
    const area = estimateBboxAreaKm2(bbox);
    expect(area).toBeCloseTo(1, 2);
    expect(validateAoiArea(area, "custom", limits)).toBeNull();
  });

  it("centres the box on the given point", () => {
    const [minLon, minLat, maxLon, maxLat] = defaultCustomBbox(CENTER, limits);
    expect((minLon + maxLon) / 2).toBeCloseTo(CENTER[0], 4);
    expect((minLat + maxLat) / 2).toBeCloseTo(CENTER[1], 4);
    expect(minLon).toBeLessThan(maxLon);
    expect(minLat).toBeLessThan(maxLat);
  });

  it("stays inside unusually tight configured windows", () => {
    const tight: AoiLimits = {
      min_aoi_area_km2: 0.5,
      max_aoi_area_km2: 600,
      max_custom_aoi_area_km2: 0.8,
    };
    const area = estimateBboxAreaKm2(defaultCustomBbox(CENTER, tight));
    expect(validateAoiArea(area, "custom", tight)).toBeNull();
    expect(defaultCustomAreaKm2(tight)).toBeLessThanOrEqual(0.8);
  });
});
