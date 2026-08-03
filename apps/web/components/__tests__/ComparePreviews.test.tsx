import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ComparePreviews from "@/components/ComparePreviews";
import {
  AnalysisSchema,
  ArtifactSchema,
  PublicConfigSchema,
  TimeseriesSchema,
  type Analysis,
  type Artifact,
  type ArtifactType,
} from "@/lib/schemas";
import {
  analysisFixture,
  artifactFixture,
  configFixture,
  gridFixture,
  timeseriesPointFixture,
} from "@/lib/__tests__/fixtures";

const legend = PublicConfigSchema.parse(configFixture).ndvi_legend;
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
  } = {},
) {
  return render(
    <ComparePreviews
      analysis={overrides.analysis ?? analysis}
      points={points}
      artifacts={overrides.artifacts ?? artifactsFor()}
      legend={legend}
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
});
