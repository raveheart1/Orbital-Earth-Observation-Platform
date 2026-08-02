/** Formatting helpers. All date output is UTC so renders are deterministic. */

/** "2024-06-01T16:39:01Z" → "2024-06-01". Tolerates bare dates. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

/** "2024-06-01T16:39:01Z" → "2024-06-01 16:39 UTC". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(
    date.getUTCDate(),
  )} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

/** Humanize a byte count: 0 → "0 B", 1536 → "1.5 KB", 20971520 → "20 MB". */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = "B";
  for (const next of units) {
    if (value < 1024) break;
    value /= 1024;
    unit = next;
  }
  const rendered = value >= 10 ? String(Math.round(value)) : value.toFixed(1);
  return `${rendered} ${unit}`;
}

/** Fixed-precision number with a true minus sign; "—" for null. */
export function formatNumber(
  value: number | null | undefined,
  digits = 3,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits).replace("-", "−");
}

/** Signed change, e.g. +0.042 / −0.017. */
export function formatChange(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  return `${sign}${Math.abs(value).toFixed(digits)}`;
}

/** Percentage with one decimal, e.g. 93.5%. */
export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

/** Area in km² with thousands separators. */
export function formatKm2(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = value >= 100 ? Math.round(value) : Number(value.toFixed(1));
  return `${rounded.toLocaleString("en-US")} km²`;
}

/** Shorten long identifiers, keeping both ends: "S2A_MSIL2A_2024…T17TKG". */
export function truncateMiddle(value: string, maxLength = 24): string {
  if (value.length <= maxLength) return value;
  const keep = Math.max(4, Math.floor((maxLength - 1) / 2));
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

/** First 8 hex chars of a digest for compact display. */
export function shortSha(value: string | null | undefined, length = 8): string {
  if (!value) return "—";
  return value.slice(0, length);
}
