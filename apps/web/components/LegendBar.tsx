import type { NdviLegend } from "@/lib/schemas";
import { formatNumber } from "@/lib/format";

/**
 * Preview color-scale legend rendered from the server-provided legend stops,
 * so the web UI and the rendered PNGs always agree. Distinguishes the three
 * non-colormap cases a viewer can encounter: genuinely low values (colormap),
 * masked pixels (transparent), and "no source imagery" (opaque grey). The
 * index name comes from the legend's own `type`, so an NBR legend labels
 * itself NBR without any caller wiring.
 */
export default function LegendBar({ legend }: { legend: NdviLegend }) {
  const { display_min: min, display_max: max, stops } = legend;
  const indexName = legend.type.toUpperCase();
  const span = max - min || 1;
  const gradientStops = [...stops]
    .sort((a, b) => a.value - b.value)
    .map((stop) => {
      const pct = ((stop.value - min) / span) * 100;
      return `${stop.color} ${Math.max(0, Math.min(100, pct)).toFixed(1)}%`;
    })
    .join(", ");

  const maskedLabel =
    legend.masked_label ?? "Masked pixels (cloud, shadow, snow)";

  return (
    <figure className="legend-bar">
      <figcaption className="small muted">
        {indexName} color scale — fixed display range {formatNumber(min, 1)} to{" "}
        {formatNumber(max, 1)} for every scene
      </figcaption>
      <div
        className="legend-gradient"
        style={{ background: `linear-gradient(90deg, ${gradientStops})` }}
        role="img"
        aria-label={`${indexName} color scale, fixed range from ${formatNumber(min, 1)} to ${formatNumber(max, 1)}`}
      />
      <div className="legend-scale" aria-hidden="true">
        <span>{formatNumber(min, 1)}</span>
        <span>{formatNumber(min + span / 2, 1)}</span>
        <span>{formatNumber(max, 1)}</span>
      </div>
      <div className="legend-keys">
        <p className="legend-masked">
          <span
            className="swatch"
            style={{ background: legend.masked_color }}
            aria-hidden="true"
          />
          {maskedLabel} — rendered transparent
        </p>
        {legend.nodata_color ? (
          <p className="legend-masked">
            <span
              className="swatch"
              style={{ background: legend.nodata_color }}
              aria-hidden="true"
            />
            {legend.nodata_label ?? "No source imagery"} — not low {indexName}
          </p>
        ) : null}
      </div>
      <p className="small muted" style={{ marginTop: "0.35rem" }}>
        {legend.note}
      </p>
    </figure>
  );
}
