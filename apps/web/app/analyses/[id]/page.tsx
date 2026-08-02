import type { Metadata } from "next";
import AnalysisDetail from "@/components/AnalysisDetail";

export const metadata: Metadata = {
  title: "Analysis detail",
  description:
    "Status, NDVI time series, imagery, artifacts, and provenance for a single analysis.",
};

export default async function AnalysisDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <main id="main" className="page">
      <AnalysisDetail id={id} />
    </main>
  );
}
