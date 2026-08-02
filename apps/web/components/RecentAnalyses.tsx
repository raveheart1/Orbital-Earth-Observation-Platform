"use client";

import Link from "next/link";
import { getAnalyses } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";
import { formatDate, formatDateTime, formatKm2 } from "@/lib/format";
import { EmptyBox, ErrorBox, LoadingBox } from "./FetchStates";
import StatusBadge from "./StatusBadge";

/** The five most recently submitted analyses, linking to their detail pages. */
export default function RecentAnalyses() {
  const { state, reload } = useFetch(() => getAnalyses(5, 0), []);

  if (state.status === "loading" || state.status === "idle") {
    return <LoadingBox label="Loading recent analyses…" />;
  }
  if (state.status === "error") {
    return <ErrorBox message={state.error} onRetry={reload} />;
  }
  if (state.data.items.length === 0) {
    return (
      <EmptyBox>
        No analyses have been run yet.{" "}
        <Link href="/analyses/new">Run the first one</Link>.
      </EmptyBox>
    );
  }

  return (
    <ul className="recent-list">
      {state.data.items.map((analysis) => (
        <li key={analysis.id}>
          <Link href={`/analyses/${analysis.id}`}>
            <StatusBadge status={analysis.status} />
            <span style={{ fontWeight: 600 }}>
              {analysis.region?.name ?? "Custom area"}
            </span>
            <span className="mono small muted">
              {formatDate(analysis.start_date)} → {formatDate(analysis.end_date)}
            </span>
            <span className="mono small muted">{formatKm2(analysis.area_km2)}</span>
            <span className="small muted">
              submitted {formatDateTime(analysis.submitted_at)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
