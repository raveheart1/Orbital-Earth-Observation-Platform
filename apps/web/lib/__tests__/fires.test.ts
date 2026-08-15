import { describe, expect, it } from "vitest";
import {
  findFireDetectionsArtifact,
  fireDetectionsCaption,
  parseFireDetections,
} from "@/lib/fires";
import { ArtifactSchema } from "@/lib/schemas";
import { artifactFixture } from "./fixtures";

const fireArtifact = ArtifactSchema.parse(
  artifactFixture({
    id: "artifact-fires",
    scene_id: null,
    stac_item_id: null,
    artifact_type: "fire_detections",
    content_type: "application/geo+json",
  }),
);
const previewArtifact = ArtifactSchema.parse(artifactFixture());

function pointFeature(lon: number, lat: number): GeoJSON.Feature {
  return {
    type: "Feature",
    properties: { brightness: 330.5, acq_date: "2024-07-22", confidence: "n" },
    geometry: { type: "Point", coordinates: [lon, lat] },
  };
}

describe("findFireDetectionsArtifact", () => {
  it("finds the fire-detections artifact among others", () => {
    expect(findFireDetectionsArtifact([previewArtifact, fireArtifact])).toEqual(
      fireArtifact,
    );
  });

  it("returns null when the run produced none", () => {
    expect(findFireDetectionsArtifact([previewArtifact])).toBeNull();
    expect(findFireDetectionsArtifact([])).toBeNull();
  });
});

describe("parseFireDetections", () => {
  it("accepts a FeatureCollection of points", () => {
    const fc = {
      type: "FeatureCollection",
      features: [pointFeature(-121.5, 39.8), pointFeature(-121.4, 39.7)],
    };
    const parsed = parseFireDetections(fc);
    expect(parsed?.features).toHaveLength(2);
  });

  it("drops non-point features defensively", () => {
    const fc = {
      type: "FeatureCollection",
      features: [
        pointFeature(-121.5, 39.8),
        {
          type: "Feature",
          properties: {},
          geometry: {
            type: "LineString",
            coordinates: [
              [-121.5, 39.8],
              [-121.4, 39.7],
            ],
          },
        },
      ],
    };
    expect(parseFireDetections(fc)?.features).toHaveLength(1);
  });

  it("returns null for an empty collection so the overlay is omitted", () => {
    expect(
      parseFireDetections({ type: "FeatureCollection", features: [] }),
    ).toBeNull();
  });

  it("returns null for anything that is not a FeatureCollection", () => {
    expect(parseFireDetections(null)).toBeNull();
    expect(parseFireDetections("not json")).toBeNull();
    expect(parseFireDetections({ type: "Feature" })).toBeNull();
    expect(
      parseFireDetections({ type: "FeatureCollection", features: "oops" }),
    ).toBeNull();
  });
});

describe("fireDetectionsCaption", () => {
  it("states the count with the context-not-perimeters caveat", () => {
    expect(fireDetectionsCaption(3)).toBe(
      "3 FIRMS active-fire detections within this analysis's area and date " +
        "window (context, not perimeters).",
    );
  });

  it("singularizes a single detection", () => {
    expect(fireDetectionsCaption(1)).toContain("1 FIRMS active-fire detection ");
  });
});
