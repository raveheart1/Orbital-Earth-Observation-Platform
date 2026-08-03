import { describe, expect, it } from "vitest";
import { TimeseriesSchema } from "@/lib/schemas";
import {
  findSceneArtifact,
  selectComparisonPoints,
  toChartPoints,
} from "@/lib/timeseries";
import type { Artifact } from "@/lib/schemas";
import { timeseriesFixture, timeseriesPointFixture } from "./fixtures";

const points = TimeseriesSchema.parse(timeseriesFixture).points;

describe("toChartPoints", () => {
  it("sorts observations chronologically even when the API is unordered", () => {
    const shuffled = [points[2]!, points[0]!, points[1]!];
    const chart = toChartPoints(shuffled);
    expect(chart.map((p) => p.date)).toEqual([
      "2023-05-04",
      "2023-07-16",
      "2023-09-26",
    ]);
    expect(chart[0]!.t).toBeLessThan(chart[1]!.t);
  });

  it("maps statistics and builds the p25–p75 band", () => {
    const chart = toChartPoints(points);
    expect(chart[0]).toMatchObject({
      mean: 0.512,
      median: 0.53,
      p25: 0.42,
      p75: 0.63,
      band: [0.42, 0.63],
      validPixelPct: 95.9,
      cloudPct: 4.2,
    });
  });

  it("leaves the band null when a percentile is missing", () => {
    const withNull = [
      timeseriesPointFixture({ ndvi_p25: null }),
    ];
    const chart = toChartPoints(
      TimeseriesSchema.parse({ analysis_id: "x", points: withNull }).points,
    );
    expect(chart[0]!.band).toBeNull();
  });
});

describe("selectComparisonPoints", () => {
  it("returns the earliest and latest observations", () => {
    const comparison = selectComparisonPoints([points[1]!, points[2]!, points[0]!]);
    expect(comparison?.first.observed_at).toBe("2023-05-04T16:32:11Z");
    expect(comparison?.last.observed_at).toBe("2023-09-26T16:33:49Z");
  });

  it("returns null when fewer than two observations exist", () => {
    expect(selectComparisonPoints([])).toBeNull();
    expect(selectComparisonPoints([points[0]!])).toBeNull();
  });
});

describe("findSceneArtifact", () => {
  const artifact = (
    stacItemId: string,
    type: Artifact["artifact_type"],
  ): Artifact => ({
    id: `${stacItemId}-${type}`,
    scene_id: "scene-1",
    stac_item_id: stacItemId,
    artifact_type: type,
    content_type: "image/png",
    size_bytes: 1024,
    sha256: "ab".repeat(32),
    crs: null,
    created_at: "2024-06-01T14:03:00Z",
    download_url: "https://example.com/signed",
    download_url_expires_in_seconds: 3600,
    grid_signature: null,
  });

  it("matches artifacts by STAC item id and type", () => {
    const artifacts = [
      artifact("item-a", "ndvi_preview"),
      artifact("item-a", "true_color_preview"),
      artifact("item-b", "ndvi_preview"),
    ];
    expect(findSceneArtifact(artifacts, "item-b", "ndvi_preview")?.id).toBe(
      "item-b-ndvi_preview",
    );
    expect(findSceneArtifact(artifacts, "item-b", "true_color_preview")).toBeNull();
  });
});
