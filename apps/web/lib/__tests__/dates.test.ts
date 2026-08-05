import { describe, expect, it } from "vitest";
import { addDays, dateSpanDays, validateDateRange } from "@/lib/dates";

const RULES = {
  minStartDate: "2017-01-01",
  maxSpanDays: 365,
  today: "2026-08-02",
};

describe("dateSpanDays", () => {
  it("counts whole days between dates", () => {
    expect(dateSpanDays("2024-01-01", "2024-01-31")).toBe(30);
    expect(dateSpanDays("2024-01-01", "2024-01-01")).toBe(0);
  });

  it("handles month and year boundaries", () => {
    expect(dateSpanDays("2023-12-31", "2024-01-01")).toBe(1);
    expect(dateSpanDays("2023-01-01", "2024-01-01")).toBe(365);
  });
});

describe("addDays", () => {
  it("subtracts days across month boundaries", () => {
    expect(addDays("2024-03-01", -1)).toBe("2024-02-29");
  });
});

describe("validateDateRange", () => {
  it("accepts a valid range", () => {
    expect(validateDateRange("2025-09-01", "2025-10-01", RULES)).toBeNull();
  });

  it("rejects an end date before the start date", () => {
    expect(validateDateRange("2025-10-01", "2025-09-01", RULES)).toMatch(
      /start date must be on or before/,
    );
  });

  it("rejects ranges longer than the max span", () => {
    expect(validateDateRange("2024-01-01", "2025-06-01", RULES)).toMatch(
      /exceeds the 365-day limit/,
    );
  });

  // The cap is now multi-year, so the message must not read "3660-day".
  it("groups thousands in the multi-year span message", () => {
    const multiYear = { ...RULES, maxSpanDays: 3660, minStartDate: "2015-07-01" };
    expect(validateDateRange("2015-07-01", "2026-08-01", multiYear)).toMatch(
      /spans 4,049 days, which exceeds the 3,660-day limit/,
    );
    expect(validateDateRange("2018-01-01", "2026-01-01", multiYear)).toBeNull();
  });

  it("rejects a start before the platform minimum", () => {
    expect(validateDateRange("2016-06-01", "2016-08-01", RULES)).toMatch(
      /cannot be before 2017-01-01/,
    );
  });

  it("rejects an end date in the future", () => {
    expect(validateDateRange("2026-07-01", "2026-09-01", RULES)).toMatch(
      /cannot be in the future/,
    );
  });

  it("rejects missing or malformed dates", () => {
    expect(validateDateRange("", "2025-10-01", RULES)).toMatch(/Choose both/);
    expect(validateDateRange("2025/09/01", "2025-10-01", RULES)).toMatch(
      /YYYY-MM-DD/,
    );
  });
});
