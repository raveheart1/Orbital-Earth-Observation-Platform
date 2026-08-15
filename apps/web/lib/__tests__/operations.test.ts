import { describe, expect, it } from "vitest";
import { legendForOperation, operationUi } from "@/lib/operations";
import { PublicConfigSchema } from "@/lib/schemas";
import { configFixture } from "./fixtures";

const config = PublicConfigSchema.parse(configFixture);

describe("operationUi", () => {
  it("carries the NDVI wording the components had before operations existed", () => {
    // Byte-exact: NDVI analyses must render identically to before.
    const op = operationUi("ndvi");
    expect(op.name).toBe("NDVI");
    expect(op.previewArtifactType).toBe("ndvi_preview");
    expect(op.changePreviewArtifactType).toBe("ndvi_change_preview");
    expect(op.previewAltHint).toBe(
      "greener shades indicate denser, healthier vegetation",
    );
    expect(op.changeAltHint).toBe(
      "brown shades lost vegetation greenness, blue-green shades gained",
    );
    expect(op.changeIncreaseLabel).toBe("greener");
    expect(op.changeDecreaseLabel).toBe("browner");
    expect(op.changeSectionBlurb).toBe(
      "Per-pixel difference between the earliest and latest usable " +
        "observations; blue-green means greener, brown means browner.",
    );
    expect(op.changeLegendNote).toBe(
      "Delta is the later minus the earlier NDVI; positive is greening. The " +
        "analytical COG retains full delta values beyond the display range.",
    );
  });

  it("describes NBR in burn-severity terms", () => {
    const op = operationUi("nbr");
    expect(op.name).toBe("NBR");
    expect(op.title).toBe("NBR — burn severity");
    expect(op.previewArtifactType).toBe("nbr_preview");
    expect(op.changePreviewArtifactType).toBe("nbr_change_preview");
    expect(op.changeIncreaseLabel).toBe("recovered");
    expect(op.changeDecreaseLabel).toBe("burn severity increase");
    expect(op.changeLegendNote).toContain("burn severity increase");
    expect(op.description).toContain("does not by itself confirm fire");
  });

  it("falls back to NDVI wording when the operation is missing", () => {
    expect(operationUi(null)).toEqual(operationUi("ndvi"));
    expect(operationUi(undefined)).toEqual(operationUi("ndvi"));
  });

  it("still renders an unknown future operation under its own name", () => {
    const op = operationUi("ndwi");
    expect(op.name).toBe("NDWI");
    expect(op.previewArtifactType).toBe("ndvi_preview");
    expect(op.changePreviewArtifactType).toBe("ndvi_change_preview");
  });
});

describe("legendForOperation", () => {
  it("picks each operation's own preview legend from the config", () => {
    const ndvi = legendForOperation(config, "ndvi");
    expect(ndvi.type).toBe("ndvi");
    expect(ndvi.display_min).toBe(-0.2);

    const nbr = legendForOperation(config, "nbr");
    expect(nbr.type).toBe("nbr");
    expect(nbr.display_min).toBe(-1);
    expect(nbr.display_max).toBe(1);
    expect(nbr.stops[0]?.color).toBe("#45260a");
  });

  it("falls back to the top-level ndvi_legend for an unknown operation", () => {
    expect(legendForOperation(config, "ndwi")).toEqual(config.ndvi_legend);
  });

  it("falls back when the server omits the per-operation legend", () => {
    const withoutLegends = PublicConfigSchema.parse({
      ...configFixture,
      operations: configFixture.operations.map(({ legend, ...entry }) => {
        void legend;
        return entry;
      }),
    });
    expect(legendForOperation(withoutLegends, "nbr")).toEqual(
      withoutLegends.ndvi_legend,
    );
  });
});
