/**
 * Observation-selection strategy helpers — pure, so both the submission form
 * and the analysis detail page describe the choice identically.
 *
 * Why the choice matters: in a temperate region NDVI swings from roughly 0.15
 * (dormant winter) to 0.85 (peak summer), while a genuine multi-year trend is
 * on the order of 0.02–0.05. A series spread evenly across several years
 * therefore mostly measures which month each scene happened to fall in.
 * Sampling the same part of the calendar every year holds phenology roughly
 * constant, so what is left is closer to a change in the surface itself.
 */

import { parseIsoDate } from "./dates";
import type { SelectionStrategy } from "./schemas";

export const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

/** "July" for 7; null for anything outside 1–12. */
export function monthName(month: number | null | undefined): string | null {
  if (month === null || month === undefined || !Number.isInteger(month)) {
    return null;
  }
  return MONTH_NAMES[month - 1] ?? null;
}

/**
 * The calendar month at the midpoint of a date range (1–12), which is the
 * natural default anchor: it is the part of the year the visitor's window is
 * centred on. Null when either date is unusable.
 */
export function midpointMonth(start: string, end: string): number | null {
  const startMs = parseIsoDate(start);
  const endMs = parseIsoDate(end);
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) {
    return null;
  }
  const midpoint = new Date(Math.round((startMs + endMs) / 2));
  return midpoint.getUTCMonth() + 1;
}

/**
 * Whether to nudge the visitor towards seasonal selection. Advice only — the
 * form never blocks a temporal submission over a long range.
 */
export function shouldSuggestSeasonal({
  spanDays,
  strategy,
  recommendedAboveDays,
}: {
  spanDays: number;
  strategy: SelectionStrategy | string;
  recommendedAboveDays: number;
}): boolean {
  if (strategy !== "temporal") return false;
  if (!Number.isFinite(spanDays) || !Number.isFinite(recommendedAboveDays)) {
    return false;
  }
  return spanDays > recommendedAboveDays;
}

/** Short label for a strategy on its own, without the target month. */
export function selectionStrategyName(strategy: string): string {
  if (strategy === "seasonal") return "Same season each year";
  if (strategy === "temporal") return "Spread across the range";
  return strategy;
}

/**
 * Human-readable description of how an analysis chose its observations, e.g.
 * "Same season each year (target: July)".
 */
export function describeSelectionStrategy(analysis: {
  selection_strategy: string;
  seasonal_target_month?: number | null;
}): string {
  const name = selectionStrategyName(analysis.selection_strategy);
  if (analysis.selection_strategy !== "seasonal") return name;
  const target = monthName(analysis.seasonal_target_month);
  return target ? `${name} (target: ${target})` : name;
}
