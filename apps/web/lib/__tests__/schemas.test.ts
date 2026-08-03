import { describe, expect, it } from "vitest";
import {
  AnalysisSchema,
  ArtifactSchema,
  PublicConfigSchema,
  SceneSchema,
  TimeseriesSchema,
} from "@/lib/schemas";
import {
  analysisFixture,
  artifactFixture,
  configFixture,
  gridFixture,
  sceneFixture,
  timeseriesFixture,
} from "./fixtures";

describe("PublicConfigSchema", () => {
  it("parses a full public config payload", () => {
    const parsed = PublicConfigSchema.parse(configFixture);
    expect(parsed.map_default_center).toEqual([-83.5, 42.35]);
    expect(parsed.ndvi_legend.stops.length).toBeGreaterThan(1);
    expect(parsed.demo_analysis_id).toBe("0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77");
  });

  it("accepts a null demo_analysis_id", () => {
    const parsed = PublicConfigSchema.parse({
      ...configFixture,
      demo_analysis_id: null,
    });
    expect(parsed.demo_analysis_id).toBeNull();
  });

  it("rejects a config with a malformed legend", () => {
    const result = PublicConfigSchema.safeParse({
      ...configFixture,
      ndvi_legend: { type: "ndvi", stops: "nope" },
    });
    expect(result.success).toBe(false);
  });

  it("parses the no-data and masked legend entries", () => {
    const parsed = PublicConfigSchema.parse(configFixture);
    expect(parsed.ndvi_legend.nodata_color).toBe("#686a72");
    expect(parsed.ndvi_legend.nodata_label).toBe("No source imagery");
    expect(parsed.ndvi_legend.masked_label).toBe("Masked (cloud, shadow, snow)");
  });

  it("still parses a legacy legend without the no-data entries", () => {
    const { masked_label, nodata_color, nodata_label, ...legacyLegend } =
      configFixture.ndvi_legend;
    void masked_label;
    void nodata_color;
    void nodata_label;
    const parsed = PublicConfigSchema.parse({
      ...configFixture,
      ndvi_legend: legacyLegend,
    });
    expect(parsed.ndvi_legend.nodata_color).toBeUndefined();
  });
});

describe("AnalysisSchema", () => {
  it("parses a succeeded analysis with summary and region", () => {
    const parsed = AnalysisSchema.parse(analysisFixture);
    expect(parsed.status).toBe("succeeded");
    expect(parsed.summary?.usable_scene_count).toBe(6);
    expect(parsed.region?.slug).toBe("ann-arbor-huron");
  });

  it("parses a queued analysis with null summary/region", () => {
    const parsed = AnalysisSchema.parse({
      ...analysisFixture,
      status: "queued",
      status_message: null,
      region: null,
      summary: null,
      started_at: null,
      completed_at: null,
    });
    expect(parsed.status).toBe("queued");
    expect(parsed.summary).toBeNull();
  });

  it("rejects an unknown status value", () => {
    const result = AnalysisSchema.safeParse({
      ...analysisFixture,
      status: "exploded",
    });
    expect(result.success).toBe(false);
  });

  it("parses the canonical analysis grid and summary grid fields", () => {
    const parsed = AnalysisSchema.parse(analysisFixture);
    expect(parsed.grid?.signature).toBe(gridFixture.signature);
    expect(parsed.grid?.width).toBe(1272);
    expect(parsed.grid?.height).toBe(1149);
    expect(parsed.summary?.identical_analytical_grid).toBe(true);
    expect(parsed.summary?.min_aoi_coverage_pct).toBe(99);
  });

  it("defaults grid to null on legacy analyses missing the field", () => {
    const { grid, ...legacy } = analysisFixture;
    void grid;
    const legacySummary = { ...analysisFixture.summary } as Record<
      string,
      unknown
    >;
    delete legacySummary.min_aoi_coverage_pct;
    delete legacySummary.identical_analytical_grid;
    delete legacySummary.comparison_note;
    const parsed = AnalysisSchema.parse({ ...legacy, summary: legacySummary });
    expect(parsed.grid).toBeNull();
    expect(parsed.summary?.identical_analytical_grid).toBe(false);
    expect(parsed.summary?.min_aoi_coverage_pct).toBeNull();
  });
});

describe("SceneSchema", () => {
  it("parses the new nested assets shape keyed by item id, then role", () => {
    const parsed = SceneSchema.parse(sceneFixture());
    expect(
      parsed.assets["S2A_MSIL2A_20230504T163211_R041_T17TLH"]?.visual,
    ).toBe("https://example.com/T17TLH/visual.tif");
    expect(parsed.granule_count).toBe(2);
    expect(parsed.tile_ids).toEqual(["T17TLG", "T17TLH"]);
    expect(parsed.aoi_coverage_pct).toBe(100);
    expect(parsed.valid_pixel_pct).toBe(95.9);
  });

  it("parses the legacy flat assets shape and normalizes it under the scene's item id", () => {
    const legacy = sceneFixture({
      assets: {
        visual: "https://example.com/legacy/visual.tif",
        red: "https://example.com/legacy/red.tif",
      },
    }) as Record<string, unknown>;
    // Legacy payloads predate the mosaicking fields entirely.
    delete legacy.acquisition_key;
    delete legacy.contributing_item_ids;
    delete legacy.tile_ids;
    delete legacy.granule_count;
    delete legacy.aoi_coverage_pct;
    delete legacy.valid_pixel_pct;
    const parsed = SceneSchema.parse(legacy);
    expect(parsed.assets).toEqual({
      S2A_MSIL2A_20230504T163211_R041_T17TLG: {
        visual: "https://example.com/legacy/visual.tif",
        red: "https://example.com/legacy/red.tif",
      },
    });
    expect(parsed.granule_count).toBe(1);
    expect(parsed.tile_ids).toEqual([]);
    expect(parsed.aoi_coverage_pct).toBeNull();
    expect(parsed.valid_pixel_pct).toBeNull();
  });
});

describe("ArtifactSchema", () => {
  it("parses grid_signature and defaults it to null on legacy artifacts", () => {
    const parsed = ArtifactSchema.parse(artifactFixture());
    expect(parsed.grid_signature).toBe(gridFixture.signature);

    const legacy = artifactFixture() as Record<string, unknown>;
    delete legacy.grid_signature;
    expect(ArtifactSchema.parse(legacy).grid_signature).toBeNull();
  });
});

describe("TimeseriesSchema", () => {
  it("parses a timeseries payload including nullable statistics", () => {
    const parsed = TimeseriesSchema.parse({
      ...timeseriesFixture,
      points: [
        ...timeseriesFixture.points,
        { ...timeseriesFixture.points[0], ndvi_mean: null, ndvi_p25: null },
      ],
    });
    expect(parsed.points).toHaveLength(4);
    expect(parsed.points[3]?.ndvi_mean).toBeNull();
  });

  it("rejects a point missing pixel counts", () => {
    const point = { ...timeseriesFixture.points[0] } as Record<string, unknown>;
    delete point.valid_pixel_count;
    const result = TimeseriesSchema.safeParse({
      analysis_id: timeseriesFixture.analysis_id,
      points: [point],
    });
    expect(result.success).toBe(false);
  });
});
