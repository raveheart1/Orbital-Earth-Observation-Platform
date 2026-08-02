import type { AnalysisStatus } from "./schemas";

export const TERMINAL_STATUSES: readonly AnalysisStatus[] = [
  "succeeded",
  "failed",
  "cancelled",
];

/** True when the analysis will never change state again — polling must stop. */
export function isTerminalStatus(status: AnalysisStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

const FAST_POLL_WINDOW_MS = 30_000;
const FAST_POLL_INTERVAL_MS = 3_000;
const SLOW_POLL_INTERVAL_MS = 10_000;

/**
 * Poll cadence for a queued/running analysis: every 3 s for the first 30 s
 * after polling began, then every 10 s.
 */
export function nextPollDelayMs(elapsedMs: number): number {
  return elapsedMs < FAST_POLL_WINDOW_MS
    ? FAST_POLL_INTERVAL_MS
    : SLOW_POLL_INTERVAL_MS;
}
