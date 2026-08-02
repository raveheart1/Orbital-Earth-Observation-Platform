"use client";

import { useState } from "react";
import type { Artifact, ArtifactType } from "@/lib/schemas";
import { formatBytes, formatDate, shortSha, truncateMiddle } from "@/lib/format";

const TYPE_LABELS: Record<ArtifactType, string> = {
  ndvi_cog: "NDVI GeoTIFF (COG)",
  ndvi_preview: "NDVI preview (PNG)",
  true_color_preview: "True-color preview (PNG)",
  scene_summary: "Scene summary (JSON)",
  timeseries_csv: "Time series (CSV)",
  analysis_summary: "Analysis summary (JSON)",
  provenance: "Provenance record (JSON)",
};

const ANALYSIS_LEVEL: ArtifactType[] = [
  "timeseries_csv",
  "analysis_summary",
  "provenance",
];

function CopySha({ sha }: { sha: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="a-meta">
      sha256:
      <span title={sha}> {shortSha(sha, 12)}… </span>
      <button
        type="button"
        className="copy-btn"
        onClick={() => {
          void navigator.clipboard?.writeText(sha).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          });
        }}
        aria-label={`Copy full sha256 checksum ${shortSha(sha, 12)}`}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}

function ArtifactRow({ artifact }: { artifact: Artifact }) {
  return (
    <li>
      <span className="a-type">{TYPE_LABELS[artifact.artifact_type]}</span>
      <span className="a-meta">{formatBytes(artifact.size_bytes)}</span>
      <CopySha sha={artifact.sha256} />
      <a
        href={artifact.download_url}
        target="_blank"
        rel="noopener noreferrer"
        className="small"
      >
        Download
      </a>
    </li>
  );
}

/**
 * Grouped artifact downloads: analysis-level products first, then per-scene
 * outputs grouped by STAC item.
 */
export default function ArtifactList({ artifacts }: { artifacts: Artifact[] }) {
  if (artifacts.length === 0) {
    return <p className="panel-note">No artifacts have been produced yet.</p>;
  }

  const analysisLevel = artifacts.filter((a) =>
    ANALYSIS_LEVEL.includes(a.artifact_type),
  );
  const perScene = artifacts.filter(
    (a) => !ANALYSIS_LEVEL.includes(a.artifact_type),
  );

  const sceneGroups = new Map<string, Artifact[]>();
  for (const artifact of perScene) {
    const key = artifact.stac_item_id ?? artifact.scene_id ?? "unattributed";
    const group = sceneGroups.get(key);
    if (group) group.push(artifact);
    else sceneGroups.set(key, [artifact]);
  }

  return (
    <div>
      <p className="small muted">
        Download links are short-lived signed URLs — they expire after a while
        and are refreshed each time this page loads.
      </p>
      {analysisLevel.length > 0 ? (
        <div className="artifact-group">
          <h4>Analysis-level products</h4>
          <ul className="artifact-items">
            {analysisLevel.map((a) => (
              <ArtifactRow key={a.id} artifact={a} />
            ))}
          </ul>
        </div>
      ) : null}
      {[...sceneGroups.entries()].map(([itemId, group]) => {
        const first = group[0];
        return (
          <div className="artifact-group" key={itemId}>
            <h4 title={itemId}>
              Scene {truncateMiddle(itemId, 32)}
              {first ? (
                <span style={{ textTransform: "none", letterSpacing: 0 }}>
                  {" "}
                  · {formatDate(first.created_at)}
                </span>
              ) : null}
            </h4>
            <ul className="artifact-items">
              {group.map((a) => (
                <ArtifactRow key={a.id} artifact={a} />
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
