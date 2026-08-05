"""Analysis execution: claim, process, persist, finalize.

Reliability properties:

- **Claiming** is a conditional UPDATE — only a ``queued`` analysis (or a
  ``running`` one whose lease went stale) can be claimed, so two workers can
  never process the same analysis concurrently.
- **Idempotency**: each attempt starts from a clean slate — prior partial
  scenes/observations/artifacts and blobs for the analysis are removed before
  reprocessing, and the analysis is only marked ``succeeded`` after every
  artifact and metadata row is durably persisted.
- **Error taxonomy**: user/data errors fail terminally with a sanitized
  message; transient errors propagate so the queue redelivers the message.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping, shape
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from earth_observation import PROCESSING_VERSION
from earth_observation.acquisition import group_acquisitions
from earth_observation.errors import (
    DataError,
    NoUsableScenesError,
    TransientError,
    UserInputError,
)
from earth_observation.grid import CanonicalGrid
from earth_observation.processing import process_acquisition
from earth_observation.provenance import build_provenance
from earth_observation.selection import (
    SelectionStrategy,
    select_acquisitions,
    select_acquisitions_seasonal,
)
from earth_observation.stac import search_scenes
from earth_observation.timeseries import analysis_summary, write_timeseries_csv
from earth_observation.types import ProcessingConfig, SceneResult
from oeop_core.azure.blob import BlobStore
from oeop_core.db.models import (
    Analysis,
    AnalysisStatus,
    Artifact,
    ArtifactType,
    FailureCategory,
    Observation,
    Region,
    Scene,
    SceneSelectionStatus,
)
from oeop_core.logging import get_logger
from oeop_core.settings import Settings
from oeop_core.telemetry import WorkerMetrics

logger = get_logger(__name__)

STALE_LEASE = timedelta(hours=2)


class JobTimeoutError(Exception):
    """The analysis exceeded the configured maximum runtime."""


@dataclass
class Outcome:
    status: str  # "succeeded" | "failed" | "skipped"
    detail: str = ""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _software_metadata(settings: Settings) -> dict[str, Any]:
    def version_of(package: str) -> str:
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    lock_sha: str | None = None
    for candidate in (Path("/app/uv.lock"), Path("uv.lock")):
        if candidate.exists():
            lock_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
            break
    return {
        "processing_version": PROCESSING_VERSION,
        "git_commit_sha": settings.git_commit_sha,
        "container_image": settings.container_image,
        "python_version": sys.version.split()[0],
        "dependency_lock_sha256": lock_sha,
        "key_packages": {
            name: version_of(name)
            for name in ("rasterio", "rioxarray", "numpy", "pystac-client", "rio-cogeo")
        },
    }


async def claim_analysis(session: AsyncSession, analysis_id: uuid.UUID) -> Analysis | None:
    """Atomically transition queued (or stale-running) -> running."""
    stale_cutoff = _utcnow() - STALE_LEASE
    result = await session.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            (Analysis.status == AnalysisStatus.QUEUED)
            | ((Analysis.status == AnalysisStatus.RUNNING) & (Analysis.started_at < stale_cutoff)),
        )
        .values(
            status=AnalysisStatus.RUNNING,
            started_at=_utcnow(),
            status_message="Processing",
            failure_category=None,
            failure_detail=None,
        )
        .returning(Analysis.id)
    )
    await session.commit()
    if result.first() is None:
        return None
    return await session.get(Analysis, analysis_id)


async def _reset_previous_attempt(
    session: AsyncSession, blob: BlobStore, analysis_id: uuid.UUID
) -> None:
    """Remove partial outputs from an earlier attempt (idempotent reprocessing)."""
    await session.execute(delete(Artifact).where(Artifact.analysis_id == analysis_id))
    await session.execute(delete(Observation).where(Observation.analysis_id == analysis_id))
    await session.execute(delete(Scene).where(Scene.analysis_id == analysis_id))
    await session.commit()
    deleted = blob.delete_prefix(f"analyses/{analysis_id}/")
    if deleted:
        logger.info("stale_blobs_deleted", analysis_id=str(analysis_id), count=deleted)


class _StorageBudget:
    def __init__(self, limit_mb: int, analysis_id: str) -> None:
        self.limit_bytes = limit_mb * 1024 * 1024
        self.used = 0
        self.analysis_id = analysis_id

    def charge(self, size: int) -> None:
        self.used += size
        if self.used > self.limit_bytes:
            raise DataError(
                f"Analysis exceeded the per-analysis storage limit "
                f"({self.limit_bytes // (1024 * 1024)} MB); reduce the AOI or scene count"
            )


async def _upload(
    session: AsyncSession,
    blob: BlobStore,
    budget: _StorageBudget,
    metrics: WorkerMetrics,
    *,
    analysis_id: uuid.UUID,
    scene_id: uuid.UUID | None,
    artifact_type: ArtifactType,
    local_path: Path,
    blob_path: str,
    content_type: str,
    crs: str | None = None,
    bbox: list[float] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    result = blob.upload_file(local_path, blob_path, content_type)
    metrics.blob_upload_duration.record(time.monotonic() - started)
    budget.charge(result.size_bytes)
    session.add(
        Artifact(
            analysis_id=analysis_id,
            scene_id=scene_id,
            artifact_type=artifact_type,
            container=blob._settings.artifacts_container,
            blob_path=blob_path,
            content_type=content_type,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            crs=crs,
            bbox=bbox,
            provenance=provenance,
        )
    )
    return {
        "artifact_type": artifact_type.value,
        "scene_item_id": None,
        "path": blob_path,
        "content_type": content_type,
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
    }


async def process_analysis(
    analysis_id: uuid.UUID,
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    blob: BlobStore,
    metrics: WorkerMetrics,
) -> Outcome:
    """Run one analysis end to end. See module docstring for guarantees."""
    job_started = time.monotonic()
    deadline = job_started + settings.max_job_runtime_seconds

    async with session_factory() as session:
        analysis = await claim_analysis(session, analysis_id)
        if analysis is None:
            current = await session.get(Analysis, analysis_id)
            if current is None:
                return Outcome("skipped", f"analysis {analysis_id} does not exist")
            if current.status == AnalysisStatus.SUCCEEDED:
                return Outcome("skipped", "analysis already succeeded")
            return Outcome("skipped", f"analysis not claimable (status={current.status.value})")

        logger.info("analysis_claimed", analysis_id=str(analysis_id))
        try:
            outcome = await _run_pipeline(session, analysis, settings, blob, metrics, deadline)
            metrics.job_duration.record(time.monotonic() - job_started)
            metrics.analyses_succeeded.add(1)
            return outcome
        except (UserInputError, DataError, JobTimeoutError) as exc:
            if isinstance(exc, UserInputError):
                category = FailureCategory.USER_INPUT
            elif isinstance(exc, JobTimeoutError):
                category = FailureCategory.TIMEOUT
            else:  # DataError, incl. NoUsableScenesError
                category = FailureCategory.DATA
            await _mark_failed(session, analysis_id, category, str(exc))
            metrics.analyses_failed.add(1)
            metrics.job_duration.record(time.monotonic() - job_started)
            return Outcome("failed", str(exc))
        except TransientError:
            # Leave status=running; the queue message becomes visible again and
            # the stale-lease rule allows reclaim. Do NOT delete the message.
            logger.warning("analysis_transient_error", analysis_id=str(analysis_id))
            raise
        except Exception as exc:
            logger.error("analysis_internal_error", analysis_id=str(analysis_id), exc_info=exc)
            await _mark_failed(
                session,
                analysis_id,
                FailureCategory.INTERNAL,
                "Internal processing error; see server logs for details.",
            )
            metrics.analyses_failed.add(1)
            return Outcome("failed", "internal error")


async def _mark_failed(
    session: AsyncSession,
    analysis_id: uuid.UUID,
    category: FailureCategory,
    detail: str,
) -> None:
    await session.rollback()
    await session.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id)
        .values(
            status=AnalysisStatus.FAILED,
            failure_category=category,
            failure_detail=detail[:1000],
            status_message="Failed",
            completed_at=_utcnow(),
        )
    )
    await session.commit()
    logger.info(
        "analysis_failed",
        analysis_id=str(analysis_id),
        category=category.value,
        detail=detail[:200],
    )


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise JobTimeoutError(
            "Analysis exceeded the maximum job runtime; reduce the AOI, date span, or scene count"
        )


async def _aoi_geojson(session: AsyncSession, analysis: Analysis) -> dict[str, Any]:
    if analysis.geometry is not None:
        return dict(mapping(to_shape(analysis.geometry)))
    if analysis.region_id is not None:
        region = await session.get(Region, analysis.region_id)
        if region is not None:
            return dict(mapping(to_shape(region.geometry)))
    raise UserInputError("Analysis has neither a geometry nor a valid region")


async def _run_pipeline(
    session: AsyncSession,
    analysis: Analysis,
    settings: Settings,
    blob: BlobStore,
    metrics: WorkerMetrics,
    deadline: float,
) -> Outcome:
    analysis_id = analysis.id
    await _reset_previous_attempt(session, blob, analysis_id)

    config = ProcessingConfig(**analysis.processing_config)
    analysis_warnings: list[str] = []
    aoi_geojson = await _aoi_geojson(session, analysis)
    aoi_bounds = shape(aoi_geojson).bounds

    # ONE grid per analysis; every observation is reprojected onto it, so all
    # dates share an identical footprint by construction.
    grid = CanonicalGrid.from_aoi(aoi_geojson, resolution_m=config.grid_resolution_m)
    await session.execute(
        update(Analysis).where(Analysis.id == analysis_id).values(grid=grid.to_dict())
    )
    await session.commit()
    logger.info(
        "canonical_grid_derived",
        analysis_id=str(analysis_id),
        crs=grid.crs,
        width=grid.width,
        height=grid.height,
        signature=grid.signature(),
    )

    # --- 1. Canonical grid + candidate discovery ---------------------------
    stac_started = time.monotonic()
    search_result = search_scenes(
        config,
        aoi_bounds,
        analysis.start_date.isoformat(),
        analysis.end_date.isoformat(),
        analysis.max_cloud_cover_pct,
    )
    metrics.stac_duration.record(time.monotonic() - stac_started)
    candidates = search_result.candidates
    logger.info(
        "stac_search_complete",
        analysis_id=str(analysis_id),
        candidates=len(candidates),
        windows=len(search_result.windows),
        truncated_windows=search_result.truncated_windows,
    )
    if search_result.truncated:
        # The candidate set for those periods is incomplete, so selection saw
        # only part of what exists. Surface it rather than silently proceeding.
        analysis_warnings.append(
            "STAC search hit its per-window item cap for "
            f"{', '.join(search_result.truncated_windows)}; more acquisitions may "
            "exist in those periods than were considered."
        )
    if not candidates:
        raise NoUsableScenesError(
            "No Sentinel-2 scenes match the requested area, dates, and cloud cover. "
            "Widen the date range or raise the cloud-cover threshold."
        )
    _check_deadline(deadline)

    # --- 2. Group granules into acquisitions, then select ------------------
    acquisitions = group_acquisitions(candidates, aoi_geojson)
    multi = [a for a in acquisitions if a.granule_count > 1]
    logger.info(
        "acquisitions_grouped",
        analysis_id=str(analysis_id),
        acquisitions=len(acquisitions),
        multi_granule=len(multi),
    )
    if analysis.selection_strategy == SelectionStrategy.SEASONAL.value:
        target_month = (
            analysis.seasonal_target_month
            or (analysis.start_date + (analysis.end_date - analysis.start_date) / 2).month
        )
        selection = select_acquisitions_seasonal(
            acquisitions,
            scene_limit=analysis.scene_limit,
            max_cloud_cover_pct=analysis.max_cloud_cover_pct,
            min_aoi_coverage_pct=config.min_aoi_coverage_pct,
            target_month=target_month,
            tolerance_days=config.seasonal_tolerance_days,
        )
    else:
        selection = select_acquisitions(
            acquisitions,
            scene_limit=analysis.scene_limit,
            max_cloud_cover_pct=analysis.max_cloud_cover_pct,
            min_aoi_coverage_pct=config.min_aoi_coverage_pct,
            range_start=datetime.combine(analysis.start_date, datetime.min.time(), UTC),
            range_end=datetime.combine(analysis.end_date, datetime.max.time(), UTC),
        )
    if not selection.selected:
        raise NoUsableScenesError(
            "No acquisition covers at least "
            f"{config.min_aoi_coverage_pct:.0f}% of the area of interest within the "
            "requested dates and cloud-cover threshold. Widen the date range or "
            "raise the cloud-cover threshold."
        )

    def _scene_row(acq: Any, *, selected: bool, reason: str | None = None) -> Scene:
        return Scene(
            analysis_id=analysis_id,
            stac_collection=acq.collection,
            stac_item_id=acq.primary_item_id,
            acquisition_key=acq.key,
            observed_at=acq.observed_at,
            geometry=None,
            bbox=list(acq.granules[0].bbox),
            cloud_cover_pct=acq.cloud_cover_pct,
            platform=acq.platform,
            instruments=acq.granules[0].instruments,
            assets={g.item_id: dict(g.assets) for g in acq.granules},
            contributing_item_ids=acq.item_ids,
            tile_ids=acq.tile_ids,
            granule_count=acq.granule_count,
            aoi_coverage_pct=round(acq.aoi_coverage_pct, 4),
            selection_status=(
                SceneSelectionStatus.SELECTED if selected else SceneSelectionStatus.EXCLUDED
            ),
            exclusion_reason=reason,
            quality={
                "geometric_aoi_coverage_pct": round(acq.aoi_coverage_pct, 4),
                "relative_orbit": acq.relative_orbit,
                "processing_baselines": acq.processing_baselines,
            },
        )

    scene_rows: dict[str, Scene] = {}
    for acq in selection.selected:
        row = _scene_row(acq, selected=True)
        session.add(row)
        scene_rows[acq.key] = row
    for excluded in selection.excluded:
        session.add(_scene_row(excluded.acquisition, selected=False, reason=excluded.reason))
    await session.commit()
    logger.info(
        "acquisitions_selected",
        analysis_id=str(analysis_id),
        selected=len(selection.selected),
        excluded=len(selection.excluded),
    )

    # --- 3. Process each acquisition onto the canonical grid ---------------
    budget = _StorageBudget(settings.per_analysis_storage_limit_mb, str(analysis_id))
    output_prefix = f"analyses/{analysis_id}"
    results: list[SceneResult] = []
    provenance_outputs: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="oeop-") as tmp:
        workdir = Path(tmp)
        for acq in selection.selected:
            _check_deadline(deadline)
            result = process_acquisition(acq, grid, config, workdir)
            results.append(result)
            metrics.scene_duration.record(result.processing_seconds)
            scene_row = scene_rows[acq.key]
            logger.info(
                "acquisition_processed",
                analysis_id=str(analysis_id),
                acquisition_key=acq.key,
                granules=acq.granule_count,
                tiles=acq.tile_ids,
                usable=result.usable,
                seconds=result.processing_seconds,
                aoi_coverage_pct=result.coverage.aoi_coverage_pct if result.coverage else None,
                valid_pct=result.stats.valid_pixel_pct if result.stats else None,
            )

            if result.stats is not None:
                metrics.valid_pixel_pct.record(result.stats.valid_pixel_pct)

            # Coverage and valid-pixel figures are recorded for EVERY scene row,
            # selected or not, so the UI never has to show a dash.
            quality = dict(scene_row.quality or {})
            quality["warnings"] = result.warnings
            if result.coverage is not None:
                quality.update(
                    {
                        "aoi_coverage_pct": result.coverage.aoi_coverage_pct,
                        "valid_coverage_pct": result.coverage.valid_coverage_pct,
                        "masked_pct": result.coverage.masked_pct,
                        "missing_data_pct": result.coverage.missing_data_pct,
                        "contributing_item_ids": result.coverage.contributing_item_ids,
                    }
                )
            if result.stats is not None:
                quality["valid_pixel_pct"] = result.stats.valid_pixel_pct
            if not result.usable:
                quality["unusable_reason"] = result.unusable_reason
            scene_row.quality = quality
            if result.coverage is not None:
                scene_row.valid_pixel_pct = result.stats.valid_pixel_pct if result.stats else None
                scene_row.aoi_coverage_pct = result.coverage.aoi_coverage_pct
            if not result.usable:
                scene_row.selection_status = SceneSelectionStatus.EXCLUDED
                scene_row.exclusion_reason = result.unusable_reason
                continue

            assert result.stats is not None
            assert result.outputs is not None
            stats = result.stats
            session.add(
                Observation(
                    analysis_id=analysis_id,
                    scene_id=scene_row.id,
                    ndvi_min=stats.ndvi_min,
                    ndvi_max=stats.ndvi_max,
                    ndvi_mean=stats.ndvi_mean,
                    ndvi_median=stats.ndvi_median,
                    ndvi_std=stats.ndvi_std,
                    ndvi_p10=stats.ndvi_p10,
                    ndvi_p25=stats.ndvi_p25,
                    ndvi_p75=stats.ndvi_p75,
                    ndvi_p90=stats.ndvi_p90,
                    valid_pixel_count=stats.valid_pixel_count,
                    masked_pixel_count=stats.masked_pixel_count,
                    aoi_pixel_count=stats.aoi_pixel_count,
                    valid_pixel_pct=stats.valid_pixel_pct,
                    zero_denominator_pixel_count=stats.zero_denominator_pixel_count,
                    uncovered_pixel_count=(
                        result.coverage.uncovered_pixel_count if result.coverage else 0
                    ),
                    aoi_coverage_pct=(
                        result.coverage.aoi_coverage_pct if result.coverage else 100.0
                    ),
                    valid_coverage_pct=(
                        result.coverage.valid_coverage_pct if result.coverage else 0.0
                    ),
                    missing_data_pct=(result.coverage.missing_data_pct if result.coverage else 0.0),
                    granule_count=(result.coverage.granule_count if result.coverage else 1),
                    mask_scl_classes=list(config.masked_scl_classes),
                    band_scaling=result.scaling.model_dump() if result.scaling else {},
                    processing_params={
                        "operation": "ndvi",
                        "resampling_spectral": "bilinear",
                        "resampling_categorical": "nearest",
                        "min_valid_pixel_pct": config.min_valid_pixel_pct,
                        "min_aoi_coverage_pct": config.min_aoi_coverage_pct,
                        "grid_signature": grid.signature(),
                    },
                    processing_seconds=result.processing_seconds,
                )
            )

            scene_prefix = f"{output_prefix}/scenes/{acq.primary_item_id}"
            raster = result.raster
            uploads = [
                (ArtifactType.NDVI_COG, result.outputs.ndvi_cog, "image/tiff", "ndvi.tif"),
                (
                    ArtifactType.NDVI_PREVIEW,
                    result.outputs.ndvi_preview,
                    "image/png",
                    "ndvi_preview.png",
                ),
                (
                    ArtifactType.SCENE_SUMMARY,
                    result.outputs.scene_summary,
                    "application/json",
                    "summary.json",
                ),
            ]
            if result.outputs.true_color_preview:
                uploads.append(
                    (
                        ArtifactType.TRUE_COLOR_PREVIEW,
                        result.outputs.true_color_preview,
                        "image/png",
                        "true_color.png",
                    )
                )
            for artifact_type, local, content_type, name in uploads:
                record = await _upload(
                    session,
                    blob,
                    budget,
                    metrics,
                    analysis_id=analysis_id,
                    scene_id=scene_row.id,
                    artifact_type=artifact_type,
                    local_path=Path(local),
                    blob_path=f"{scene_prefix}/{name}",
                    content_type=content_type,
                    crs=raster.crs if raster else None,
                    bbox=list(grid.bounds_geographic),
                    provenance={
                        "grid_signature": grid.signature(),
                        "width": grid.width,
                        "height": grid.height,
                        "contributing_item_ids": acq.item_ids,
                    },
                )
                record["scene_item_id"] = acq.primary_item_id
                provenance_outputs.append(record)
            await session.commit()

        usable = [r for r in results if r.usable]
        if not usable:
            reasons = sorted({r.unusable_reason for r in results if r.unusable_reason})
            raise NoUsableScenesError(
                "No acquisition produced a usable observation over the full area "
                f"of interest ({', '.join(reasons) or 'unknown'}). Try different "
                "dates or a lower cloud-cover threshold."
            )

        # Hard invariant: comparability is the whole point of the canonical
        # grid, so refuse to publish an analysis whose observations somehow
        # ended up on different grids.
        signatures = {
            f"{r.raster.crs}:{r.raster.width}x{r.raster.height}:{r.raster.transform}"
            for r in usable
            if r.raster is not None
        }
        if len(signatures) > 1:
            raise DataError(
                "Internal consistency check failed: usable observations do not "
                f"share one analytical grid ({len(signatures)} distinct grids)."
            )

        # --- 4. Analysis-level outputs -------------------------------------
        timeseries_path = workdir / "timeseries.csv"
        write_timeseries_csv(timeseries_path, results)
        summary = analysis_summary(results)
        summary_path = workdir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))

        for agg_type, agg_path, agg_content_type, agg_name in (
            (ArtifactType.TIMESERIES_CSV, timeseries_path, "text/csv", "timeseries.csv"),
            (ArtifactType.ANALYSIS_SUMMARY, summary_path, "application/json", "summary.json"),
        ):
            record = await _upload(
                session,
                blob,
                budget,
                metrics,
                analysis_id=analysis_id,
                scene_id=None,
                artifact_type=agg_type,
                local_path=agg_path,
                blob_path=f"{output_prefix}/{agg_name}",
                content_type=agg_content_type,
            )
            provenance_outputs.append(record)

        completed_at = _utcnow()
        started_at = analysis.started_at or completed_at
        provenance_doc = build_provenance(
            analysis_id=str(analysis_id),
            created_at=completed_at.isoformat(),
            config=config,
            grid=grid,
            aoi_geometry=aoi_geojson,
            aoi_area_km2=analysis.area_km2,
            start_date=analysis.start_date.isoformat(),
            end_date=analysis.end_date.isoformat(),
            max_cloud_cover_pct=analysis.max_cloud_cover_pct,
            scene_limit=analysis.scene_limit,
            selection=selection,
            results=results,
            outputs=provenance_outputs,
            software=_software_metadata(settings),
            timing={
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
            },
        )
        provenance_path = workdir / "provenance.json"
        provenance_path.write_text(json.dumps(provenance_doc, indent=2, sort_keys=True))
        await _upload(
            session,
            blob,
            budget,
            metrics,
            analysis_id=analysis_id,
            scene_id=None,
            artifact_type=ArtifactType.PROVENANCE,
            local_path=provenance_path,
            blob_path=f"{output_prefix}/provenance.json",
            content_type="application/json",
            provenance={"schema_version": provenance_doc["schema_version"]},
        )

    # --- 5. Finalize (only after everything above is durable) ---------------
    await session.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id)
        .values(
            status=AnalysisStatus.SUCCEEDED,
            status_message="Completed",
            completed_at=_utcnow(),
            summary=summary,
            output_prefix=output_prefix,
        )
    )
    await session.commit()
    logger.info(
        "analysis_succeeded",
        analysis_id=str(analysis_id),
        usable_scenes=len(usable),
        storage_bytes=budget.used,
    )
    return Outcome("succeeded", f"{len(usable)} usable scenes")
