"use client";

import Link from "next/link";
import { useState } from "react";
import { getAnalyses } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import { formatDate, formatDateTime, formatKm2 } from "@/lib/format";
import { EmptyBox, ErrorBox, LoadingBox } from "./FetchStates";
import StatusBadge from "./StatusBadge";

const PAGE_SIZE = 20;

export default function AnalysesTable() {
  const [offset, setOffset] = useState(0);
  const { state, reload } = useFetch(
    () => getAnalyses(PAGE_SIZE, offset),
    [offset],
  );

  if (state.status === "loading" || state.status === "idle") {
    return <LoadingBox label="Loading analyses…" />;
  }
  if (state.status === "error") {
    return <ErrorBox message={state.error} onRetry={reload} />;
  }

  const { items, total } = state.data;

  if (total === 0) {
    return (
      <EmptyBox>
        No analyses have been run yet.{" "}
        <Link href="/analyses/new">Run the first one</Link>.
      </EmptyBox>
    );
  }

  const pageStart = offset + 1;
  const pageEnd = offset + items.length;

  return (
    <div>
      <div className="table-scroll">
        <table className="data">
          <caption>
            Submitted analyses, most recent first ({pageStart}–{pageEnd} of{" "}
            {total}).
          </caption>
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Area</th>
              <th scope="col">Date range</th>
              <th scope="col" className="num">
                Area (km²)
              </th>
              <th scope="col">Submitted (UTC)</th>
              <th scope="col">
                <span className="visually-hidden">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((analysis) => (
              <tr key={analysis.id}>
                <td>
                  <StatusBadge status={analysis.status} />
                </td>
                <td>
                  {analysis.region?.name ?? "Custom area"}
                  {analysis.is_demo ? (
                    <span className="small muted"> (demo)</span>
                  ) : null}
                </td>
                <td className="mono">
                  {formatDate(analysis.start_date)} →{" "}
                  {formatDate(analysis.end_date)}
                </td>
                <td className="num">{formatKm2(analysis.area_km2)}</td>
                <td className="mono">{formatDateTime(analysis.submitted_at)}</td>
                <td>
                  <Link href={`/analyses/${analysis.id}`}>View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > PAGE_SIZE ? (
        <nav className="pager" aria-label="Analyses pagination">
          <button
            type="button"
            className="btn btn-small"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="muted">
            {pageStart}–{pageEnd} of {total}
          </span>
          <button
            type="button"
            className="btn btn-small"
            disabled={pageEnd >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </nav>
      ) : null}
    </div>
  );
}
