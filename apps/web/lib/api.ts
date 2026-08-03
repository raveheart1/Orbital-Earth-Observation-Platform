import type { z } from "zod";
import {
  AnalysisListSchema,
  AnalysisSchema,
  ArtifactListSchema,
  HealthSchema,
  ProblemSchema,
  ProvenanceSchema,
  PublicConfigSchema,
  RegionsSchema,
  ScenesSchema,
  TimeseriesSchema,
  type Analysis,
  type CreateAnalysisRequest,
  type Problem,
  type PublicConfig,
} from "./schemas";

/**
 * All browser requests go through the same-origin proxy at /backend/*
 * (app/backend/[...path]/route.ts). The browser never talks to the API
 * origin directly, which keeps the API URL runtime-configurable and
 * avoids CORS entirely.
 */
const PROXY_BASE = "/backend";

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;

  constructor(message: string, status: number, problem: Problem | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

async function apiFetch<T>(
  path: string,
  // Input type is `unknown` so schemas with defaults/transforms (whose input
  // shape differs from their output shape) are accepted.
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${PROXY_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(
      "Could not reach the platform API. Check your connection and try again.",
      0,
    );
  }

  if (!res.ok) {
    let problem: Problem | null = null;
    const contentType = res.headers.get("content-type") ?? "";
    if (contentType.includes("json")) {
      const body: unknown = await res.json().catch(() => null);
      const parsed = ProblemSchema.safeParse(body);
      if (parsed.success) problem = parsed.data;
    }
    const message =
      problem?.detail ||
      problem?.title ||
      `The API responded with status ${res.status}.`;
    throw new ApiError(message, res.status, problem);
  }

  const body: unknown = await res.json().catch(() => {
    throw new ApiError(`The API returned a non-JSON response for ${path}.`, res.status);
  });
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(
      `The API returned an unexpected response shape for ${path}.`,
      res.status,
    );
  }
  return parsed.data;
}

export function getPublicConfig(): Promise<PublicConfig> {
  return apiFetch("/api/v1/config/public", PublicConfigSchema);
}

/**
 * The public config is immutable for the lifetime of a page session, and
 * several independent client components need it. Cache the promise so it is
 * fetched at most once per page load; a failure clears the cache so a retry
 * can succeed.
 */
let configPromise: Promise<PublicConfig> | null = null;

export function getPublicConfigCached(): Promise<PublicConfig> {
  if (!configPromise) {
    configPromise = getPublicConfig().catch((err: unknown) => {
      configPromise = null;
      throw err;
    });
  }
  return configPromise;
}

export function getRegions() {
  return apiFetch("/api/v1/regions", RegionsSchema);
}

export function getAnalyses(limit: number, offset: number) {
  return apiFetch(
    `/api/v1/analyses?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`,
    AnalysisListSchema,
  );
}

export function getAnalysis(id: string) {
  return apiFetch(`/api/v1/analyses/${encodeURIComponent(id)}`, AnalysisSchema);
}

export function getScenes(id: string) {
  return apiFetch(`/api/v1/analyses/${encodeURIComponent(id)}/scenes`, ScenesSchema);
}

export function getTimeseries(id: string) {
  return apiFetch(
    `/api/v1/analyses/${encodeURIComponent(id)}/timeseries`,
    TimeseriesSchema,
  );
}

export function getArtifacts(id: string) {
  return apiFetch(
    `/api/v1/analyses/${encodeURIComponent(id)}/artifacts`,
    ArtifactListSchema,
  );
}

export function getProvenance(id: string) {
  return apiFetch(
    `/api/v1/analyses/${encodeURIComponent(id)}/provenance`,
    ProvenanceSchema,
  );
}

export function getHealth() {
  return apiFetch("/health/ready", HealthSchema);
}

export function createAnalysis(body: CreateAnalysisRequest): Promise<Analysis> {
  return apiFetch("/api/v1/analyses", AnalysisSchema, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Human-readable label for a problem+json field location. */
export function formatProblemLoc(loc: string | (string | number)[]): string {
  if (typeof loc === "string") return loc;
  return loc.filter((part) => part !== "body").join(".");
}
