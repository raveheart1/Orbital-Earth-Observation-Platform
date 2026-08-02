import { z } from "zod";

/**
 * Zod schemas mirroring the platform API contract (base path /api/v1).
 * Every response is validated at the fetch boundary in lib/api.ts.
 */

export const BboxSchema = z.tuple([z.number(), z.number(), z.number(), z.number()]);
export type Bbox = z.infer<typeof BboxSchema>;

/** GeoJSON geometry — kept permissive; only rendered, never traversed deeply. */
const GeoJsonSchema = z.record(z.string(), z.unknown());

export const LegendStopSchema = z.object({
  value: z.number(),
  color: z.string(),
});

export const NdviLegendSchema = z.object({
  type: z.literal("ndvi"),
  display_min: z.number(),
  display_max: z.number(),
  stops: z.array(LegendStopSchema).min(1),
  masked_color: z.string(),
  note: z.string(),
});
export type NdviLegend = z.infer<typeof NdviLegendSchema>;

export const PublicConfigSchema = z.object({
  environment: z.string(),
  demo_mode: z.boolean(),
  submissions_enabled: z.boolean(),
  max_aoi_area_km2: z.number(),
  min_aoi_area_km2: z.number(),
  max_date_span_days: z.number(),
  min_start_date: z.string(),
  max_scene_limit: z.number(),
  default_scene_limit: z.number(),
  max_cloud_cover_pct: z.number(),
  default_cloud_cover_pct: z.number(),
  map_default_center: z.tuple([z.number(), z.number()]),
  map_default_zoom: z.number(),
  ndvi_legend: NdviLegendSchema,
  demo_analysis_id: z.string().nullable(),
  processing_version: z.string(),
});
export type PublicConfig = z.infer<typeof PublicConfigSchema>;

export const RegionSchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  description: z.string(),
  bbox: BboxSchema,
  geometry: GeoJsonSchema.nullable().optional(),
  area_km2: z.number(),
  is_predefined: z.boolean(),
});
export type Region = z.infer<typeof RegionSchema>;

export const RegionsSchema = z.array(RegionSchema);

export const AnalysisStatusSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
]);
export type AnalysisStatus = z.infer<typeof AnalysisStatusSchema>;

export const AnalysisSummarySchema = z.object({
  usable_scene_count: z.number(),
  unusable_scene_count: z.number(),
  first_observation: z.string().nullable(),
  last_observation: z.string().nullable(),
  ndvi_mean_first: z.number().nullable(),
  ndvi_mean_last: z.number().nullable(),
  ndvi_mean_change: z.number().nullable(),
  mean_valid_pixel_pct: z.number().nullable(),
  interpretation_note: z.string().optional(),
});
export type AnalysisSummary = z.infer<typeof AnalysisSummarySchema>;

