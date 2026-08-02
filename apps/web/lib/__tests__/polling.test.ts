import { describe, expect, it } from "vitest";
import { isTerminalStatus, nextPollDelayMs } from "@/lib/polling";

describe("nextPollDelayMs", () => {
  it("polls every 3 s during the first 30 s", () => {
    expect(nextPollDelayMs(0)).toBe(3000);
    expect(nextPollDelayMs(15_000)).toBe(3000);
    expect(nextPollDelayMs(29_999)).toBe(3000);
  });

  it("backs off to 10 s from 30 s onward", () => {
    expect(nextPollDelayMs(30_000)).toBe(10_000);
    expect(nextPollDelayMs(31_000)).toBe(10_000);
    expect(nextPollDelayMs(600_000)).toBe(10_000);
  });
});

describe("isTerminalStatus", () => {
  it("treats succeeded/failed/cancelled as terminal", () => {
    expect(isTerminalStatus("succeeded")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
    expect(isTerminalStatus("cancelled")).toBe(true);
  });

  it("keeps polling for queued/running", () => {
    expect(isTerminalStatus("queued")).toBe(false);
    expect(isTerminalStatus("running")).toBe(false);
  });
});
