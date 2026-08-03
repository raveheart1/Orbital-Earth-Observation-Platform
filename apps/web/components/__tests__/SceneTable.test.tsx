import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SceneTable from "@/components/SceneTable";
import { ScenesSchema } from "@/lib/schemas";
import { sceneFixture } from "@/lib/__tests__/fixtures";

function renderScenes(raw: unknown[]) {
  return render(<SceneTable scenes={ScenesSchema.parse(raw)} />);
}

describe("SceneTable", () => {
  it("renders the valid-pixel percentage for a selected scene (not a dash)", () => {
    renderScenes([sceneFixture({ valid_pixel_pct: 95.9 })]);
    const row = screen.getByText("Selected").closest("tr")!;
    expect(within(row).getByText("95.9%")).toBeInTheDocument();
    expect(within(row).queryByText("—")).not.toBeInTheDocument();
  });

  it("renders the granule count and tile ids for mosaicked acquisitions", () => {
    renderScenes([
      sceneFixture({ granule_count: 2, tile_ids: ["T17TLG", "T17TLH"] }),
    ]);
    const row = screen.getByText("Selected").closest("tr")!;
    expect(within(row).getByText("2")).toBeInTheDocument();
    expect(within(row).getByText(/T17TLG, T17TLH/)).toBeInTheDocument();
  });

  it("does not list tile ids for single-granule acquisitions", () => {
    renderScenes([sceneFixture({ granule_count: 1, tile_ids: ["T17TLG"] })]);
    expect(screen.queryByText(/· T17TLG/)).not.toBeInTheDocument();
  });

  it("renders the AOI coverage percentage", () => {
    renderScenes([sceneFixture({ aoi_coverage_pct: 99.6 })]);
    expect(screen.getByText("99.6%")).toBeInTheDocument();
  });

  it("humanizes exclusion reasons, using the row's own AOI coverage", () => {
    renderScenes([
      sceneFixture({
        id: "scene-x",
        selection_status: "excluded",
        exclusion_reason: "insufficient_aoi_coverage",
        aoi_coverage_pct: 56.2,
        valid_pixel_pct: null,
      }),
    ]);
    const row = screen.getByText("Excluded").closest("tr")!;
    expect(row).toHaveClass("row-muted");
    expect(
      within(row).getByText(
        /Source granules covered only 56\.2% of the area of interest/,
      ),
    ).toBeInTheDocument();
  });

  it("labels dates as acquisition (sensing) dates", () => {
    renderScenes([sceneFixture()]);
    expect(
      screen.getByRole("columnheader", { name: /Acquired \(UTC\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/acquisition \(sensing\) date/i)).toBeInTheDocument();
  });
});
