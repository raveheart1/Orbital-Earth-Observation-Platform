# Data provenance

Every completed analysis ships a machine-readable provenance document that
contains enough information to **audit** the result (what data, what code,
what parameters) and to **reproduce** it (re-run with identical
configuration). The document is validated against a JSON Schema (draft
2020-12) before it is persisted; an invalid document fails the run rather
than shipping unauditable results.

- Schema source of truth: `packages/earth_observation/src/earth_observation/provenance.py`
  (`PROVENANCE_SCHEMA`, version `1.0.0`)
- Published copy: [`schemas/provenance-1.0.0.json`](schemas/provenance-1.0.0.json)
- Methodology the parameters refer to:
  [scientific-methodology.md](scientific-methodology.md)

## What is recorded, and why

| Section | Contents | Why it is recorded |
| --- | --- | --- |
| `data_source` | STAC endpoint, collection, provider, license | Identifies the exact catalog; the same item id in a different catalog is not the same data. |
| `request` | AOI geometry + geodesic area (km²), start/end dates, cloud threshold, scene limit | The full user-controlled input surface. Everything needed to re-issue the query. |
| `canonical_grid` | Grid schema version, CRS/EPSG, resolution, affine transform, width/height, projected and geographic bounds, AOI geometry, signature | The single analytical grid every observation was reprojected onto. Two observations are only comparable if they share it, so it is recorded once per analysis and echoed per scene. |
| `scene_selection` | Algorithm name + version (`temporal-stratified-lowest-cloud` / `2.0.0`), selected count, the coverage threshold used, **every excluded acquisition with its reason and coverage** | Selection changes results as much as processing does. Recording exclusions (`insufficient_aoi_coverage`, `cloud_cover_above_threshold`, `not_selected_temporal_sampling`) makes "why isn't scene X in my series?" answerable. |
| `processing` | Operation (`ndvi`), the full `ProcessingConfig` snapshot, masked SCL classes (ids and names), **mosaic method**, **resampling method for spectral and categorical data** | The mask policy and every scientific parameter, frozen at run time. Resampling choices are recorded because they change pixel values; the categorical/nearest guarantee is what keeps SCL class labels meaningful. |
| `software` | `processing_version` (2.0.0), git commit SHA, container image, Python version, `uv.lock` sha256, key package versions | Pins the exact code. Two runs with identical config but different rasterio/GDAL versions are not guaranteed bit-identical. |
| `scenes` | Per **acquisition**: acquisition key, primary item id, **every contributing STAC item id**, **Sentinel-2 tile ids**, granule count, acquisition (sensing) time, cloud cover, processing baselines, **band scaling used and its source**, original **unsigned** asset hrefs keyed by item, **coverage accounting**, usable flag + reason, output CRS/transform/resolution, processing seconds, warnings | The per-observation scientific record. Listing every contributing granule is what makes a mosaicked observation auditable — see [ADR 0007](adr/0007-canonical-analysis-grid.md). |
| `outputs` | Every artifact: type, blob path, content type, **sha256**, size in bytes | Integrity: a downloaded artifact can be verified against its recorded digest. |
| `timing` | Started/completed timestamps, duration | Operational forensics and performance regression tracking. |
| `warnings` | Non-fatal anomalies (grid mismatches, missing visual asset, ...) | Anything unusual that did not stop the run must still be visible. |

## Unsigned vs signed URL policy

Planetary Computer assets require time-limited signed URLs. The platform's
rule is strict:

- **Sign immediately before access, never persist.** `sign_href` in
  `earth_observation/stac.py` is called at read time only; no other module
  imports the `planetary_computer` SDK.
- **Provenance stores the original unsigned hrefs.** Signed URLs expire
  within hours and embed access tokens — persisting them would make
  provenance both stale and mildly sensitive. Unsigned hrefs are stable
  identifiers that anyone can re-sign with their own Planetary Computer
  access.

## Schema structure summary

```
provenance (object, required keys marked *)
├─ schema_version*         const "1.0.0"
├─ analysis_id*            uuid
├─ created_at*             date-time
├─ data_source*            { stac_endpoint*, collection*, provider, license }
├─ request*                { aoi_geometry*, aoi_area_km2, start_date*,
│                            end_date*, max_cloud_cover_pct*, scene_limit }
├─ scene_selection*        { algorithm*, algorithm_version*, selected_count*,
│                            excluded*: [{ item_id*, reason* }] }
├─ processing*             { operation*, config*, masked_scl_classes,
│                            masked_scl_class_names }
├─ software*               { processing_version*, git_commit_sha,
│                            container_image, python_version,
│                            dependency_lock_sha256, key_packages }
├─ scenes*                 [{ item_id*, observed_at*, assets* (unsigned),
│                            cloud_cover_pct, processing_baseline,
│                            band_scaling, usable, unusable_reason,
│                            raster, processing_seconds, warnings }]
├─ outputs*                [{ artifact_type*, path*, sha256*, size_bytes*,
│                            scene_item_id, content_type }]
├─ timing                  { started_at, completed_at, duration_seconds }
└─ warnings                [string]
```

