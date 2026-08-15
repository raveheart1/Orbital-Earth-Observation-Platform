import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ArtifactList from "@/components/ArtifactList";
import { ArtifactSchema } from "@/lib/schemas";
import { artifactFixture } from "@/lib/__tests__/fixtures";

describe("ArtifactList", () => {
  it("labels the fire-detections artifact and groups it with analysis products", () => {
    const fires = ArtifactSchema.parse(
      artifactFixture({
        id: "artifact-fires",
        scene_id: null,
        stac_item_id: null,
        artifact_type: "fire_detections",
        content_type: "application/geo+json",
      }),
    );
    render(<ArtifactList artifacts={[fires]} />);
    expect(
      screen.getByText("Active-fire detections (FIRMS, GeoJSON)"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Analysis-level products/ }),
    ).toBeInTheDocument();
  });

  it("keeps the existing type labels unchanged", () => {
    render(
      <ArtifactList
        artifacts={[ArtifactSchema.parse(artifactFixture())]}
      />,
    );
    expect(screen.getByText("NDVI preview (PNG)")).toBeInTheDocument();
  });
});
