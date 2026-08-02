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
                ? ([["selected scenes", String(selection.selected_count)]] as [
                    string,
                    string,
                  ][])
                : []),
            ]}
          />
          {selection?.excluded && selection.excluded.length > 0 ? (
            <div>
              <h4 className="small" style={{ margin: "0.5rem 0 0.25rem" }}>
                Excluded scenes
              </h4>
              <ul className="small" style={{ margin: 0, paddingLeft: "1.25rem" }}>
                {selection.excluded.map((entry) => (
                  <li key={entry.item_id}>
                    <span className="mono" title={entry.item_id}>
                      {truncateMiddle(entry.item_id, 30)}
                    </span>{" "}
                    — {entry.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="small muted">No scenes were excluded.</p>
          )}
        </div>
      </details>

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
