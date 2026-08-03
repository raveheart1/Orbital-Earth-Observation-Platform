import type { Provenance } from "@/lib/schemas";
import { truncateMiddle } from "@/lib/format";

/** Render only primitive entries of an unknown record as key/value rows. */
function primitiveEntries(
  record: Record<string, unknown> | undefined,
): [string, string][] {
  if (!record) return [];
  return Object.entries(record)
    .filter(
      ([, v]) =>
        v === null ||
        typeof v === "string" ||
        typeof v === "number" ||
        typeof v === "boolean",
    )
    .map(([k, v]) => [k, v === null ? "—" : String(v)]);
}

function KvList({ entries }: { entries: [string, string][] }) {
  if (entries.length === 0) return <p className="small muted">Not recorded.</p>;
  return (
    <dl className="kv">
      {entries.map(([key, value]) => (
        <div key={key} style={{ display: "contents" }}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The provenance document, split into disclosure sections so the full
 * reproducibility record is inspectable without leaving the page.
 */
export default function ProvenancePanel({ provenance }: { provenance: Provenance }) {
  const selection = provenance.scene_selection;
  const processing = provenance.processing;
  const grid = provenance.canonical_grid;
  const software = provenance.software;

  return (
    <div>
      <details className="panel">
        <summary>Data source</summary>
        <div className="panel-body">
          <KvList entries={primitiveEntries(provenance.data_source)} />
        </div>
      </details>

      <details className="panel">
        <summary>Scene selection</summary>
        <div className="panel-body stack-s">
          <KvList
            entries={[
              ...(selection?.algorithm
                ? ([["algorithm", selection.algorithm]] as [string, string][])
                : []),
              ...(selection?.algorithm_version
                ? ([["algorithm version", selection.algorithm_version]] as [
                    string,
                    string,
                  ][])
                : []),
              ...(selection?.selected_count !== undefined
                ? ([["selected acquisitions", String(selection.selected_count)]] as [
                    string,
                    string,
                  ][])
                : []),
              ...(selection?.min_aoi_coverage_pct !== undefined
                ? ([
                    [
                      "required AOI coverage",
                      `${selection.min_aoi_coverage_pct}%`,
                    ],
                  ] as [string, string][])
                : []),
            ]}
          />
          {selection?.excluded && selection.excluded.length > 0 ? (
            <div>
              <h4 className="small" style={{ margin: "0.5rem 0 0.25rem" }}>
                Excluded acquisitions
              </h4>
              <ul className="small" style={{ margin: 0, paddingLeft: "1.25rem" }}>
                {selection.excluded.map((entry, index) => {
                  // 2.0.0 identifies an exclusion by acquisition; 1.x
                  // documents carried a single item_id.
                  const label =
                    entry.primary_item_id ??
                    entry.item_id ??
                    entry.acquisition_key ??
                    `exclusion ${index + 1}`;
                  const coverage =
                    entry.aoi_coverage_pct !== null &&
                    entry.aoi_coverage_pct !== undefined
                      ? ` (${entry.aoi_coverage_pct.toFixed(1)}% AOI coverage)`
                      : "";
                  return (
                    <li key={`${label}-${index}`}>
                      <span className="mono" title={label}>
                        {truncateMiddle(label, 30)}
                      </span>{" "}
                      — {entry.reason}
                      {coverage}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : (
            <p className="small muted">No acquisitions were excluded.</p>
          )}
        </div>
      </details>

      {grid ? (
        <details className="panel">
          <summary>Analytical grid</summary>
          <div className="panel-body">
            <p className="small muted" style={{ marginTop: 0 }}>
              Every observation in this analysis was reprojected onto this single
              grid, so all dates measure the identical ground.
            </p>
            <KvList
              entries={[
                ...(grid.crs ? ([["CRS", grid.crs]] as [string, string][]) : []),
                ...(grid.width && grid.height
                  ? ([["size", `${grid.width} x ${grid.height} px`]] as [
                      string,
                      string,
                    ][])
                  : []),
                ...(grid.resolution?.length
                  ? ([["resolution", `${grid.resolution[0]} m`]] as [
                      string,
                      string,
                    ][])
                  : []),
                ...(grid.transform?.length
                  ? ([["transform", grid.transform.join(", ")]] as [
                      string,
                      string,
                    ][])
                  : []),
                ...(grid.bounds_projected?.length
                  ? ([["projected bounds", grid.bounds_projected.join(", ")]] as [
                      string,
                      string,
                    ][])
                  : []),
                ...(processing?.mosaic_method
                  ? ([["mosaic method", processing.mosaic_method]] as [
                      string,
                      string,
                    ][])
                  : []),
                ...(processing?.resampling_spectral
                  ? ([
                      [
                        "resampling (spectral)",
                        processing.resampling_spectral,
                      ],
                    ] as [string, string][])
                  : []),
                ...(processing?.resampling_categorical
                  ? ([
                      [
                        "resampling (SCL, categorical)",
                        processing.resampling_categorical,
                      ],
                    ] as [string, string][])
                  : []),
              ]}
            />
          </div>
        </details>
      ) : null}

      <details className="panel">
        <summary>Mask policy</summary>
        <div className="panel-body">
          {processing?.masked_scl_class_names?.length ? (
            <p className="small">
              Pixels in these Sentinel-2 Scene Classification (SCL) classes are
              masked before any statistic is computed:{" "}
              <span className="mono">
                {processing.masked_scl_class_names.join(", ")}
              </span>
              {processing.masked_scl_classes?.length ? (
                <>
                  {" "}
                  (class codes{" "}
                  <span className="mono">
                    {processing.masked_scl_classes.join(", ")}
                  </span>
                  )
                </>
              ) : null}
              .
            </p>
          ) : (
            <p className="small muted">Mask policy not recorded.</p>
          )}
        </div>
      </details>

      <details className="panel">
        <summary>Software versions</summary>
        <div className="panel-body stack-s">
          <KvList
            entries={primitiveEntries(
              software as Record<string, unknown> | undefined,
            ).filter(([k]) => k !== "key_packages")}
          />
          {software?.key_packages ? (
            <div>
              <h4 className="small" style={{ margin: "0.5rem 0 0.25rem" }}>
                Key packages
              </h4>
              <KvList entries={Object.entries(software.key_packages)} />
            </div>
          ) : null}
        </div>
      </details>

      <details className="panel">
        <summary>Timing</summary>
        <div className="panel-body">
          <KvList entries={primitiveEntries(provenance.timing)} />
        </div>
      </details>
    </div>
  );
}
