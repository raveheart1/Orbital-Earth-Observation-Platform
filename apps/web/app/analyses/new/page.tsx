import type { Metadata } from "next";
import NewAnalysisForm from "@/components/NewAnalysisForm";

export const metadata: Metadata = {
  title: "New analysis",
  description:
    "Submit a new NDVI analysis over a predefined region or a custom bounding box.",
};

export default function NewAnalysisPage() {
  return (
    <main id="main" className="page">
      <div className="section-head" style={{ marginBottom: "1.5rem" }}>
        <p className="kicker">Submission</p>
        <h1>New analysis</h1>
        <p className="muted" style={{ maxWidth: "46rem" }}>
          Choose an area of interest and an observation window. The platform
          finds matching Sentinel-2 scenes on the Microsoft Planetary Computer,
          masks clouds, computes NDVI statistics per scene, and records full
          provenance.
        </p>
      </div>
      <NewAnalysisForm />
    </main>
  );
}
