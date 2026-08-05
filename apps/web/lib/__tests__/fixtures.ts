/** Realistic API payload fixtures used by the schema and transform tests. */

export const configFixture = {
  environment: "local",
  demo_mode: true,
  submissions_enabled: true,
  custom_areas_enabled: true,
  // Two independent ceilings: curated regions may be large, and drawn areas
  // carry their own cap, set from measured processing cost.
  max_aoi_area_km2: 600,
  max_custom_aoi_area_km2: 250,
  min_aoi_area_km2: 0.5,
  max_date_span_days: 3660,
  min_start_date: "2015-07-01",
  selection_strategies: ["temporal", "seasonal"],
  // Above ~400 days an evenly spread series mostly measures season, not trend.
  seasonal_recommended_above_days: 400,
  max_scene_limit: 12,
  default_scene_limit: 8,
  max_cloud_cover_pct: 60,
  default_cloud_cover_pct: 20,
  map_default_center: [-83.5, 42.35],
  map_default_zoom: 8.5,
  ndvi_legend: {
    type: "ndvi",
    display_min: -0.2,
    display_max: 0.9,
    stops: [
      { value: -0.2, color: "#2c7bb6" },
      { value: 0.0, color: "#d7d1c0" },
      { value: 0.3, color: "#a6d96a" },
      { value: 0.9, color: "#1a9641" },
    ],
    masked_color: "#b0a8b9",
    masked_label: "Masked (cloud, shadow, snow)",
    nodata_color: "#686a72",
    nodata_label: "No source imagery",
    note: "masked pixels are transparent and excluded from all statistics; grey pixels had no source imagery",
  },
  demo_analysis_id: "0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77",
  processing_version: "2.0.0",
};

export const regionFixture = {
  id: "6f0a5c1e-1b2d-4a3e-8c4f-5d6e7f8a9b0c",
  name: "Ann Arbor & Huron River corridor",
  slug: "ann-arbor-huron",
  description: "Urban–rural gradient along the Huron River in Washtenaw County.",
  bbox: [-83.95, 42.2, -83.6, 42.35],
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-83.95, 42.2],
        [-83.6, 42.2],
        [-83.6, 42.35],
        [-83.95, 42.35],
        [-83.95, 42.2],
      ],
    ],
  },
  area_km2: 481.5,
  is_predefined: true,
  group: "Michigan",
};

/** Canonical analysis grid (processing v2.0.0+). */
export const gridFixture = {
  schema_version: "1.0",
  crs: "EPSG:32617",
  epsg: 32617,
  resolution: [10, 10],
  transform: [10, 0, 322730, 0, -10, 4696470],
  width: 1272,
  height: 1149,
  bounds_projected: [322730, 4684980, 335450, 4696470],
  bounds_geographic: [-83.95, 42.2, -83.6, 42.35],
  signature: "EPSG:32617:1272x1149:10,0,322730,0,-10,4696470",
};

export const analysisFixture = {
  id: "0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77",
  status: "succeeded",
  status_message: "Completed: 6 usable scenes processed.",
  region: regionFixture,
  bbox: [-83.95, 42.2, -83.6, 42.35],
  geometry: null,
  area_km2: 481.5,
  start_date: "2023-05-01",
  end_date: "2023-09-30",
  collection: "sentinel-2-l2a",
  max_cloud_cover_pct: 20,
  scene_limit: 8,
  selection_strategy: "temporal",
  seasonal_target_month: null,
  processing: {
    operation: "ndvi",
    version: "2.0.0",
    git_commit_sha: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
  },
  submitted_at: "2024-06-01T14:00:00Z",
  started_at: "2024-06-01T14:00:12Z",
  completed_at: "2024-06-01T14:03:41Z",
  failure: null,
  retry_count: 0,
  summary: {
    usable_scene_count: 6,
    unusable_scene_count: 2,
    first_observation: "2023-05-04T16:32:11Z",
    last_observation: "2023-09-26T16:33:49Z",
    ndvi_mean_first: 0.512,
    ndvi_mean_last: 0.431,
    ndvi_mean_change: -0.081,
    mean_valid_pixel_pct: 93.4,
    interpretation_note:
      "Observed change between first and last usable scenes; seasonality and acquisition timing may dominate.",
    min_aoi_coverage_pct: 99,
    identical_analytical_grid: true,
    comparison_note:
      "Every usable observation was resampled onto one canonical analytical grid, so imagery and statistics cover identical ground.",
  },
  grid: gridFixture,
  is_demo: true,
  links: {
    self: "/api/v1/analyses/0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77",
    scenes: "/api/v1/analyses/0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77/scenes",
    timeseries:
      "/api/v1/analyses/0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77/timeseries",
    artifacts:
      "/api/v1/analyses/0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77/artifacts",
    provenance:
      "/api/v1/analyses/0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77/provenance",
  },
};

