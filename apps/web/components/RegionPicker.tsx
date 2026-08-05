"use client";

import { useMemo } from "react";
import { groupRegions, regionGroupHeadingId } from "@/lib/regions";
import type { Region } from "@/lib/schemas";
import { formatKm2 } from "@/lib/format";

/**
 * Radio-card list of predefined regions, bucketed by catalogue group (Michigan
 * first, then the worldwide regions). Real radio inputs keep it fully keyboard-
 * and screen-reader-operable — every card shares one `name`, so arrow keys move
 * across group boundaries as a single choice — and the card styling is purely
 * visual. Each list is labelled by its heading so the grouping is announced.
 */
export default function RegionPicker({
  regions,
  selectedId,
  onSelect,
}: {
  regions: Region[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const groups = useMemo(() => groupRegions(regions), [regions]);

  if (regions.length === 0) {
    return <p className="panel-note">No predefined regions are available.</p>;
  }
  return (
    <div className="region-groups">
      {groups.map((group) => {
        const headingId = regionGroupHeadingId(group.name);
        return (
          <div className="region-group" key={group.name}>
            <h2 className="region-group-heading" id={headingId}>
              {group.name}
            </h2>
            <ul className="region-cards" aria-labelledby={headingId}>
              {group.regions.map((region) => (
                <li key={region.id}>
                  <label className="region-card">
                    <input
                      type="radio"
                      name="region"
                      value={region.id}
                      checked={selectedId === region.id}
                      onChange={() => onSelect(region.id)}
                    />
                    <span>
                      <span className="region-name">{region.name}</span>{" "}
                      <span className="mono small muted">
                        {formatKm2(region.area_km2)}
                      </span>
                      <span className="region-desc" style={{ display: "block" }}>
                        {region.description}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
