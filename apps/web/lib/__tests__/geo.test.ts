import { describe, expect, it } from "vitest";
import {
  bboxAroundCenterKm,
  bboxIsValid,
  bboxRing,
  estimateBboxAreaKm2,
  estimateRingAreaKm2,
  normalizeBbox,
  parseBboxInputs,
  ringToPolygonFeature,
  ringToPolygonGeometry,
  type LonLatRing,
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

describe("estimateRingAreaKm2", () => {
  // 0.009° of latitude ≈ 1.0008 km on the mean sphere, so both squares below
  // enclose almost exactly 1 km² of ground.
  const SIDE_DEG = 0.009;

  it("measures a ~1 km² square at the equator within 1%", () => {
    const ring: LonLatRing = [
      [0, 0],
      [SIDE_DEG, 0],
      [SIDE_DEG, SIDE_DEG],
      [0, SIDE_DEG],
    ];
    // Spherical truth for this lon/lat square is ≈ 1.0015 km².
    const area = estimateRingAreaKm2(ring);
    expect(area).toBeGreaterThan(0.99);
    expect(area).toBeLessThan(1.01);
  });

  it("measures a ~1 km² square at 60°N within 1%", () => {
    // The longitude span is doubled so the ground width stays ~1 km.
    const ring: LonLatRing = [
      [0, 60],
      [2 * SIDE_DEG, 60],
      [2 * SIDE_DEG, 60 + SIDE_DEG],
      [0, 60 + SIDE_DEG],
    ];
    const area = estimateRingAreaKm2(ring);
    expect(area).toBeGreaterThan(0.99);
    expect(area).toBeLessThan(1.01);
  });

  it("halves the square's area for the triangle cut along its diagonal", () => {
    const square: LonLatRing = [
      [0, 0],
      [SIDE_DEG, 0],
      [SIDE_DEG, SIDE_DEG],
      [0, SIDE_DEG],
    ];
    const triangle: LonLatRing = [
      [0, 0],
      [SIDE_DEG, 0],
      [0, SIDE_DEG],
    ];
    expect(estimateRingAreaKm2(triangle) / estimateRingAreaKm2(square)).toBeCloseTo(
      0.5,
      4,
    );
  });

  it("is indifferent to ring closure and winding", () => {
    const open: LonLatRing = [
      [-83.6, 42.3],
      [-83.5, 42.3],
      [-83.5, 42.4],
    ];
    const closed: LonLatRing = [...open, [-83.6, 42.3]];
    const reversed: LonLatRing = [...open].reverse();
    const area = estimateRingAreaKm2(open);
    expect(estimateRingAreaKm2(closed)).toBe(area);
    // Reversed winding sums the same terms in a different order, so allow for
    // floating-point noise while requiring the same magnitude.
    expect(estimateRingAreaKm2(reversed)).toBeCloseTo(area, 10);
  });

  it("agrees with the bbox estimate on a rectangular ring", () => {
    const bbox: Bbox = [-83.95, 42.2, -83.6, 42.35];
    const ratio = estimateRingAreaKm2(bboxRing(bbox)) / estimateBboxAreaKm2(bbox);
    // Two independent approximations (sphere vs fixed per-degree constants).
    expect(ratio).toBeGreaterThan(0.985);
    expect(ratio).toBeLessThan(1.015);
  });

  it("returns zero below three distinct vertices", () => {
    expect(estimateRingAreaKm2([])).toBe(0);
    expect(estimateRingAreaKm2([[-83.5, 42.3]])).toBe(0);
    expect(
      estimateRingAreaKm2([
        [-83.5, 42.3],
        [-83.4, 42.4],
      ]),
    ).toBe(0);
    // A closed two-vertex "ring" is still degenerate.
    expect(
      estimateRingAreaKm2([
        [-83.5, 42.3],
        [-83.4, 42.4],
        [-83.5, 42.3],
      ]),
    ).toBe(0);
  });
});

describe("ringToPolygonGeometry", () => {
  const open: LonLatRing = [
    [-83.6, 42.3],
    [-83.5, 42.3],
    [-83.5, 42.4],
  ];

  it("closes an open ring by repeating the first vertex", () => {
    const geometry = ringToPolygonGeometry(open);
    expect(geometry.type).toBe("Polygon");
    expect(geometry.coordinates).toEqual([
      [
        [-83.6, 42.3],
        [-83.5, 42.3],
        [-83.5, 42.4],
        [-83.6, 42.3],
      ],
    ]);
  });

  it("does not double-close an already closed ring", () => {
    const closed: LonLatRing = [...open, [-83.6, 42.3]];
    expect(ringToPolygonGeometry(closed)).toEqual(ringToPolygonGeometry(open));
  });

  it("wraps the same geometry in a feature for MapLibre", () => {
    const feature = ringToPolygonFeature(open);
    expect(feature.type).toBe("Feature");
    expect(feature.geometry).toEqual(ringToPolygonGeometry(open));
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
