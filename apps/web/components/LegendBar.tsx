import type { NdviLegend } from "@/lib/schemas";
import { formatNumber } from "@/lib/format";

/**
 * NDVI color-scale legend rendered from the server-provided legend stops,
 * so the web UI and the rendered PNGs always agree.
 */
export default function LegendBar({ legend }: { legend: NdviLegend }) {
  const { display_min: min, display_max: max, stops } = legend;
  const span = max - min || 1;
  const gradientStops = [...stops]
    .sort((a, b) => a.value - b.value)
    .map((stop) => {
      const pct = ((stop.value - min) / span) * 100;
      return `${stop.color} ${Math.max(0, Math.min(100, pct)).toFixed(1)}%`;
    })
    .join(", ");

  return (
    <figure className="legend-bar">
      <figcaption className="small muted">NDVI color scale</figcaption>
      <div
        className="legend-gradient"
        style={{ background: `linear-gradient(90deg, ${gradientStops})` }}
        role="img"
        aria-label={`NDVI color scale from ${formatNumber(min, 1)} to ${formatNumber(max, 1)}`}
      />
      <div className="legend-scale" aria-hidden="true">
        <span>{formatNumber(min, 1)}</span>
        <span>{formatNumber(min + span / 2, 1)}</span>
        <span>{formatNumber(max, 1)}</span>
      </div>
      <p className="legend-masked">
        <span
          className="swatch"
          style={{ background: legend.masked_color }}
          aria-hidden="true"
        />
        Masked pixels (cloud, shadow, snow, no data) — {legend.note}
      </p>
    </figure>
  );
}
