import { createElement } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FormInner } from "@/components/NewAnalysisForm";
import { createAnalysis } from "@/lib/api";
import {
  AnalysisSchema,
  PublicConfigSchema,
  RegionSchema,
  type CreateAnalysisRequest,
  type PublicConfig,
  type Region,
} from "@/lib/schemas";
import {
  analysisFixture,
  configFixture,
  regionFixture,
} from "@/lib/__tests__/fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Only the submission call is faked; ApiError and the problem formatter stay
// real so the error paths behave as they do in the browser.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  createAnalysis: vi.fn(),
}));

const createAnalysisMock = vi.mocked(createAnalysis);

beforeEach(() => {
  createAnalysisMock.mockReset();
  createAnalysisMock.mockResolvedValue(AnalysisSchema.parse(analysisFixture));
});

/** The payload the form last POSTed. */
function submittedPayload(): CreateAnalysisRequest {
  expect(createAnalysisMock).toHaveBeenCalledTimes(1);
  return createAnalysisMock.mock.calls[0]![0];
}

// MapLibre touches WebGL at import time and cannot run under jsdom.
vi.mock("@/components/MapPanel", () => ({
  default: (props: { drawEnabled?: boolean }) =>
    createElement("div", {
      "data-testid": "map",
      "data-draw-enabled": String(Boolean(props.drawEnabled)),
    }),
}));

// Deliberately listed Global-first, so the form cannot pass by accident: the
// picker must still lead with Michigan and preselect a Michigan region.
const regions: Region[] = [
  RegionSchema.parse({
    ...regionFixture,
    id: "0b1c2d3e-4f50-4a1b-8c2d-3e4f5a6b7c8d",
    name: "Nile Delta Farmland",
    slug: "nile-delta-farmland",
    description: "Irrigated cropland north of Cairo, where the Nile meets desert.",
    area_km2: 137.2,
    group: "Global",
  }),
  RegionSchema.parse(regionFixture),
];

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
      screen.getByText(/Drawn areas are limited to 250 km²/),
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

