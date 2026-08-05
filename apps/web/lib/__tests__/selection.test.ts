import { describe, expect, it } from "vitest";
import {
  describeSelectionStrategy,
  midpointMonth,
  monthName,
  selectionStrategyName,
  shouldSuggestSeasonal,
} from "@/lib/selection";

describe("midpointMonth", () => {
  it("takes the month at the centre of a single-season range", () => {
    // 2024-04-01 → 2024-08-31 centres on mid-June.
    expect(midpointMonth("2024-04-01", "2024-08-31")).toBe(6);
  });

  it("handles a range that crosses a year boundary", () => {
    // 2023-11-01 → 2024-02-01 centres on mid-December.
    expect(midpointMonth("2023-11-01", "2024-02-01")).toBe(12);
  });

  it("handles a multi-year range", () => {
    // Eight full years centred on 2022-01-01.
    expect(midpointMonth("2018-01-01", "2026-01-01")).toBe(1);
    // A July-to-July window over eight years stays in July.
    expect(midpointMonth("2018-07-01", "2026-07-01")).toBe(7);
  });

  it("returns the month itself for a zero-length range", () => {
    expect(midpointMonth("2024-09-14", "2024-09-14")).toBe(9);
  });

  it("returns null for unusable input", () => {
    expect(midpointMonth("", "2024-01-01")).toBeNull();
    expect(midpointMonth("2024/01/01", "2024-06-01")).toBeNull();
    expect(midpointMonth("2024-06-01", "2024-01-01")).toBeNull();
  });
});

describe("shouldSuggestSeasonal", () => {
  const base = { recommendedAboveDays: 400 };

  it("suggests seasonal for a long span still using temporal selection", () => {
    expect(
      shouldSuggestSeasonal({ ...base, spanDays: 2920, strategy: "temporal" }),
    ).toBe(true);
    expect(
      shouldSuggestSeasonal({ ...base, spanDays: 401, strategy: "temporal" }),
    ).toBe(true);
  });

  it("stays quiet once the visitor has switched to seasonal", () => {
    expect(
      shouldSuggestSeasonal({ ...base, spanDays: 2920, strategy: "seasonal" }),
    ).toBe(false);
  });

  it("stays quiet at or below the threshold", () => {
    expect(
      shouldSuggestSeasonal({ ...base, spanDays: 400, strategy: "temporal" }),
    ).toBe(false);
    expect(
      shouldSuggestSeasonal({ ...base, spanDays: 120, strategy: "temporal" }),
    ).toBe(false);
  });

  it("stays quiet when the span cannot be computed", () => {
    expect(
      shouldSuggestSeasonal({ ...base, spanDays: Number.NaN, strategy: "temporal" }),
    ).toBe(false);
  });
});

describe("monthName", () => {
  it("names months and rejects out-of-range values", () => {
    expect(monthName(1)).toBe("January");
    expect(monthName(7)).toBe("July");
    expect(monthName(12)).toBe("December");
    expect(monthName(0)).toBeNull();
    expect(monthName(13)).toBeNull();
    expect(monthName(null)).toBeNull();
  });
});

describe("describeSelectionStrategy", () => {
  it("names the seasonal strategy with its target month", () => {
    expect(
      describeSelectionStrategy({
        selection_strategy: "seasonal",
        seasonal_target_month: 7,
      }),
    ).toBe("Same season each year (target: July)");
  });

  it("names the temporal strategy and ignores any stray month", () => {
    expect(
      describeSelectionStrategy({
        selection_strategy: "temporal",
        seasonal_target_month: null,
      }),
    ).toBe("Spread across the range");
    expect(
      describeSelectionStrategy({
        selection_strategy: "temporal",
        seasonal_target_month: 7,
      }),
    ).toBe("Spread across the range");
  });

  it("omits the target when a seasonal analysis has no month recorded", () => {
    expect(
      describeSelectionStrategy({
        selection_strategy: "seasonal",
        seasonal_target_month: null,
      }),
    ).toBe("Same season each year");
  });

  it("falls back to the raw value for an unknown strategy", () => {
    expect(selectionStrategyName("cloud-free-first")).toBe("cloud-free-first");
    expect(
      describeSelectionStrategy({ selection_strategy: "cloud-free-first" }),
    ).toBe("cloud-free-first");
  });
});
