/** Parse a YYYY-MM-DD string as a UTC timestamp (ms). NaN when malformed. */
export function parseIsoDate(date: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return Number.NaN;
  const [, y, m, d] = match;
  return Date.UTC(Number(y), Number(m) - 1, Number(d));
}

/** Whole days between two YYYY-MM-DD dates (end minus start). */
export function dateSpanDays(start: string, end: string): number {
  const startMs = parseIsoDate(start);
  const endMs = parseIsoDate(end);
  return Math.round((endMs - startMs) / 86_400_000);
}

/** Today's date as YYYY-MM-DD (UTC). */
export function todayIsoDate(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

/** Add (or subtract) whole days to a YYYY-MM-DD date. */
export function addDays(date: string, days: number): string {
  const ms = parseIsoDate(date) + days * 86_400_000;
  return new Date(ms).toISOString().slice(0, 10);
}

export interface DateRangeRules {
  minStartDate: string;
  maxSpanDays: number;
  today: string;
}

/**
 * Validate a start/end date pair against platform limits.
 * Returns a human-readable error message, or null when the range is valid.
 */
export function validateDateRange(
  start: string,
  end: string,
  rules: DateRangeRules,
): string | null {
  if (!start || !end) return "Choose both a start and an end date.";
  if (Number.isNaN(parseIsoDate(start)) || Number.isNaN(parseIsoDate(end))) {
    return "Dates must use the YYYY-MM-DD format.";
  }
  if (parseIsoDate(start) > parseIsoDate(end)) {
    return "The start date must be on or before the end date.";
  }
  if (parseIsoDate(start) < parseIsoDate(rules.minStartDate)) {
    return `The start date cannot be before ${rules.minStartDate} (earliest supported observation).`;
  }
  if (parseIsoDate(end) > parseIsoDate(rules.today)) {
    return "The end date cannot be in the future.";
  }
  const span = dateSpanDays(start, end);
  if (span > rules.maxSpanDays) {
    return `The date range spans ${span} days, which exceeds the ${rules.maxSpanDays}-day limit.`;
  }
  return null;
}
