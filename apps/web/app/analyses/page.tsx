import type { Metadata } from "next";
import Link from "next/link";
import AnalysesTable from "@/components/AnalysesTable";

export const metadata: Metadata = {
  title: "Analyses",
  description: "All NDVI analyses submitted to the platform.",
};

export default function AnalysesPage() {
  return (
    <main id="main" className="page">
      <div className="section-head" style={{ marginBottom: "1.5rem" }}>
        <p className="kicker">Archive</p>
        <h1>Analyses</h1>
        <p className="muted">
          Every analysis submitted to the platform, with its current processing
          state. <Link href="/analyses/new">Run a new analysis</Link>.
        </p>
      </div>
      <AnalysesTable />
    </main>
  );
}
