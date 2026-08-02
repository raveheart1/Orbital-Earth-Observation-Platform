const DOCS_BASE =
  "https://github.com/raveheart1/Orbital-Earth-Observation-Platform/blob/main/docs";

/**
 * Prominent scientific-limitations disclaimer, shared by the landing page
 * and every analysis detail page.
 */
export default function LimitationsNote({
  headingLevel = "h2",
}: {
  headingLevel?: "h2" | "h3";
}) {
  const Heading = headingLevel;
  return (
    <aside className="limitations" aria-labelledby="limitations-heading">
      <Heading id="limitations-heading">
        <span aria-hidden="true">⚠</span> Interpret with care
      </Heading>
      <ul>
        <li>
          Results are <strong>observed spectral vegetation-index changes</strong>{" "}
          for the specific acquisition dates analysed — they describe what the
          satellite measured, not why it changed.
        </li>
        <li>
          NDVI alone does <strong>not</strong> prove drought, wildfire damage,
          climate change, or agricultural failure. Attributing a cause requires
          independent ground truth and additional data sources.
        </li>
        <li>
          Cloud and shadow masking via the Sentinel-2 Scene Classification Layer
          is imperfect; residual haze, cloud edges, and shadows can bias
          per-scene statistics.
        </li>
        <li>
          Scene availability is uneven over time, so first/last comparisons can
          reflect seasonality or acquisition timing rather than a trend.
        </li>
      </ul>
      <p style={{ marginTop: "0.85rem" }}>
        Read the full{" "}
        <a
          href={`${DOCS_BASE}/scientific-methodology.md`}
          target="_blank"
          rel="noopener noreferrer"
        >
          scientific methodology
        </a>{" "}
        and{" "}
        <a
          href={`${DOCS_BASE}/limitations.md`}
          target="_blank"
          rel="noopener noreferrer"
        >
          known limitations
        </a>
        .
      </p>
    </aside>
  );
}
