"use client";

import { getHealth, getPublicConfigCached } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";

function checkLabel(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "ok" : "failing";
  return "unknown";
}

/**
 * Live system-status strip: API readiness (database, queue) plus the public
 * configuration that shapes what the platform will accept.
 */
export default function SystemStatus() {
  const health = useFetch(() => getHealth(), []);
  const config = useFetch(() => getPublicConfigCached(), []);

  return (
    <div className="status-strip" aria-live="polite">
      <span className="item">
        <span className="label">API</span>
        {health.state.status === "ok" ? (
          <span
            className={
              health.state.data.status === "ok" ? "health-ok" : "health-degraded"
            }
          >
            {health.state.data.status === "ok" ? "Ready" : "Degraded"}
          </span>
        ) : health.state.status === "error" ? (
          <span className="health-degraded">Unreachable</span>
        ) : (
          <span className="muted">Checking…</span>
        )}
      </span>
      {health.state.status === "ok"
        ? Object.entries(health.state.data.checks).map(([name, value]) => (
            <span className="item" key={name}>
              <span className="label">{name}</span>
              <span className="mono">{checkLabel(value)}</span>
            </span>
          ))
        : null}
      {config.state.status === "ok" ? (
        <>
          <span className="item">
            <span className="label">Environment</span>
            <span className="mono">{config.state.data.environment}</span>
          </span>
          <span className="item">
            <span className="label">Submissions</span>
            <span
              className={
                config.state.data.submissions_enabled
                  ? "health-ok"
                  : "health-degraded"
              }
            >
              {config.state.data.submissions_enabled ? "Enabled" : "Disabled"}
            </span>
          </span>
          <span className="item">
            <span className="label">Processing</span>
            <span className="mono">{config.state.data.processing_version}</span>
          </span>
        </>
      ) : null}
    </div>
  );
}