## Truncated example document

```json
{
  "schema_version": "1.0.0",
  "analysis_id": "7f3d2c1a-9b4e-4f6a-8c2d-1e5f7a9b3c4d",
  "created_at": "2026-07-14T18:02:11+00:00",
  "data_source": {
    "stac_endpoint": "https://planetarycomputer.microsoft.com/api/stac/v1",
    "collection": "sentinel-2-l2a",
    "provider": "Microsoft Planetary Computer",
    "license": "Copernicus Sentinel data terms"
  },
  "request": {
    "aoi_geometry": {
      "type": "Polygon",
      "coordinates": [[[-83.30, 42.55], [-83.15, 42.55], [-83.15, 42.65],
                       [-83.30, 42.65], [-83.30, 42.55]]]
    },
    "aoi_area_km2": 137.2385,
    "start_date": "2024-06-01",
    "end_date": "2024-09-30",
    "max_cloud_cover_pct": 20.0,
    "scene_limit": 6
  },
  "canonical_grid": {
    "schema_version": "1.0.0",
    "crs": "EPSG:32617",
    "epsg": 32617,
    "resolution": [10.0, 10.0],
    "transform": [10.0, 0.0, 322770.0, 0.0, -10.0, 4696430.0],
    "width": 1264,
    "height": 1141,
    "bounds_projected": [322770.0, 4685020.0, 335410.0, 4696430.0],
    "bounds_geographic": [-83.1506, 42.2996, -82.9993, 42.4004],
    "signature": "EPSG:32617:1264x1141:10,0,322770,0,-10,4.69643e+06"
  },
  "scene_selection": {
    "algorithm": "temporal-stratified-lowest-cloud",
    "algorithm_version": "2.0.0",
    "selected_count": 6,
    "min_aoi_coverage_pct": 99.0,
    "excluded": [
      {
        "acquisition_key": "sentinel-2-l2a|sentinel-2c|R040|2026-01-08T16:26:00+00:00",
        "primary_item_id": "S2C_MSIL2A_20260108T162651_R040_T17TLH_20260108T200411",
        "contributing_item_ids": ["S2C_MSIL2A_20260108T162651_R040_T17TLH_20260108T200411"],
        "aoi_coverage_pct": 56.2,
        "reason": "insufficient_aoi_coverage"
      }
    ]
  },
  "processing": {
    "operation": "ndvi",
    "config": {
      "collection": "sentinel-2-l2a",
      "masked_scl_classes": [0, 1, 3, 8, 9, 10, 11],
      "min_valid_pixel_pct": 10.0,
      "min_aoi_coverage_pct": 99.0,
      "grid_resolution_m": 10.0,
      "ndvi_display_min": -0.2,
      "ndvi_display_max": 0.9,
      "output_nodata": -9999.0,
      "processing_version": "2.0.0"
    },
    "mosaic_method": "first-valid-by-item-id",
    "resampling_spectral": "bilinear",
    "resampling_categorical": "nearest",
    "masked_scl_classes": [0, 1, 3, 8, 9, 10, 11],
    "masked_scl_class_names": ["NO_DATA", "SATURATED_OR_DEFECTIVE",
      "CLOUD_SHADOWS", "CLOUD_MEDIUM_PROBABILITY", "CLOUD_HIGH_PROBABILITY",
      "THIN_CIRRUS", "SNOW_OR_ICE"]
  },
  "software": {
    "processing_version": "2.0.0",
    "git_commit_sha": "9c1f2ab84d7e0c3b5a6f8d9e0a1b2c3d4e5f6a7b",
    "container_image": "oeopacr.azurecr.io/oeop-worker:9c1f2ab",
    "python_version": "3.12.8",
    "dependency_lock_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "key_packages": {"rasterio": "…", "rioxarray": "…", "pystac-client": "…"}
  },
  "scenes": [
    {
      "acquisition_key": "sentinel-2-l2a|sentinel-2a|R040|2026-05-30T16:27:00+00:00",
      "primary_item_id": "S2A_MSIL2A_20260530T162701_R040_T17TLG_20260531T041701",
      "contributing_item_ids": [
        "S2A_MSIL2A_20260530T162701_R040_T17TLG_20260531T041701",
        "S2A_MSIL2A_20260530T162701_R040_T17TLH_20260531T041701"
      ],
      "tile_ids": ["T17TLG", "T17TLH"],
      "granule_count": 2,
      "coverage": {
        "aoi_pixel_count": 1372771,
        "aoi_coverage_pct": 100.0,
        "valid_coverage_pct": 99.9851,
        "missing_data_pct": 0.0,
        "uncovered_pixel_count": 0,
        "cloud_masked_pixel_count": 204,
        "snow_masked_pixel_count": 0
      },
      "item_id_legacy_note": "1.x documents recorded a single item_id here",
      "observed_at": "2024-06-07T16:38:41+00:00",
      "cloud_cover_pct": 3.1,
      "processing_baseline": "05.10",
      "band_scaling": {"scale": 0.0001, "offset": -0.1,
                       "source": "baseline_heuristic"},
      "assets": {
        "red": "https://sentinel2l2a01.blob.core.windows.net/.../B04.tif",
        "nir": "https://sentinel2l2a01.blob.core.windows.net/.../B08.tif",
        "scl": "https://sentinel2l2a01.blob.core.windows.net/.../SCL.tif",
        "visual": "https://sentinel2l2a01.blob.core.windows.net/.../TCI.tif"
      },
      "usable": true,
      "unusable_reason": null,
      "raster": {"crs": "EPSG:32617", "resolution": [10.0, 10.0],
                 "width": 1247, "height": 1132, "nodata": -9999.0,
                 "transform": [10.0, 0.0, 306920.0, 0.0, -10.0, 4725220.0]},
      "processing_seconds": 41.3,
      "warnings": []
    }
  ],
  "outputs": [
    {
      "artifact_type": "ndvi_cog",
      "scene_item_id": "S2A_MSIL2A_20240607T163841_R126_T17TLH_20240608T014452",
      "path": "analyses/7f3d2c1a-9b4e-4f6a-8c2d-1e5f7a9b3c4d/S2A_.../ndvi.tif",
      "content_type": "image/tiff; application=geotiff; profile=cloud-optimized",
      "sha256": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
      "size_bytes": 2381244
    }
  ],
  "timing": {
    "started_at": "2026-07-14T18:02:12+00:00",
    "completed_at": "2026-07-14T18:06:47+00:00",
    "duration_seconds": 275.4
  },
  "warnings": []
}
```