export const AnalysisSchema = z.object({
  id: z.string(),
  status: AnalysisStatusSchema,
  status_message: z.string().nullable(),
  region: RegionSchema.nullable(),
  bbox: BboxSchema,
  geometry: GeoJsonSchema.nullable(),
  area_km2: z.number(),
  start_date: z.string(),
  end_date: z.string(),
  collection: z.string(),
  max_cloud_cover_pct: z.number(),
  scene_limit: z.number(),
  processing: z.object({
    operation: z.string(),
    version: z.string(),
    git_commit_sha: z.string().nullable(),
  }),
  submitted_at: z.string(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  failure: z
    .object({
      category: z.string(),
      detail: z.string().nullable(),
    })
    .nullable(),
  retry_count: z.number(),
  summary: AnalysisSummarySchema.nullable(),
  is_demo: z.boolean(),
  links: z.object({
    self: z.string(),
    scenes: z.string(),
    timeseries: z.string(),
    artifacts: z.string(),
    provenance: z.string(),
  }),
});
export type Analysis = z.infer<typeof AnalysisSchema>;

export const AnalysisListSchema = z.object({
  items: z.array(AnalysisSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});
export type AnalysisList = z.infer<typeof AnalysisListSchema>;

export const SceneSchema = z.object({
  id: z.string(),
  stac_collection: z.string(),
  stac_item_id: z.string(),
  observed_at: z.string(),
  cloud_cover_pct: z.number().nullable(),
  platform: z.string().nullable(),
  instruments: z.array(z.string()).nullable(),
  selection_status: z.enum(["selected", "excluded"]),
  exclusion_reason: z.string().nullable(),
  source_provider: z.string(),
  assets: z.record(z.string(), z.unknown()),
  quality: z
    .object({
      aoi_overlap_pct: z.number().optional(),
      processing_baseline: z.string().optional(),
      unusable_reason: z.string().optional(),
      valid_pixel_pct: z.number().optional(),
      warnings: z.array(z.string()).optional(),
    })
    .nullable(),
  bbox: BboxSchema.nullable(),
});
export type Scene = z.infer<typeof SceneSchema>;

export const ScenesSchema = z.array(SceneSchema);

export const TimeseriesPointSchema = z.object({
  scene_id: z.string(),
  stac_item_id: z.string(),
  observed_at: z.string(),
  stac_cloud_cover_pct: z.number().nullable(),
  ndvi_min: z.number().nullable(),
  ndvi_max: z.number().nullable(),
  ndvi_mean: z.number().nullable(),
  ndvi_median: z.number().nullable(),
  ndvi_std: z.number().nullable(),
  ndvi_p10: z.number().nullable(),
  ndvi_p25: z.number().nullable(),
  ndvi_p75: z.number().nullable(),
  ndvi_p90: z.number().nullable(),
  valid_pixel_count: z.number(),
  masked_pixel_count: z.number(),
  valid_pixel_pct: z.number(),
});
export type TimeseriesPoint = z.infer<typeof TimeseriesPointSchema>;

export const TimeseriesSchema = z.object({
  analysis_id: z.string(),
  points: z.array(TimeseriesPointSchema),
});
export type Timeseries = z.infer<typeof TimeseriesSchema>;

export const ArtifactTypeSchema = z.enum([
  "ndvi_cog",
  "ndvi_preview",
  "true_color_preview",
  "scene_summary",
  "timeseries_csv",
  "analysis_summary",
  "provenance",
]);
export type ArtifactType = z.infer<typeof ArtifactTypeSchema>;

export const ArtifactSchema = z.object({
  id: z.string(),
  scene_id: z.string().nullable(),
  stac_item_id: z.string().nullable(),
  artifact_type: ArtifactTypeSchema,
  content_type: z.string(),
  size_bytes: z.number(),
  sha256: z.string(),
  crs: z.string().nullable(),
  created_at: z.string(),
  download_url: z.string(),
  download_url_expires_in_seconds: z.number(),
});
export type Artifact = z.infer<typeof ArtifactSchema>;

export const ArtifactListSchema = z.object({
  analysis_id: z.string(),
  items: z.array(ArtifactSchema),
});
export type ArtifactList = z.infer<typeof ArtifactListSchema>;

export const ProvenanceSchema = z
  .object({
    schema_version: z.union([z.string(), z.number()]).optional(),
    data_source: z.record(z.string(), z.unknown()).optional(),
    request: z.record(z.string(), z.unknown()).optional(),
    scene_selection: z
      .object({
        algorithm: z.string().optional(),
        algorithm_version: z.string().optional(),
        selected_count: z.number().optional(),
        excluded: z
          .array(z.object({ item_id: z.string(), reason: z.string() }))
          .optional(),
      })
      .passthrough()
      .optional(),
    processing: z
      .object({
        operation: z.string().optional(),
        config: z.record(z.string(), z.unknown()).optional(),
        masked_scl_classes: z.array(z.number()).optional(),
        masked_scl_class_names: z.array(z.string()).optional(),
      })
      .passthrough()
      .optional(),
    software: z
      .object({
        processing_version: z.string().optional(),
        git_commit_sha: z.string().nullable().optional(),
        container_image: z.string().nullable().optional(),
        python_version: z.string().optional(),
        key_packages: z.record(z.string(), z.string()).optional(),
      })
      .passthrough()
      .optional(),
    timing: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();
export type Provenance = z.infer<typeof ProvenanceSchema>;

export const HealthSchema = z.object({
  status: z.string(),
  checks: z.record(z.string(), z.unknown()),
});
export type Health = z.infer<typeof HealthSchema>;

/** RFC 7807 problem document (application/problem+json). */
export const ProblemSchema = z.object({
  type: z.string().optional(),
  title: z.string().optional(),
  status: z.number().optional(),
  detail: z.string().nullable().optional(),
  instance: z.string().optional(),
  errors: z
    .array(
      z.object({
        loc: z.union([z.string(), z.array(z.union([z.string(), z.number()]))]),
        message: z.string(),
      }),
    )
    .optional(),
});
export type Problem = z.infer<typeof ProblemSchema>;

export const CreateAnalysisRequestSchema = z.object({
  region_id: z.string().optional(),
  bbox: BboxSchema.optional(),
  start_date: z.string(),
  end_date: z.string(),
  max_cloud_cover_pct: z.number(),
  scene_limit: z.number().optional(),
});
export type CreateAnalysisRequest = z.infer<typeof CreateAnalysisRequestSchema>;
