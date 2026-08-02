import type { AnalysisStatus } from "@/lib/schemas";

const LABELS: Record<AnalysisStatus, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

/**
 * Analysis status pill. Never color-only: the status name is always spelled
 * out, and running state additionally shows a spinner.
 */
export default function StatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <span className={`status-badge status-${status}`} data-status={status}>
      {status === "running" ? (
        <span className="spinner" aria-hidden="true" data-testid="spinner" />
      ) : (
        <span className="status-dot" aria-hidden="true" />
      )}
      {LABELS[status]}
    </span>
  );
}