export function timeseriesPointFixture(
  overrides: Partial<{
    scene_id: string;
    stac_item_id: string;
    observed_at: string;
    stac_cloud_cover_pct: number | null;
    ndvi_min: number | null;
    ndvi_max: number | null;
    ndvi_mean: number | null;
    ndvi_median: number | null;
    ndvi_std: number | null;
    ndvi_p10: number | null;
    ndvi_p25: number | null;
    ndvi_p75: number | null;
    ndvi_p90: number | null;
    valid_pixel_count: number;
    masked_pixel_count: number;
    valid_pixel_pct: number;
    aoi_coverage_pct: number | null;
    valid_coverage_pct: number | null;
    missing_data_pct: number | null;
    granule_count: number;
    contributing_item_ids: string[];
    tile_ids: string[];
  }> = {},
) {
  return {
    scene_id: "scene-1",
    stac_item_id: "S2A_MSIL2A_20230504T163211_R041_T17TLG",
    observed_at: "2023-05-04T16:32:11Z",
    stac_cloud_cover_pct: 4.2,
    ndvi_min: -0.11,
    ndvi_max: 0.89,
    ndvi_mean: 0.512,
    ndvi_median: 0.53,
    ndvi_std: 0.14,
    ndvi_p10: 0.31,
    ndvi_p25: 0.42,
    ndvi_p75: 0.63,
    ndvi_p90: 0.71,
    valid_pixel_count: 812345,
    masked_pixel_count: 34567,
    valid_pixel_pct: 95.9,
    aoi_coverage_pct: 100,
    valid_coverage_pct: 95.9,
    missing_data_pct: 0,
    granule_count: 2,
    contributing_item_ids: [
      "S2A_MSIL2A_20230504T163211_R041_T17TLG",
      "S2A_MSIL2A_20230504T163211_R041_T17TLH",
    ],
    tile_ids: ["T17TLG", "T17TLH"],
    ...overrides,
  };
}

/** Candidate scene as returned by /scenes (v2.0.0 contract). */
export function sceneFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "scene-1",
    stac_collection: "sentinel-2-l2a",
    stac_item_id: "S2A_MSIL2A_20230504T163211_R041_T17TLG",
    observed_at: "2023-05-04T16:32:11Z",
    cloud_cover_pct: 4.2,
    platform: "sentinel-2a",
    instruments: ["msi"],
    selection_status: "selected",
    exclusion_reason: null,
    source_provider: "earth-search-aws",
    assets: {
      S2A_MSIL2A_20230504T163211_R041_T17TLG: {
        visual: "https://example.com/T17TLG/visual.tif",
        red: "https://example.com/T17TLG/red.tif",
      },
      S2A_MSIL2A_20230504T163211_R041_T17TLH: {
        visual: "https://example.com/T17TLH/visual.tif",
        red: "https://example.com/T17TLH/red.tif",
      },
    },
    quality: { valid_pixel_pct: 95.9 },
    bbox: [-83.95, 42.2, -83.6, 42.35],
    acquisition_key: "2023-05-04T163211",
    contributing_item_ids: [
      "S2A_MSIL2A_20230504T163211_R041_T17TLG",
      "S2A_MSIL2A_20230504T163211_R041_T17TLH",
    ],
    tile_ids: ["T17TLG", "T17TLH"],
    granule_count: 2,
    aoi_coverage_pct: 100,
    valid_pixel_pct: 95.9,
    ...overrides,
  };
}

/** Artifact as returned by /artifacts (v2.0.0 contract). */
export function artifactFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "artifact-1",
    scene_id: "scene-1",
    stac_item_id: "S2A_MSIL2A_20230504T163211_R041_T17TLG",
    artifact_type: "ndvi_preview",
    content_type: "image/png",
    size_bytes: 204800,
    sha256: "ab".repeat(32),
    crs: "EPSG:32617",
    created_at: "2024-06-01T14:03:00Z",
    download_url: "https://example.com/signed/preview.png",
    download_url_expires_in_seconds: 3600,
    grid_signature: gridFixture.signature,
    ...overrides,
  };
}

export const timeseriesFixture = {
  analysis_id: "0d3f9a52-6f89-4a2e-9f4e-0f8b0e5c1a77",
  points: [
    timeseriesPointFixture(),
    timeseriesPointFixture({
      scene_id: "scene-2",
      stac_item_id: "S2B_MSIL2A_20230716T163159_R041_T17TKG",
      observed_at: "2023-07-16T16:31:59Z",
      ndvi_mean: 0.58,
      ndvi_median: 0.6,
      ndvi_p25: 0.49,
      ndvi_p75: 0.68,
      stac_cloud_cover_pct: 8.9,
      valid_pixel_pct: 91.2,
    }),
    timeseriesPointFixture({
      scene_id: "scene-3",
      stac_item_id: "S2A_MSIL2A_20230926T163349_R041_T17TKG",
      observed_at: "2023-09-26T16:33:49Z",
      ndvi_mean: 0.431,
      ndvi_median: 0.44,
      ndvi_p25: 0.35,
      ndvi_p75: 0.55,
      stac_cloud_cover_pct: 12.4,
      valid_pixel_pct: 89.7,
    }),
  ],
};
