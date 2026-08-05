import type { Region } from "./schemas";

/**
 * Curated regions arrive from the API as one flat list carrying a `group`
 * label. The picker shows them bucketed by that label, so the ordering rule
 * lives here where it can be tested independently of the component.
 */

/**
 * Display order for known groups. Michigan leads: it is the project's home
 * ground and holds the demonstration analysis. Anything the catalogue adds
 * later is appended in the order the API returned it, so a new group appears
 * without a frontend change.
 */
export const REGION_GROUP_ORDER = ["Michigan", "Global"] as const;

/** Bucket used for regions whose group is missing or blank. */
export const FALLBACK_REGION_GROUP = "Global";

export interface RegionGroup {
  /** The `group` value shared by every region in this bucket. */
  name: string;
  /** Members, in the order the API listed them. */
  regions: Region[];
}

function normalizeGroup(group: string | undefined): string {
  const trimmed = group?.trim();
  return trimmed ? trimmed : FALLBACK_REGION_GROUP;
}

/** Position of a group in the display order; unknown groups sort last. */
function groupRank(name: string): number {
  const index = (REGION_GROUP_ORDER as readonly string[]).indexOf(name);
  return index === -1 ? REGION_GROUP_ORDER.length : index;
}

/**
 * Bucket regions by `group`, ordering the buckets Michigan → Global → anything
 * else. Order *within* a bucket is left exactly as the API returned it, and
 * empty buckets are never emitted, so a deployment seeded with only Michigan
 * regions renders a single heading rather than an empty "Global" one.
 */
export function groupRegions(regions: Region[]): RegionGroup[] {
  const buckets = new Map<string, Region[]>();
  for (const region of regions) {
    const name = normalizeGroup(region.group);
    const existing = buckets.get(name);
    if (existing) {
      existing.push(region);
    } else {
      buckets.set(name, [region]);
    }
  }
  // Array.prototype.sort is stable, so unknown groups (equal rank) keep the
  // order in which they first appeared.
  return [...buckets]
    .sort(([a], [b]) => groupRank(a) - groupRank(b))
    .map(([name, members]) => ({ name, regions: members }));
}

/** The region the picker should start on: first member of the first group. */
export function firstRegionId(regions: Region[]): string | null {
  return groupRegions(regions)[0]?.regions[0]?.id ?? null;
}

/** Stable DOM id for a group heading, so its list can be labelled by it. */
export function regionGroupHeadingId(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `region-group-${slug || "other"}`;
}
