import type { Scene } from "@/lib/schemas";
import { formatDateTime, formatPct, truncateMiddle } from "@/lib/format";
import { humanizeExclusionReason } from "@/lib/reasons";

/**
 * All candidate scenes considered for the analysis. Excluded scenes stay in
 * the table (reproducibility: what was rejected matters) but are visually
 * muted and labeled with a human-readable exclusion reason.
 */
export default function SceneTable({ scenes }: { scenes: Scene[] }) {
  if (scenes.length === 0) {
    return <p className="panel-note">No scenes were returned for this analysis.</p>;
  }
  const sorted = [...scenes].sort(
    (a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at),
  );
  return (
    <div className="table-scroll">
      <table className="data">
        <caption>
          {scenes.length} candidate Sentinel-2 acquisitions, ordered by
          acquisition (sensing) date — not processing date. Excluded scenes are
          shown muted with the reason.
        </caption>
        <thead>
          <tr>
            <th scope="col">STAC item</th>
            <th scope="col">Acquired (UTC)</th>
            <th scope="col" className="num">
              Cloud
            </th>
            <th scope="col" className="num">
              AOI cover
            </th>
            <th scope="col">Granules</th>
            <th scope="col">Selection</th>
            <th scope="col" className="num">
              Valid px
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((scene) => {
            const excluded = scene.selection_status === "excluded";
            const reason = excluded
              ? humanizeExclusionReason(
                  scene.exclusion_reason,
                  scene.aoi_coverage_pct,
                )
              : null;
            const validPixelPct =
              scene.valid_pixel_pct ?? scene.quality?.valid_pixel_pct ?? null;
            return (
              <tr key={scene.id} className={excluded ? "row-muted" : undefined}>
                <td className="mono" title={scene.stac_item_id}>
                  {truncateMiddle(scene.stac_item_id, 28)}
                </td>
                <td className="mono">{formatDateTime(scene.observed_at)}</td>
                <td className="num">{formatPct(scene.cloud_cover_pct)}</td>
                <td className="num">{formatPct(scene.aoi_coverage_pct)}</td>
                <td>
                  <span className="mono">{scene.granule_count}</span>
                  {scene.granule_count > 1 && scene.tile_ids.length > 0 ? (
                    <span className="small muted">
                      {" "}
                      · {scene.tile_ids.join(", ")}
                    </span>
                  ) : null}
                </td>
                <td>
                  {excluded ? (
                    <>
                      Excluded
                      {reason ? (
                        <span className="small muted"> — {reason}</span>
                      ) : null}
                    </>
                  ) : (
                    "Selected"
                  )}
                </td>
                <td className="num">{formatPct(validPixelPct)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
