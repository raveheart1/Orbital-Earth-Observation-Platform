import { describe, expect, it } from "vitest";
import { detectGridMismatch } from "@/lib/grid";

const SIG_A = "EPSG:32617:1272x1149:10,0,322730,0,-10,4696470";
const SIG_B = "EPSG:32617:1272x627:10,0,322730,0,-10,4691250";

describe("detectGridMismatch", () => {
  it("warns when two artifacts report different grid signatures", () => {
    const result = detectGridMismatch([
      { grid_signature: SIG_A },
      { grid_signature: SIG_B },
    ]);
    expect(result.mismatch).toBe(true);
    expect(result.signatures).toEqual([SIG_A, SIG_B]);
  });

  it("does not warn when all signatures match", () => {
    const result = detectGridMismatch(
      [{ grid_signature: SIG_A }, { grid_signature: SIG_A }],
      SIG_A,
    );
    expect(result.mismatch).toBe(false);
    expect(result.signatures).toEqual([SIG_A]);
  });

  it("warns when an artifact disagrees with the analysis grid signature", () => {
    const result = detectGridMismatch([{ grid_signature: SIG_B }], SIG_A);
    expect(result.mismatch).toBe(true);
    expect(result.signatures).toContain(SIG_A);
    expect(result.signatures).toContain(SIG_B);
  });

  it("ignores null/absent signatures (legacy artifacts carry no grid identity)", () => {
    const result = detectGridMismatch(
      [{ grid_signature: null }, null, undefined, { grid_signature: SIG_A }],
      null,
    );
    expect(result.mismatch).toBe(false);
    expect(result.signatures).toEqual([SIG_A]);
  });

  it("reports no mismatch when nothing carries a signature", () => {
    const result = detectGridMismatch([{ grid_signature: null }]);
    expect(result.mismatch).toBe(false);
    expect(result.signatures).toEqual([]);
  });
});
