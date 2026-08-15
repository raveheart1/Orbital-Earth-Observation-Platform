import { formatChange, formatNumber } from "@/lib/format";
import { operationUi, type OperationUi } from "@/lib/operations";

/**
 * Diverging color-scale legend for the change preview. The stops mirror the
 * worker's fixed BrBG ramp (`_CHANGE_STOPS` in earth_observation's previews
 * module) — shared by every operation — so this legend and the rendered PNGs
 * always agree: brown = index loss, near-white = no change, blue-green =
 * gain, with the center stop exactly at delta zero. The wording comes from
 * the operation's UI metadata (NDVI loss/greening vs NBR burn severity).
 */
const CHANGE_STOPS: { position: number; color: string }[] = [
  { position: 0.0, color: "#543005" },
  { position: 0.17, color: "#bf812d" },
  { position: 0.33, color: "#dfc27d" },
  { position: 0.5, color: "#f5f5f5" },
  { position: 0.67, color: "#80cdc1" },
  { position: 0.83, color: "#35978f" },
  { position: 1.0, color: "#003c30" },
];

export default function ChangeLegendBar({
  displayRange,
  op,
}: {
  displayRange: number;
  /** Operation wording; defaults to NDVI so existing callers are unchanged. */
  op?: OperationUi;
}) {
  const wording = op ?? operationUi("ndvi");
  const gradientStops = CHANGE_STOPS.map(
    (stop) => `${stop.color} ${(stop.position * 100).toFixed(1)}%`,
  ).join(", ");
  const minLabel = formatChange(-displayRange, 1);
  const maxLabel = formatChange(displayRange, 1);

  return (
    <figure className="legend-bar">
      <figcaption className="small muted">
        Δ{wording.name} color scale — fixed symmetric display range {minLabel} to{" "}
        {maxLabel}, centered at zero
      </figcaption>
      <div
        className="legend-gradient"
        style={{ background: `linear-gradient(90deg, ${gradientStops})` }}
        role="img"
        aria-label={`${wording.name} change color scale, fixed symmetric range from ${minLabel} to ${maxLabel} centered at zero`}
      />
      <div className="legend-scale" aria-hidden="true">
        <span>{minLabel}</span>
        <span>{formatNumber(0, 1)}</span>
        <span>{maxLabel}</span>
      </div>
      <div className="legend-keys">
        <p className="legend-masked">
          <span
            className="swatch"
            style={{ background: "transparent" }}
            aria-hidden="true"
          />
          No valid observation on one or both dates — rendered transparent
        </p>
      </div>
      <p className="small muted" style={{ marginTop: "0.35rem" }}>
        {wording.changeLegendNote}
      </p>
    </figure>
  );
}
