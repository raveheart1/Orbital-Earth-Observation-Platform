import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ComparePreviews from "@/components/ComparePreviews";
import { legendForOperation } from "@/lib/operations";
import {
  AnalysisSchema,
  ArtifactSchema,
  PublicConfigSchema,
  TimeseriesSchema,
  type Analysis,
  type Artifact,
  type ArtifactType,
  type NdviLegend,
} from "@/lib/schemas";
import {
  analysisFixture,
  artifactFixture,
  configFixture,
  gridFixture,
  nbrAnalysisFixture,
  timeseriesPointFixture,
} from "@/lib/__tests__/fixtures";

const config = PublicConfigSchema.parse(configFixture);
const legend = config.ndvi_legend;
const analysis: Analysis = AnalysisSchema.parse(analysisFixture);

const OTHER_SIGNATURE = "EPSG:32617:1272x627:10,0,322730,0,-10,4691250";

const points = TimeseriesSchema.parse({
  analysis_id: analysis.id,
  points: [
    timeseriesPointFixture({
      scene_id: "scene-1",
      stac_item_id: "ITEM-A",
      observed_at: "2023-05-04T16:32:11Z",
    }),
    timeseriesPointFixture({
      scene_id: "scene-3",
      stac_item_id: "ITEM-B",
      observed_at: "2023-09-26T16:33:49Z",
      aoi_coverage_pct: 99.4,
      valid_pixel_pct: 89.7,
    }),
  ],
}).points;

function artifactsFor(signatures: Partial<Record<string, string>> = {}): Artifact[] {
  const types: ArtifactType[] = ["true_color_preview", "ndvi_preview"];
  const items = ["ITEM-A", "ITEM-B"];
  return items.flatMap((itemId) =>
    types.map((type) =>
      ArtifactSchema.parse(
        artifactFixture({
          id: `${itemId}-${type}`,
          stac_item_id: itemId,
          artifact_type: type,
          grid_signature:
            signatures[`${itemId}:${type}`] ?? gridFixture.signature,
        }),
      ),
    ),
  );
}

function renderCompare(
  overrides: {
    analysis?: Analysis;
    artifacts?: Artifact[];
    legend?: NdviLegend;
  } = {},
) {
  return render(
    <ComparePreviews
      analysis={overrides.analysis ?? analysis}
      points={points}
      artifacts={overrides.artifacts ?? artifactsFor()}
      legend={overrides.legend ?? legend}
      areaLabel="Detroit Urban Core"
    />,
  );
}