describe("NewAnalysisForm — region grouping", () => {
  it("renders one heading per group, Michigan first", () => {
    renderForm();
    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(headings).toEqual(["Michigan", "Global"]);
  });

  it("labels each group's list by its heading", () => {
    renderForm();
    const michigan = screen.getByRole("list", { name: "Michigan" });
    expect(michigan).toBeInTheDocument();
    expect(michigan).toContainElement(
      screen.getByRole("radio", { name: /Ann Arbor/ }),
    );
    expect(screen.getByRole("list", { name: "Global" })).toContainElement(
      screen.getByRole("radio", { name: /Nile Delta/ }),
    );
  });

  it("preselects the first region of the first group, not of the payload", () => {
    renderForm();
    expect(screen.getByRole("radio", { name: /Ann Arbor/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Nile Delta/ })).not.toBeChecked();
  });

  it("keeps every region in one keyboard radio group", () => {
    renderForm();
    const names = screen
      .getAllByRole("radio", { name: /Ann Arbor|Nile Delta/ })
      .map((input) => (input as HTMLInputElement).name);
    expect(names).toEqual(["region", "region"]);
  });

  it("switches selection to a region in another group", () => {
    renderForm();
    fireEvent.click(screen.getByRole("radio", { name: /Nile Delta/ }));
    expect(screen.getByRole("radio", { name: /Nile Delta/ })).toBeChecked();
    expect(areaLine()).toContain("137 km²");
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
    expect(areaLine()).toContain("250 km²");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
    expect(screen.getByTestId("map")).toHaveAttribute(
      "data-draw-enabled",
      "true",
    );
  });

  it("accepts a drawn box the size of a curated region", () => {
    renderForm();
    fireEvent.click(drawRadio());
    // ~0.1° × 0.1° at 42°N ≈ 91 km². Under the old 2 km² cap this was far too
    // big to draw; the measured-cost cap now admits it.
    setBox(["-83.6", "42.3", "-83.5", "42.4"]);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
  });

  it("rejects a drawn box over the custom cap with the server's wording", () => {
    renderForm();
    fireEvent.click(drawRadio());
    // ~0.3° × 0.2° at 42.3°N ≈ 546 km²: over the drawn-area cap, though an
    // area that size could still be curated as a predefined region.
    setBox(["-83.8", "42.2", "-83.5", "42.4"]);

    const error = screen.getByRole("alert");
    expect(error.textContent).toContain("exceeds the maximum of 250 km²");
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

// --- Observation selection --------------------------------------------------

const spreadRadio = () =>
  screen.getByRole("radio", { name: /spread across the range/i });
const seasonalRadio = () =>
  screen.getByRole("radio", { name: /same season each year/i });
const monthSelect = () => screen.getByLabelText("Target month");
const nudge = () => screen.queryByTestId("seasonal-nudge");

/** Set the observation window; dates drive both the nudge and the default month. */
function setDates(start: string, end: string) {
  fireEvent.change(screen.getByLabelText("Start date"), {
    target: { value: start },
  });
  fireEvent.change(screen.getByLabelText("End date"), {
    target: { value: end },
  });
}

describe("NewAnalysisForm — observation selection", () => {
  it("offers both strategies, defaulting to spreading across the range", () => {
    renderForm();
    expect(spreadRadio()).toBeChecked();
    expect(seasonalRadio()).not.toBeChecked();
    // The month only matters once seasonal selection is chosen.
    expect(screen.queryByLabelText("Target month")).not.toBeInTheDocument();
  });

  it("explains why seasonal selection exists without overstating it", () => {
    renderForm();
    expect(
      screen.getByText(/Scenes spaced evenly over the period/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /the seasonal swing in NDVI is far larger than any year-to-year trend/,
      ),
    ).toBeInTheDocument();
  });

  it("defaults the target month to the midpoint of the range", () => {
    renderForm();
    // 2018-04-01 → 2026-04-01 centres on April.
    setDates("2018-04-01", "2026-04-01");
    fireEvent.click(seasonalRadio());
    expect(monthSelect()).toHaveValue("4");
  });

  it("recomputes the default month when the dates move", () => {
    renderForm();
    setDates("2018-04-01", "2026-04-01");
    fireEvent.click(seasonalRadio());
    expect(monthSelect()).toHaveValue("4");

    // 2018-07-01 → 2026-07-01 centres on July.
    setDates("2018-07-01", "2026-07-01");
    expect(monthSelect()).toHaveValue("7");
  });

  it("keeps a month the visitor picked explicitly when the dates change", () => {
    renderForm();
    setDates("2018-04-01", "2026-04-01");
    fireEvent.click(seasonalRadio());
    fireEvent.change(monthSelect(), { target: { value: "9" } });

    setDates("2018-07-01", "2026-07-01");
    expect(monthSelect()).toHaveValue("9");
  });
});

describe("NewAnalysisForm — seasonal nudge", () => {
  it("stays hidden for a single-season window", () => {
    renderForm();
    setDates("2025-04-01", "2025-10-01");
    expect(nudge()).not.toBeInTheDocument();
  });

  it("advises seasonal selection over a multi-year window, without blocking", () => {
    renderForm();
    setDates("2018-01-01", "2026-01-01");

    const advice = nudge();
    expect(advice).toBeInTheDocument();
    expect(advice?.textContent).toMatch(/mostly measures which month/);
    // Advice, not an error: it must not be announced as an alert, and the form
    // stays submittable with the evenly-spread strategy.
    expect(advice).not.toHaveAttribute("role", "alert");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
  });

  it("disappears once the visitor accepts the suggestion", () => {
    renderForm();
    setDates("2018-01-01", "2026-01-01");
    fireEvent.click(
      screen.getByRole("button", { name: /use the same season each year/i }),
    );

    expect(seasonalRadio()).toBeChecked();
    expect(nudge()).not.toBeInTheDocument();
    expect(monthSelect()).toBeInTheDocument();
  });

  it("respects a deployment that raises the recommendation threshold", () => {
    renderForm({ seasonal_recommended_above_days: 4000 });
    setDates("2018-01-01", "2026-01-01");
    expect(nudge()).not.toBeInTheDocument();
  });
});

describe("NewAnalysisForm — submission payload", () => {
  it("sends the temporal strategy with no target month", async () => {
    renderForm();
    setDates("2025-04-01", "2025-10-01");
    fireEvent.click(submitButton());

    await waitFor(() => expect(createAnalysisMock).toHaveBeenCalled());
    const payload = submittedPayload();
    expect(payload.selection_strategy).toBe("temporal");
    expect(payload).not.toHaveProperty("seasonal_target_month");
  });

  it("sends the seasonal strategy with the selected target month", async () => {
    renderForm();
    setDates("2018-01-01", "2026-01-01");
    fireEvent.click(seasonalRadio());
    fireEvent.change(monthSelect(), { target: { value: "7" } });
    fireEvent.click(submitButton());

    await waitFor(() => expect(createAnalysisMock).toHaveBeenCalled());
    const payload = submittedPayload();
    expect(payload.selection_strategy).toBe("seasonal");
    expect(payload.seasonal_target_month).toBe(7);
  });

  it("sends the midpoint month when the visitor never touches the select", async () => {
    renderForm();
    setDates("2018-07-01", "2026-07-01");
    fireEvent.click(seasonalRadio());
    fireEvent.click(submitButton());

    await waitFor(() => expect(createAnalysisMock).toHaveBeenCalled());
    expect(submittedPayload().seasonal_target_month).toBe(7);
  });
});
