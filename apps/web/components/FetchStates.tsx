"use client";

/** Shared loading / error / empty building blocks for data sections. */

export function LoadingBox({ label }: { label: string }) {
  return (
    <div aria-busy="true" role="status" className="stack-s">
      <p className="small muted">{label}</p>
      <div className="skeleton" style={{ height: "1.25rem", width: "60%" }} />
      <div className="skeleton" style={{ height: "1.25rem", width: "85%" }} />
      <div className="skeleton" style={{ height: "1.25rem", width: "70%" }} />
    </div>
  );
}

export function ErrorBox({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="alert alert-error" role="alert">
      <p>{message}</p>
      {onRetry ? (
        <p style={{ marginTop: "0.6rem" }}>
          <button type="button" className="btn btn-small" onClick={onRetry}>
            Try again
          </button>
        </p>
      ) : null}
    </div>
  );
}

export function EmptyBox({ children }: { children: React.ReactNode }) {
  return <div className="panel-note">{children}</div>;
}