describe("ComparePreviews", () => {
  it("renders all four previews in identically sized fixed-aspect viewports", () => {
    renderCompare();
    const viewports = screen.getAllByTestId("compare-viewport");
    expect(viewports).toHaveLength(4);
    for (const viewport of viewports) {
      expect(viewport).toHaveClass("compare-viewport--fixed");
    }
    // Every viewport carries the exact same inline style (the grid's
    // width/height aspect ratio), so all four boxes are equally sized.
    const styleAttrs = new Set(
      viewports.map((v) => v.getAttribute("style") ?? ""),
    );
    expect(styleAttrs.size).toBe(1);
    expect([...styleAttrs][0]).toContain("1272 / 1149");
  });

  it("shows acquisition date, AOI coverage, valid pixels, and granules per image", () => {
    renderCompare();
    expect(screen.getAllByText(/sensing date/)).toHaveLength(4);
    expect(screen.getAllByText("2023-05-04")).toHaveLength(2);
    expect(screen.getAllByText("2023-09-26")).toHaveLength(2);
    expect(screen.getAllByText("99.4%")).toHaveLength(2);
    expect(screen.getAllByText("2 granules · T17TLG, T17TLH")).toHaveLength(4);
  });

  it("warns prominently when artifacts were produced on different grids", () => {
    renderCompare({
      artifacts: artifactsFor({ "ITEM-B:ndvi_preview": OTHER_SIGNATURE }),
    });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/NOT directly comparable/);
    expect(alert).toHaveTextContent(gridFixture.signature);
    expect(alert).toHaveTextContent(OTHER_SIGNATURE);
  });

  it("shows no grid warning when every artifact matches the analysis grid", () => {
    renderCompare();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an informational (not alarming) note for legacy analyses without a grid", () => {
    renderCompare({ analysis: { ...analysis, grid: null } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByText(/predates the canonical-grid guarantee/),
    ).toBeInTheDocument();
    for (const viewport of screen.getAllByTestId("compare-viewport")) {
      expect(viewport).not.toHaveClass("compare-viewport--fixed");
    }
  });

  it("draws the AOI boundary by default and hides it when toggled off", () => {
    renderCompare();
    const toggle = screen.getByRole("checkbox", {
      name: /Show AOI boundary/,
    });
    expect(toggle).toBeChecked();
    expect(screen.getAllByTestId("aoi-overlay")).toHaveLength(4);
    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(screen.queryAllByTestId("aoi-overlay")).toHaveLength(0);
  });

  it("swaps the grid for a single swipe viewport with both date labels in slider mode", () => {
    renderCompare();
    fireEvent.click(screen.getByRole("radio", { name: "Slider" }));
    const viewport = screen.getByTestId("swipe-viewport");
    expect(screen.queryAllByTestId("compare-viewport")).toHaveLength(0);
    // Same fixed aspect ratio as the side-by-side cells, from the grid.
    expect(viewport.getAttribute("style")).toContain("1272 / 1149");
    expect(viewport).toHaveTextContent("2023-05-04");
    expect(viewport).toHaveTextContent("2023-09-26");
    expect(screen.getByRole("slider")).toHaveValue("50");
  });

  it("defaults the slider to NDVI previews and switches to true color on demand", () => {
    renderCompare();
    fireEvent.click(screen.getByRole("radio", { name: "Slider" }));
    expect(screen.getAllByAltText(/^NDVI map/)).toHaveLength(2);
    expect(screen.queryAllByAltText(/^True-color/)).toHaveLength(0);
    fireEvent.click(screen.getByRole("radio", { name: "True color" }));
    expect(screen.getAllByAltText(/^True-color/)).toHaveLength(2);
    expect(screen.queryAllByAltText(/^NDVI map/)).toHaveLength(0);
  });

  it("clips the earliest layer at the divider and clamps the position to 0–100", () => {
    renderCompare();
    fireEvent.click(screen.getByRole("radio", { name: "Slider" }));
    const divider = screen.getByRole("slider");
    const before = screen.getByAltText(/^NDVI map .* acquired 2023-05-04/);

    fireEvent.change(divider, { target: { value: "80" } });
    expect(divider).toHaveValue("80");
    expect(before.getAttribute("style")).toContain("inset(0 20% 0 0)");

    fireEvent.change(divider, { target: { value: "150" } });
    expect(divider).toHaveValue("100");
    expect(before.getAttribute("style")).toContain("inset(0 0% 0 0)");

    fireEvent.change(divider, { target: { value: "-20" } });
    expect(divider).toHaveValue("0");
    expect(before.getAttribute("style")).toContain("inset(0 100% 0 0)");
  });

  it("disables slider mode when grid signatures mismatch, alongside the warning", () => {
    renderCompare({
      artifacts: artifactsFor({ "ITEM-B:ndvi_preview": OTHER_SIGNATURE }),
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Slider" })).toBeDisabled();
    expect(screen.getAllByTestId("compare-viewport")).toHaveLength(4);
  });

  it("does not offer slider mode for legacy grid-null analyses", () => {
    renderCompare({ analysis: { ...analysis, grid: null } });
    expect(screen.queryByRole("radio", { name: "Slider" })).not.toBeInTheDocument();
    expect(screen.getAllByTestId("compare-viewport")).toHaveLength(4);
  });

  it("renders the NDVI legend wording from the legacy top-level legend", () => {
    renderCompare();
    expect(
      screen.getByText(/NDVI color scale — fixed display range −0\.2 to 0\.9/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not low NDVI/)).toBeInTheDocument();
  });

  describe("NBR analyses", () => {
    const nbrAnalysis: Analysis = AnalysisSchema.parse(nbrAnalysisFixture);

    function nbrArtifacts(): Artifact[] {
      const types: ArtifactType[] = ["true_color_preview", "nbr_preview"];
      return ["ITEM-A", "ITEM-B"].flatMap((itemId) =>
        types.map((type) =>
          ArtifactSchema.parse(
            artifactFixture({
              id: `${itemId}-${type}`,
              stac_item_id: itemId,
              artifact_type: type,
            }),
          ),
        ),
      );
    }

    it("labels the index previews and alt text for NBR", () => {
      renderCompare({ analysis: nbrAnalysis, artifacts: nbrArtifacts() });
      expect(screen.getAllByAltText(/^NBR map/)).toHaveLength(2);
      expect(
        screen.getAllByAltText(/dark brown shades indicate low NBR/),
      ).toHaveLength(2);
      expect(screen.getByText("NBR — earliest")).toBeInTheDocument();
      expect(screen.getByText("NBR — latest")).toBeInTheDocument();
      expect(screen.queryAllByAltText(/^NDVI map/)).toHaveLength(0);
    });

    it("defaults the slider to the NBR previews", () => {
      renderCompare({ analysis: nbrAnalysis, artifacts: nbrArtifacts() });
      fireEvent.click(screen.getByRole("radio", { name: "Slider" }));
      expect(screen.getByRole("radio", { name: "NBR" })).toBeChecked();
      expect(screen.getAllByAltText(/^NBR map/)).toHaveLength(2);
    });

    it("renders the NBR legend — not the NDVI one — from the config", () => {
      renderCompare({
        analysis: nbrAnalysis,
        artifacts: nbrArtifacts(),
        legend: legendForOperation(config, "nbr"),
      });
      expect(
        screen.getByText(/NBR color scale — fixed display range −1\.0 to 1\.0/),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("img", { name: /NBR color scale, fixed range/ }),
      ).toBeInTheDocument();
      expect(screen.getByText(/not low NBR/)).toBeInTheDocument();
      expect(screen.queryByText(/NDVI color scale/)).not.toBeInTheDocument();
      // The gradient uses the NBR ramp (deep green high end), not NDVI's.
      const gradient = screen.getByRole("img", {
        name: /NBR color scale/,
      });
      expect(gradient.getAttribute("style")).toContain("#0e6028");
    });
  });
});
