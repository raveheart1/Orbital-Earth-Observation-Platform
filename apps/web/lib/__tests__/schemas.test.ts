import { describe, expect, it } from "vitest";
import {
  AnalysisSchema,
  PublicConfigSchema,
  TimeseriesSchema,
} from "@/lib/schemas";
import { analysisFixture, configFixture, timeseriesFixture } from "./fixtures";

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
