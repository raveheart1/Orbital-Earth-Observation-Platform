"use client";

import type { Region } from "@/lib/schemas";
import { formatKm2 } from "@/lib/format";

/**
 * Radio-card list of predefined regions. Real radio inputs keep it fully
 * keyboard- and screen-reader-operable; the card styling is purely visual.
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
  if (regions.length === 0) {
    return <p className="panel-note">No predefined regions are available.</p>;
  }
  return (
    <ul className="region-cards">
      {regions.map((region) => (
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
  );
}
