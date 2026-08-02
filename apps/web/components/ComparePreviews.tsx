import type { Artifact, NdviLegend, TimeseriesPoint } from "@/lib/schemas";
import { findSceneArtifact, selectComparisonPoints } from "@/lib/timeseries";
import { formatDate } from "@/lib/format";
import LegendBar from "./LegendBar";

function PreviewCell({
  artifact,
  alt,
  label,
  date,
}: {
  artifact: Artifact | null;
  alt: string;
  label: string;
  date: string;
}) {
  return (
    <figure className="compare-cell">
      {artifact ? (
        <img src={artifact.download_url} alt={alt} loading="lazy" />
      ) : (
        <div className="compare-missing" role="img" aria-label={`${alt} (not available)`}>
          Preview not available
        </div>
      )}
      <figcaption>
        <span>{label}</span>
        <span className="mono">{date}</span>
      </figcaption>
    </figure>
  );
}

/**
 * Before/after comparison for the earliest and latest usable scenes:
 * true-color previews on top, NDVI previews below, with the NDVI color
 * legend. Scenes are matched to artifacts via their STAC item id.
 */
export default function ComparePreviews({
  points,
  artifacts,
  legend,
  areaLabel,
}: {
  points: TimeseriesPoint[];
  artifacts: Artifact[];
  legend: NdviLegend;
  areaLabel: string;
}) {
  const comparison = selectComparisonPoints(points);
  if (!comparison) {
    return (
      <p className="panel-note">
        A before/after comparison needs at least two usable observations; this
        analysis produced {points.length === 1 ? "only one" : "none"}.
      </p>
    );
  }

  const { first, last } = comparison;
  const firstDate = formatDate(first.observed_at);
  const lastDate = formatDate(last.observed_at);

  const cells = [
    {
      key: "tc-first",
      artifact: findSceneArtifact(artifacts, first.stac_item_id, "true_color_preview"),
      alt: `True-color Sentinel-2 image of ${areaLabel} on ${firstDate}`,
      label: "True color — earliest",
      date: firstDate,
    },
    {
      key: "tc-last",
      artifact: findSceneArtifact(artifacts, last.stac_item_id, "true_color_preview"),
      alt: `True-color Sentinel-2 image of ${areaLabel} on ${lastDate}`,
      label: "True color — latest",
      date: lastDate,
    },
    {
      key: "ndvi-first",
      artifact: findSceneArtifact(artifacts, first.stac_item_id, "ndvi_preview"),
      alt: `NDVI map of ${areaLabel} on ${firstDate}; greener shades indicate denser, healthier vegetation`,
      label: "NDVI — earliest",
      date: firstDate,
    },
    {
      key: "ndvi-last",
      artifact: findSceneArtifact(artifacts, last.stac_item_id, "ndvi_preview"),
      alt: `NDVI map of ${areaLabel} on ${lastDate}; greener shades indicate denser, healthier vegetation`,
      label: "NDVI — latest",
      date: lastDate,
    },
  ];

  return (
    <div>
      <div className="compare-grid">
        {cells.map(({ key, ...cell }) => (
          <PreviewCell key={key} {...cell} />
        ))}
      </div>
      <LegendBar legend={legend} />
    </div>
  );
}
