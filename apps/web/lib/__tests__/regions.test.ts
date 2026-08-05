import { describe, expect, it } from "vitest";
import {
  firstRegionId,
  groupRegions,
  regionGroupHeadingId,
} from "@/lib/regions";
import { RegionSchema, type Region } from "@/lib/schemas";
import { regionFixture } from "./fixtures";

/** A parsed region with the given slug/group, so `group` gets its schema default. */
function region(slug: string, group?: string): Region {
  const payload: Record<string, unknown> = {
    ...regionFixture,
    id: `id-${slug}`,
    slug,
    name: slug,
  };
  if (group === undefined) delete payload.group;
  else payload.group = group;
  return RegionSchema.parse(payload);
}

/** Compact view of the grouping result: [[groupName, slugs], …]. */
function shape(regions: Region[]): [string, string[]][] {
  return groupRegions(regions).map((group) => [
    group.name,
    group.regions.map((r) => r.slug),
  ]);
}

describe("groupRegions", () => {
  it("puts Michigan before Global even when the API lists Global first", () => {
    expect(
      shape([region("nile", "Global"), region("detroit", "Michigan")]),
    ).toEqual([
      ["Michigan", ["detroit"]],
      ["Global", ["nile"]],
    ]);
  });

  it("preserves the API's order within each group", () => {
    const regions = [
      region("demo", "Michigan"),
      region("okavango", "Global"),
      region("detroit", "Michigan"),
      region("mekong", "Global"),
      region("hartwick", "Michigan"),
    ];
    expect(shape(regions)).toEqual([
      ["Michigan", ["demo", "detroit", "hartwick"]],
      ["Global", ["okavango", "mekong"]],
    ]);
  });

  it("emits only the groups that have members", () => {
    expect(shape([region("demo", "Michigan")])).toEqual([
      ["Michigan", ["demo"]],
    ]);
    expect(shape([region("nile", "Global")])).toEqual([["Global", ["nile"]]]);
  });

  it("appends unknown groups after the known ones, in first-appearance order", () => {
    const regions = [
      region("polar", "Arctic"),
      region("nile", "Global"),
      region("reef", "Marine"),
      region("demo", "Michigan"),
      region("tundra", "Arctic"),
    ];
    expect(shape(regions)).toEqual([
      ["Michigan", ["demo"]],
      ["Global", ["nile"]],
      ["Arctic", ["polar", "tundra"]],
      ["Marine", ["reef"]],
    ]);
  });

  it("falls back to Global for a missing or blank group", () => {
    expect(shape([region("legacy"), region("blank", "   ")])).toEqual([
      ["Global", ["legacy", "blank"]],
    ]);
  });

  it("trims incidental whitespace rather than creating a near-duplicate group", () => {
    expect(shape([region("a", "Michigan"), region("b", " Michigan ")])).toEqual([
      ["Michigan", ["a", "b"]],
    ]);
  });

  it("returns no groups for an empty catalogue", () => {
    expect(groupRegions([])).toEqual([]);
  });

  it("does not mutate or reorder the input array", () => {
    const regions = [region("nile", "Global"), region("demo", "Michigan")];
    groupRegions(regions);
    expect(regions.map((r) => r.slug)).toEqual(["nile", "demo"]);
  });
});

describe("firstRegionId", () => {
  it("picks the first region of the first group, not the first of the payload", () => {
    const regions = [
      region("nile", "Global"),
      region("demo", "Michigan"),
      region("detroit", "Michigan"),
    ];
    expect(firstRegionId(regions)).toBe("id-demo");
  });

  it("returns null when there are no regions", () => {
    expect(firstRegionId([])).toBeNull();
  });
});

describe("regionGroupHeadingId", () => {
  it("derives a stable, unique DOM id per group", () => {
    expect(regionGroupHeadingId("Michigan")).toBe("region-group-michigan");
    expect(regionGroupHeadingId("Global")).toBe("region-group-global");
    expect(regionGroupHeadingId("South America")).toBe(
      "region-group-south-america",
    );
  });

  it("still produces a usable id for a group with no word characters", () => {
    expect(regionGroupHeadingId("—")).toBe("region-group-other");
  });
});
