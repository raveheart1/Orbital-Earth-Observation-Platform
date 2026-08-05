import { describe, expect, it } from "vitest";
import {
  bboxAroundCenterKm,
  bboxIsValid,
  estimateBboxAreaKm2,
  normalizeBbox,
  parseBboxInputs,
} from "@/lib/geo";
import type { Bbox } from "@/lib/schemas";

describe("estimateBboxAreaKm2", () => {
  it("estimates the area of a 1°×1° box at ~42.5°N (mid-latitude)", () => {
    const bbox: Bbox = [-84.0, 42.0, -83.0, 43.0];
    const area = estimateBboxAreaKm2(bbox);
    // width ≈ 111.32 · cos(42.5°) ≈ 82.07 km, height ≈ 110.57 km → ≈ 9075 km²
    expect(area).toBeGreaterThan(9000);
    expect(area).toBeLessThan(9150);
  });

  it("scales linearly with longitude span", () => {
    const single = estimateBboxAreaKm2([-84, 42, -83, 43]);
    const double = estimateBboxAreaKm2([-85, 42, -83, 43]);
    expect(double / single).toBeCloseTo(2, 5);
  });

  it("returns zero for a degenerate box", () => {
    expect(estimateBboxAreaKm2([-83.5, 42.3, -83.5, 42.3])).toBe(0);
  });
});

describe("bboxAroundCenterKm", () => {
  it("round-trips through the area estimate", () => {
    // A square ~1.41 km on a side encloses 2 km².
    const center: [number, number] = [-83.5, 42.35];
    expect(
      estimateBboxAreaKm2(bboxAroundCenterKm(center, Math.sqrt(2))),
    ).toBeCloseTo(2, 6);
    expect(estimateBboxAreaKm2(bboxAroundCenterKm(center, 2, 3))).toBeCloseTo(
      6,
      6,
    );
  });

  it("spans more longitude degrees at higher latitudes for the same ground width", () => {
    const equator = bboxAroundCenterKm([0, 0], 1);
    const high = bboxAroundCenterKm([0, 60], 1);
    expect(high[2] - high[0]).toBeGreaterThan(equator[2] - equator[0]);
  });

  it("keeps the box inside valid lon/lat ranges near the poles", () => {
    const polar = bboxAroundCenterKm([170, 89.99], 500);
    expect(bboxIsValid(polar)).toBe(true);
  });
});

describe("normalizeBbox", () => {
  it("orders corners regardless of click order", () => {
    expect(normalizeBbox([-83.0, 43.0, -84.0, 42.0])).toEqual([
      -84.0, 42.0, -83.0, 43.0,
    ]);
  });
});

describe("bboxIsValid", () => {
  it("accepts a well-formed bbox", () => {
    expect(bboxIsValid([-83.95, 42.2, -83.6, 42.35])).toBe(true);
  });

  it("rejects inverted or out-of-range boxes", () => {
    expect(bboxIsValid([-83.6, 42.2, -83.95, 42.35])).toBe(false); // minLon > maxLon
    expect(bboxIsValid([-183, 42.2, -83.6, 42.35])).toBe(false); // lon < -180
    expect(bboxIsValid([-83.95, -95, -83.6, 42.35])).toBe(false); // lat < -90
  });
});

describe("parseBboxInputs", () => {
  it("parses complete numeric input", () => {
    expect(
      parseBboxInputs({
        minLon: "-83.95",
        minLat: "42.2",
        maxLon: "-83.6",
        maxLat: "42.35",
      }),
    ).toEqual([-83.95, 42.2, -83.6, 42.35]);
  });

  it("returns null when any field is missing or non-numeric", () => {
    expect(
      parseBboxInputs({ minLon: "", minLat: "42.2", maxLon: "-83.6", maxLat: "42.35" }),
    ).toBeNull();
    expect(
      parseBboxInputs({
        minLon: "abc",
        minLat: "42.2",
        maxLon: "-83.6",
        maxLat: "42.35",
      }),
    ).toBeNull();
  });
});