(Asset hrefs, hashes, and ids above are illustrative but structurally
realistic; a real document is available from
`GET /api/v1/analyses/{id}/provenance`.)

## Reproducing a result from a provenance document

Given a provenance document, a third party with the repository can re-run the
analysis with identical configuration:

1. **Pin the code.** `git checkout <software.git_commit_sha>`, then
   `uv sync`. Verify `shasum -a 256 uv.lock` matches
   `software.dependency_lock_sha256` — if it does not, the environment is not
   the one that produced the result.
2. **Reconstruct the configuration.** `processing.config` is a verbatim
   `ProcessingConfig` dump:
   ```python
   from earth_observation.types import ProcessingConfig

   config = ProcessingConfig(**prov["processing"]["config"])
   ```
3. **Re-issue the search.** Use `request.aoi_geometry`,
   `request.start_date`, `request.end_date`, and
   `request.max_cloud_cover_pct` with
   `earth_observation.stac.search_scenes`. Note: the catalog is not frozen —
   items are occasionally reprocessed by ESA. Compare returned item ids with
   `scenes[].item_id`; discrepancies mean the catalog changed and should be
   reported alongside any reproduction.
4. **Re-select.** Run `earth_observation.selection.select_scenes` with the
   recorded scene limit, cloud threshold, and date range. The algorithm is
   deterministic (`scene_selection.algorithm_version` must match): identical
   candidates yield identical selection, including the exclusion list.
5. **Re-process.** For each scene, `earth_observation.processing.process_scene`
   with the same config. Asset URLs are re-signed at access time from the
   recorded unsigned hrefs.
6. **Verify.** Compare per-scene statistics, and compare artifact sha256
   digests against `outputs[].sha256`. Statistics should agree exactly for an
   unchanged catalog item, code version, and dependency set; byte-identical
   COGs additionally require the same GDAL build.

The notebook `notebooks/ndvi_southeast_michigan.ipynb` walks through steps
3–6 interactively using the same package.
