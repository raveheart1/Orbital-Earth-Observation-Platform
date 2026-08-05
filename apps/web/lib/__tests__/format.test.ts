import { describe, expect, it } from "vitest";
import {
  formatAreaLimitKm2,
  formatBytes,
  formatChange,
  formatDate,
  formatDateTime,
  formatKm2,
  truncateMiddle,
} from "@/lib/format";

describe("formatBytes", () => {
  it("humanizes byte counts", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(532)).toBe("532 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(20 * 1024 * 1024)).toBe("20 MB");
  });

  it("returns a dash for invalid input", () => {
    expect(formatBytes(-1)).toBe("—");
    expect(formatBytes(Number.NaN)).toBe("—");
  });
});

describe("formatChange", () => {
  it("renders explicit signs", () => {
    expect(formatChange(0.081)).toBe("+0.081");
    expect(formatChange(-0.081)).toBe("−0.081");
    expect(formatChange(null)).toBe("—");
  });
});

describe("formatKm2", () => {
  it("keeps two decimals below 10 km², where the custom cap lives", () => {
    expect(formatKm2(1.4)).toBe("1.40 km²");
    expect(formatKm2(2)).toBe("2.00 km²");
    expect(formatKm2(2.4567)).toBe("2.46 km²");
    expect(formatKm2(0.5)).toBe("0.50 km²");
    expect(formatKm2(9.994)).toBe("9.99 km²");
  });

  it("stays coarse for the larger predefined regions", () => {
    expect(formatKm2(84.2)).toBe("84.2 km²");
    expect(formatKm2(137.4)).toBe("137 km²");
    expect(formatKm2(2500)).toBe("2,500 km²");
  });

  it("returns a dash for missing values", () => {
    expect(formatKm2(null)).toBe("—");
    expect(formatKm2(Number.NaN)).toBe("—");
  });
});

describe("formatAreaLimitKm2", () => {
  it("renders configured limits without trailing zeros", () => {
    expect(formatAreaLimitKm2(2)).toBe("2 km²");
    expect(formatAreaLimitKm2(0.5)).toBe("0.5 km²");
    expect(formatAreaLimitKm2(250)).toBe("250 km²");
    expect(formatAreaLimitKm2(null)).toBe("—");
  });
});

describe("date formatting", () => {
  it("formats dates and datetimes in UTC", () => {
    expect(formatDate("2023-05-04T16:32:11Z")).toBe("2023-05-04");
    expect(formatDateTime("2023-05-04T16:32:11Z")).toBe("2023-05-04 16:32 UTC");
    expect(formatDate(null)).toBe("—");
  });
});

describe("truncateMiddle", () => {
  it("keeps both ends of long identifiers", () => {
    const id = "S2A_MSIL2A_20230504T163211_R041_T17TKG_20230504T221755";
    const short = truncateMiddle(id, 24);
    expect(short.length).toBeLessThanOrEqual(24);
    expect(short).toContain("…");
    expect(short.startsWith("S2A_")).toBe(true);
    expect(short.endsWith("1755")).toBe(true);
  });

  it("leaves short strings untouched", () => {
    expect(truncateMiddle("short-id", 24)).toBe("short-id");
  });
});
