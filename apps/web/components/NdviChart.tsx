"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TimeseriesPoint } from "@/lib/schemas";
import { toChartPoints, type ChartPoint } from "@/lib/timeseries";
import { formatNumber, formatPct } from "@/lib/format";

const ACCENT = "#0c5a63";
const GRID = "#e7e5dc";
const AXIS_INK = "#44545a";

function formatTick(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

interface TooltipContentProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: ChartPoint }>;
}

function ChartTooltip({ active, payload }: TooltipContentProps) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="chart-tooltip">
      <p className="tt-date">{point.date}</p>
      <p>
        Mean NDVI: <span className="num">{formatNumber(point.mean)}</span>
      </p>
      <p>
        Median: <span className="num">{formatNumber(point.median)}</span>
      </p>
      <p>
        p25–p75: <span className="num">{formatNumber(point.p25)}</span> –{" "}
        <span className="num">{formatNumber(point.p75)}</span>
      </p>
      <p>
        Valid pixels: <span className="num">{formatPct(point.validPixelPct)}</span>
      </p>
      <p>
        AOI coverage: <span className="num">{formatPct(point.aoiCoveragePct)}</span>
      </p>
      <p>
        Source granules: <span className="num">{point.granuleCount}</span>
        {point.granuleCount > 1 && point.tileIds.length > 0
          ? ` (${point.tileIds.join(", ")})`
          : null}
      </p>
      <p>
        Scene cloud cover: <span className="num">{formatPct(point.cloudPct)}</span>
      </p>
    </div>
  );
}

/**
 * NDVI time series: mean NDVI per usable scene plotted on a true time axis
 * (observation dates, no interpolation between them), with a shaded
 * interquartile (p25–p75) band. The same data is available as an accessible
 * table below the chart.
 */
export default function NdviChart({ points }: { points: TimeseriesPoint[] }) {
  const data = toChartPoints(points);

  if (data.length === 0) {
    return (
      <p className="panel-note">
        No usable observations were produced, so there is no time series to
        plot.
      </p>
    );
  }

  const values = data.flatMap((d) =>
    [d.mean, d.p25, d.p75].filter((v): v is number => v !== null),
  );
  const lo = values.length ? Math.min(...values) : 0;
  const hi = values.length ? Math.max(...values) : 1;
  const yMin = Math.max(-1, Math.floor((lo - 0.05) * 10) / 10);
  const yMax = Math.min(1, Math.ceil((hi + 0.05) * 10) / 10);

  return (
    <div>
      <div className="chart-frame">
        <div style={{ width: "100%", height: 320 }}>
          <ResponsiveContainer>
            <ComposedChart
              data={data}
              margin={{ top: 8, right: 16, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatTick}
                tick={{ fill: AXIS_INK, fontSize: 12 }}
                tickLine={{ stroke: GRID }}
                axisLine={{ stroke: GRID }}
                minTickGap={40}
              />
              <YAxis
                domain={[yMin, yMax]}
                tick={{ fill: AXIS_INK, fontSize: 12 }}
                tickLine={{ stroke: GRID }}
                axisLine={{ stroke: GRID }}
                width={48}
                tickFormatter={(v: number) => v.toFixed(1)}
                label={{
                  value: "NDVI",
                  angle: -90,
                  position: "insideLeft",
                  fill: AXIS_INK,
                  fontSize: 12,
                }}
              />
              <Tooltip content={<ChartTooltip />} isAnimationActive={false} />
              <Area
                dataKey="band"
                stroke="none"
                fill={ACCENT}
                fillOpacity={0.16}
                connectNulls={false}
                isAnimationActive={false}
                activeDot={false}
                name="p25–p75 band"
              />
              <Line
                dataKey="mean"
                stroke={ACCENT}
                strokeWidth={2}
                dot={{ r: 3.5, fill: ACCENT, strokeWidth: 0 }}
                activeDot={{ r: 5 }}
                connectNulls={false}
                isAnimationActive={false}
                name="Mean NDVI"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="chart-legend">
          <span className="key">
            <span className="key-line" aria-hidden="true" />
            Mean NDVI per scene
          </span>
          <span className="key">
            <span className="key-band" aria-hidden="true" />
            Interquartile range (p25–p75)
          </span>
        </p>
      </div>

      <details className="panel" style={{ marginTop: "0.75rem" }}>
        <summary>View chart data as table</summary>
        <div className="panel-body table-scroll" style={{ border: "none" }}>
          <table className="data">
            <caption>
              NDVI statistics per usable scene, ordered by acquisition
              (sensing) date.
            </caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col" className="num">
                  Mean
                </th>
                <th scope="col" className="num">
                  Median
                </th>
                <th scope="col" className="num">
                  p25
                </th>
                <th scope="col" className="num">
                  p75
                </th>
                <th scope="col" className="num">
                  Valid px
                </th>
                <th scope="col" className="num">
                  AOI cover
                </th>
                <th scope="col">Granules</th>
                <th scope="col" className="num">
                  Cloud
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.stacItemId + d.t}>
                  <td className="mono">{d.date}</td>
                  <td className="num">{formatNumber(d.mean)}</td>
                  <td className="num">{formatNumber(d.median)}</td>
                  <td className="num">{formatNumber(d.p25)}</td>
                  <td className="num">{formatNumber(d.p75)}</td>
                  <td className="num">{formatPct(d.validPixelPct)}</td>
                  <td className="num">{formatPct(d.aoiCoveragePct)}</td>
                  <td>
                    <span className="mono">{d.granuleCount}</span>
                    {d.granuleCount > 1 && d.tileIds.length > 0 ? (
                      <span className="small muted"> · {d.tileIds.join(", ")}</span>
                    ) : null}
                  </td>
                  <td className="num">{formatPct(d.cloudPct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
