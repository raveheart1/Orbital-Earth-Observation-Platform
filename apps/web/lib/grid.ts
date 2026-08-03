import type { Artifact } from "./schemas";

/**
 * Guard against comparing imagery rendered on different analytical grids.
 *
 * Every artifact produced by processing v2.0.0+ carries the signature of the
 * canonical grid it was rasterized on. If the artifacts shown side by side
 * (or the analysis itself) disagree on that signature, the images cover
 * different ground and any visual comparison is scientifically invalid —
 * the UI must warn loudly instead of letting the mismatch pass silently.
 */
export interface GridMismatchResult {
  /** True when two or more distinct grid signatures were observed. */
  mismatch: boolean;
  /** Distinct signatures observed, in first-seen order. */
  signatures: string[];
}

export function detectGridMismatch(
  artifacts: ReadonlyArray<Pick<Artifact, "grid_signature"> | null | undefined>,
  analysisSignature?: string | null,
): GridMismatchResult {
  const signatures: string[] = [];
  const record = (signature: string | null | undefined) => {
    // Null signatures (legacy artifacts) carry no grid identity to compare;
    // the legacy informational note covers that case instead.
    if (typeof signature !== "string" || signature.length === 0) return;
    if (!signatures.includes(signature)) signatures.push(signature);
  };
  record(analysisSignature);
  for (const artifact of artifacts) record(artifact?.grid_signature);
  return { mismatch: signatures.length > 1, signatures };
}
