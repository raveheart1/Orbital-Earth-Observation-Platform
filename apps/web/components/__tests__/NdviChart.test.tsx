import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NdviChart from "@/components/NdviChart";
import { TimeseriesSchema } from "@/lib/schemas";
import { timeseriesFixture } from "@/lib/__tests__/fixtures";

const points = TimeseriesSchema.parse(timeseriesFixture).points;

describe("NdviChart", () => {
  it("labels the series for NDVI by default", () => {
    render(<NdviChart points={points} />);
    expect(screen.getByText("Mean NDVI per scene")).toBeInTheDocument();
    expect(
      screen.getByText(/NDVI statistics per usable scene/),
    ).toBeInTheDocument();
  });

  it("labels the series for the analysis operation", () => {
    render(<NdviChart points={points} operation="nbr" />);
    expect(screen.getByText("Mean NBR per scene")).toBeInTheDocument();
    expect(
      screen.getByText(/NBR statistics per usable scene/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Mean NDVI/)).not.toBeInTheDocument();
  });
});
