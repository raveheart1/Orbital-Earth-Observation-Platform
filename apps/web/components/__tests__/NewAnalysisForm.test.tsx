import { createElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FormInner } from "@/components/NewAnalysisForm";
import {
  PublicConfigSchema,
  RegionSchema,
  type PublicConfig,
  type Region,
} from "@/lib/schemas";
import { configFixture, regionFixture } from "@/lib/__tests__/fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// MapLibre touches WebGL at import time and cannot run under jsdom.
vi.mock("@/components/MapPanel", () => ({
  default: (props: { drawEnabled?: boolean }) =>
    createElement("div", {
      "data-testid": "map",
      "data-draw-enabled": String(Boolean(props.drawEnabled)),
    }),
}));

const regions: Region[] = [RegionSchema.parse(regionFixture)];

function configWith(overrides: Record<string, unknown> = {}): PublicConfig {
  return PublicConfigSchema.parse({ ...configFixture, ...overrides });
}

function renderForm(overrides: Record<string, unknown> = {}) {
  return render(
    createElement(FormInner, { config: configWith(overrides), regions }),
  );
}

const drawRadio = () =>
  screen.getByRole("radio", { name: /draw a custom area/i });
const areaLine = () => screen.getByText(/Estimated area:/).textContent ?? "";
const submitButton = () =>
  screen.getByRole("button", { name: /submit analysis/i });

function setBox(box: [string, string, string, string]) {
  const labels = ["Min longitude", "Min latitude", "Max longitude", "Max latitude"];
  labels.forEach((label, i) => {
    fireEvent.change(screen.getByLabelText(label), { target: { value: box[i] } });
  });
}

describe("NewAnalysisForm — custom area gating", () => {
  // Regression: drawing used to be disabled whenever demo_mode was set. It is
  // now gated on custom_areas_enabled alone.
  it("allows drawing in demo mode when custom areas are enabled", () => {
    renderForm({ demo_mode: true, custom_areas_enabled: true });
    expect(drawRadio()).toBeEnabled();
    expect(
      screen.getByText(/Drawn areas are limited to 2 km²/),
    ).toBeInTheDocument();
  });

  it("disables drawing when the deployment turns custom areas off", () => {
    renderForm({ demo_mode: false, custom_areas_enabled: false });
    expect(drawRadio()).toBeDisabled();
    const note = screen.getByText(/Custom areas are disabled/);
    expect(note).toBeInTheDocument();
    expect(note.textContent).not.toMatch(/demo/i);
  });
});

describe("NewAnalysisForm — area limits by mode", () => {
  it("shows the predefined-region limit while a region is selected", () => {
    renderForm();
    expect(areaLine()).toContain("for predefined regions");
    expect(areaLine()).toContain("600 km²");
    // A curated 481 km² region stays submittable under its own, larger cap.
    expect(submitButton()).toBeEnabled();
  });

  it("prefills a compliant ~1 km² box and switches to the drawn-area limit", () => {
    renderForm();
    fireEvent.click(drawRadio());

    expect(screen.getByLabelText("Min longitude")).toHaveValue(-83.50608);
    expect(screen.getByLabelText("Max latitude")).toHaveValue(42.35452);
    // Two decimals: whole-number rounding would be useless at this scale.
    expect(areaLine()).toContain("1.00 km²");
    expect(areaLine()).toContain("for drawn areas");
    expect(areaLine()).toContain("2 km²");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
    expect(screen.getByTestId("map")).toHaveAttribute(
      "data-draw-enabled",
      "true",
    );
  });

  it("rejects a drawn box over the custom cap with the server's wording", () => {
    renderForm();
    fireEvent.click(drawRadio());
    // ~0.1° × 0.1° at 42°N ≈ 91 km²: legal for a region, far too big to draw.
    setBox(["-83.6", "42.3", "-83.5", "42.4"]);

    const error = screen.getByRole("alert");
    expect(error.textContent).toContain("exceeds the maximum of 2 km²");
    expect(error.textContent).toContain("Draw a smaller box");
    expect(error.textContent).toContain("predefined region");
    expect(submitButton()).toBeDisabled();
  });

  it("rejects a drawn box under the shared minimum", () => {
    renderForm();
    fireEvent.click(drawRadio());
    setBox(["-83.5", "42.35", "-83.499", "42.351"]);

    expect(screen.getByRole("alert").textContent).toContain("0.5 km² minimum");
    expect(submitButton()).toBeDisabled();
  });

  it("keeps a box the visitor already entered when toggling modes", () => {
    renderForm();
    fireEvent.click(drawRadio());
    setBox(["-83.51", "42.34", "-83.5", "42.35"]);
    fireEvent.click(screen.getByRole("radio", { name: /predefined region/i }));
    fireEvent.click(drawRadio());

    expect(screen.getByLabelText("Min longitude")).toHaveValue(-83.51);
  });
});
