import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ChangePanel from "@/components/ChangePanel";
import {
  AnalysisSchema,
  ArtifactSchema,
  type Analysis,
  type Artifact,
} from "@/lib/schemas";
import { analysisFixture, artifactFixture, nbrAnalysisFixture } from "@/lib/__tests__/fixtures";

const analysis: Analysis = AnalysisSchema.parse(analysisFixture);

/** The change preview is analysis-level: attached to no scene or STAC item. */
const changePreview: Artifact = ArtifactSchema.parse(
  artifactFixture({
    id: "artifact-change-preview",
    scene_id: null,
    stac_item_id: null,
    artifact_type: "ndvi_change_preview",
    download_url: "https://example.com/signed/ndvi_change_preview.png",
  }),
);

function renderPanel(
  overrides: {
    analysis?: Analysis;
    artifacts?: Artifact[];
    fireDetectionCount?: number | null;
  } = {},
) {
  return render(
    <ChangePanel
      analysis={overrides.analysis ?? analysis}
      artifacts={overrides.artifacts ?? [changePreview]}
      areaLabel="Ann Arbor & Huron River corridor"
      fireDetectionCount={overrides.fireDetectionCount}
    />,
  );
}

describe("ChangePanel", () => {
  it("renders the change preview in a fixed-aspect viewport with its dates", () => {
    renderPanel();
    const viewport = screen.getByTestId("change-viewport");
    expect(viewport).toHaveClass("compare-viewport--fixed");
    expect(viewport.getAttribute("style")).toContain("1272 / 1149");
    expect(
      screen.getByAltText(
        /NDVI change map of Ann Arbor & Huron River corridor between 2023-05-04 and 2023-09-26/,
      ),
    ).toBeInTheDocument();
  });

  it("states the change statistics in plain language", () => {
    renderPanel();
    const stats = screen.getByTestId("change-stats");
    expect(stats).toHaveTextContent(
      "Between 2023-05-04 and 2023-09-26: mean ΔNDVI −0.081",
    );
    expect(stats).toHaveTextContent(
      "8.6% of observed area greener (Δ > +0.10)",
    );
    expect(stats).toHaveTextContent("22.3% browner (Δ < −0.10)");
    expect(stats).toHaveTextContent(
      "87.4% of the AOI observed cloud-free on both dates",
    );
  });

  it("renders a diverging legend labeled −range to +range centered at zero", () => {
    renderPanel();
    expect(
      screen.getByRole("img", {
        name: "NDVI change color scale, fixed symmetric range from −0.4 to +0.4 centered at zero",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("−0.4")).toBeInTheDocument();
    expect(screen.getByText("0.0")).toBeInTheDocument();
    expect(screen.getByText("+0.4")).toBeInTheDocument();
    expect(
      screen.getByText(/No valid observation on one or both dates/),
    ).toBeInTheDocument();
  });

  it("carries the worker note and the screening-not-diagnosis caveat", () => {
    renderPanel();
    const note = screen.getByText(/screening instrument/);
    expect(note).toHaveTextContent(/does not by itself establish causes/);
    expect(note).toHaveTextContent(/residual cloud and shadow/);
  });

  it("never shows the FIRMS context line for NDVI, even with a count", () => {
    renderPanel({ fireDetectionCount: 7 });
    expect(screen.queryByTestId("fire-context")).not.toBeInTheDocument();
  });

  it("draws the AOI boundary by default and hides it when toggled off", () => {
    renderPanel();
    const toggle = screen.getByRole("checkbox", { name: /Show AOI boundary/ });
    expect(toggle).toBeChecked();
    expect(screen.getByTestId("aoi-overlay")).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.queryByTestId("aoi-overlay")).not.toBeInTheDocument();
  });

  it("shows a placeholder when the change preview artifact is missing", () => {
    renderPanel({ artifacts: [] });
    expect(screen.getByText("Preview not available")).toBeInTheDocument();
    expect(screen.getByTestId("change-stats")).toBeInTheDocument();
  });

  it("renders nothing for an analysis without a change block or preview", () => {
    const legacySummary = { ...analysisFixture.summary } as Record<
      string,
      unknown
    >;
    delete legacySummary.change;
    const legacy = AnalysisSchema.parse({
      ...analysisFixture,
      summary: legacySummary,
    });
    const { container } = renderPanel({ analysis: legacy, artifacts: [] });
    expect(container).toBeEmptyDOMElement();
  });

  describe("NBR analyses", () => {
    const nbrAnalysis: Analysis = AnalysisSchema.parse(nbrAnalysisFixture);
    const nbrChangePreview: Artifact = ArtifactSchema.parse(
      artifactFixture({
        id: "artifact-nbr-change-preview",
        scene_id: null,
        stac_item_id: null,
        artifact_type: "nbr_change_preview",
        download_url: "https://example.com/signed/nbr_change_preview.png",
      }),
    );

    it("renders the NBR change preview with burn-severity wording", () => {
      renderPanel({
        analysis: nbrAnalysis,
        artifacts: [nbrChangePreview],
      });
      expect(
        screen.getByAltText(
          /Per-pixel NBR change map of Ann Arbor & Huron River corridor between 2023-05-04 and 2023-09-26/,
        ),
      ).toBeInTheDocument();
      expect(screen.getByText(/^ΔNBR —/)).toBeInTheDocument();
      const stats = screen.getByTestId("change-stats");
      expect(stats).toHaveTextContent("mean ΔNBR −0.081");
      // ΔNBR sign convention: up = recovery, down = burn severity increase.
      expect(stats).toHaveTextContent(
        "8.6% of observed area recovered (Δ > +0.10)",
      );
      expect(stats).toHaveTextContent("22.3% burn severity increase (Δ < −0.10)");
    });

    it("labels the legend for NBR over its own display range", () => {
      renderPanel({
        analysis: nbrAnalysis,
        artifacts: [nbrChangePreview],
      });
      expect(
        screen.getByRole("img", {
          name: "NBR change color scale, fixed symmetric range from −0.6 to +0.6 centered at zero",
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/negative indicates burn severity increase/),
      ).toBeInTheDocument();
    });

    it("ignores the NDVI change preview of a different operation", () => {
      renderPanel({ analysis: nbrAnalysis, artifacts: [changePreview] });
      expect(screen.getByText("Preview not available")).toBeInTheDocument();
      expect(
        screen.queryByAltText(/Per-pixel NDVI change map/),
      ).not.toBeInTheDocument();
    });

    it("shows the FIRMS context line when detections are archived", () => {
      renderPanel({
        analysis: nbrAnalysis,
        artifacts: [nbrChangePreview],
        fireDetectionCount: 7,
      });
      expect(screen.getByTestId("fire-context")).toHaveTextContent(
        "7 FIRMS active-fire detections within this analysis's area and " +
          "date window (context, not perimeters).",
      );
    });

    it("omits the FIRMS context line when no detections were archived", () => {
      renderPanel({ analysis: nbrAnalysis, artifacts: [nbrChangePreview] });
      expect(screen.queryByTestId("fire-context")).not.toBeInTheDocument();
    });
  });
});
