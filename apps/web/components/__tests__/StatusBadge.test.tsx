import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatusBadge from "@/components/StatusBadge";
import type { AnalysisStatus } from "@/lib/schemas";

describe("StatusBadge", () => {
  const cases: [AnalysisStatus, string][] = [
    ["queued", "Queued"],
    ["running", "Running"],
    ["succeeded", "Succeeded"],
    ["failed", "Failed"],
    ["cancelled", "Cancelled"],
  ];

  it.each(cases)(
    "renders the %s status as visible text (never color-only)",
    (status, label) => {
      render(<StatusBadge status={status} />);
      const badge = screen.getByText(label);
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass(`status-${status}`);
    },
  );

  it("shows a spinner only while running", () => {
    const { rerender } = render(<StatusBadge status="running" />);
    expect(screen.getByTestId("spinner")).toBeInTheDocument();
    rerender(<StatusBadge status="succeeded" />);
    expect(screen.queryByTestId("spinner")).not.toBeInTheDocument();
  });

  it("marks decorative indicators as hidden from assistive tech", () => {
    render(<StatusBadge status="running" />);
    expect(screen.getByTestId("spinner")).toHaveAttribute("aria-hidden", "true");
  });
});
