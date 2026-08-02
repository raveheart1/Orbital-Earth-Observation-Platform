"use client";

import Link from "next/link";
import { getPublicConfigCached } from "@/lib/api";
import { useFetch } from "@/lib/useFetch";

/**
 * Hero call-to-action buttons. The demonstration link targets the configured
 * demo analysis when one exists, otherwise the analyses index.
 */
export default function HeroActions() {
  const { state } = useFetch(() => getPublicConfigCached(), []);
  const demoId = state.status === "ok" ? state.data.demo_analysis_id : null;
  const demoHref = demoId ? `/analyses/${demoId}` : "/analyses";

  return (
    <p className="actions">
      <Link className="btn btn-primary" href={demoHref}>
        Explore the demonstration analysis
      </Link>
      <Link className="btn" href="/analyses/new">
        Run a new analysis
      </Link>
    </p>
  );
}
