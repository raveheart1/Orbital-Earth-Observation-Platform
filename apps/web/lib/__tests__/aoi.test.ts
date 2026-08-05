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

/** Deployment defaults: drawn areas 250 km², predefined regions up to 600. */
const limits: AoiLimits = PublicConfigSchema.parse(configFixture);

/** Michigan-ish; latitude matters for the degree↔km conversion. */
const CENTER: [number, number] = [-83.5, 42.35];

describe("maxAreaKm2ForMode", () => {
  it("uses the drawn-area cap when drawing", () => {
    expect(maxAreaKm2ForMode("custom", limits)).toBe(250);
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
  it("rejects a 300 km² drawn box against the 250 km² custom cap", () => {
    const error = validateAoiArea(300, "custom", limits);
    expect(error).not.toBeNull();
    // Mirrors the server's 422 detail, including the way out.
    expect(error).toContain("300 km²");
    expect(error).toContain("maximum of 250 km² for custom areas");
    expect(error).toContain("Draw a smaller box");
    expect(error).toContain("predefined region");
  });

  it("accepts a 1.0 km² drawn box", () => {
    expect(validateAoiArea(1.0, "custom", limits)).toBeNull();
  });

  it("accepts a curated 137 km² region under either cap", () => {
    // Curated regions are ~137 km², which now fits inside the drawn-area cap
    // too: the two ceilings sit in the same range rather than orders apart.
    expect(validateAoiArea(137, "region", limits)).toBeNull();
    expect(validateAoiArea(137, "custom", limits)).toBeNull();
  });

  it("still applies the region cap to areas only a curated region may reach", () => {
    // 481 km² is legal for a curated region and too large to draw by hand.
    expect(validateAoiArea(481.5, "region", limits)).toBeNull();
    expect(validateAoiArea(481.5, "custom", limits)).toContain(
      "maximum of 250 km²",
    );
  });

  it("keeps the shared below-minimum check for both modes", () => {
    expect(validateAoiArea(0.2, "custom", limits)).toContain("0.5 km² minimum");
    expect(validateAoiArea(0.2, "region", limits)).toContain("0.5 km² minimum");
  });

  it("accepts areas exactly on either bound", () => {
    expect(validateAoiArea(250, "custom", limits)).toBeNull();
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
