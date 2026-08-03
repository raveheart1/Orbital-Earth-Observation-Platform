"""Analysis endpoints: submit, status, scenes, time series, artifacts, provenance."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from oeop_api.deps import BlobDep, QueueDep, SessionDep, SettingsDep
from oeop_api.problem import ProblemException
from oeop_api.rate_limit import client_key_from_request
from oeop_api.schemas import (
    AnalysisCreateRequest,
    AnalysisListResponse,
    AnalysisResponse,
    ArtifactListResponse,
    ArtifactResponse,
    SceneResponse,
    TimeseriesResponse,
)
from oeop_api.services import analysis_service, artifact_service
from oeop_api.services.serializers import (
    serialize_analysis,
    serialize_scene,
    serialize_timeseries_point,
)
from oeop_core.db.models import Analysis, Artifact, ArtifactType, Observation, Region, Scene

router = APIRouter(prefix="/analyses", tags=["analyses"])


async def _load_analysis(session: SessionDep, analysis_id: uuid.UUID) -> Analysis:
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        raise ProblemException(404, "Analysis not found", f"No analysis with id {analysis_id}")
    return analysis


async def _region_for(session: SessionDep, analysis: Analysis) -> Region | None:
    if analysis.region_id is None:
        return None
    return await session.get(Region, analysis.region_id)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisResponse,
    summary="Submit a new NDVI analysis",
)
async def create_analysis(
    request: Request,
    body: AnalysisCreateRequest,
    session: SessionDep,
    queue: QueueDep,
    settings: SettingsDep,
    response: Response,
) -> AnalysisResponse:
    limiter = request.app.state.rate_limiter
    limiter.check(client_key_from_request(request))
    analysis = await analysis_service.create_analysis(
        session=session, queue=queue, settings=settings, request=body
    )
    region = await _region_for(session, analysis)
    payload = serialize_analysis(analysis, region=region)
    response.headers["Location"] = payload.links.self
    return payload


@router.get("", response_model=AnalysisListResponse, summary="List analyses")
async def list_analyses(
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AnalysisListResponse:
    total = (await session.execute(select(func.count(Analysis.id)))).scalar_one()
    result = await session.execute(
        select(Analysis).order_by(Analysis.submitted_at.desc()).limit(limit).offset(offset)
    )
    items = []
    for analysis in result.scalars():
        region = await _region_for(session, analysis)
        items.append(serialize_analysis(analysis, region=region))
    return AnalysisListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{analysis_id}", response_model=AnalysisResponse, summary="Analysis status")
async def get_analysis(analysis_id: uuid.UUID, session: SessionDep) -> AnalysisResponse:
    analysis = await _load_analysis(session, analysis_id)
    region = await _region_for(session, analysis)
    return serialize_analysis(analysis, region=region)


@router.get(
    "/{analysis_id}/scenes",
    response_model=list[SceneResponse],
    summary="Selected and excluded scenes",
)
async def list_scenes(analysis_id: uuid.UUID, session: SessionDep) -> list[SceneResponse]:
    await _load_analysis(session, analysis_id)
    result = await session.execute(
        select(Scene).where(Scene.analysis_id == analysis_id).order_by(Scene.observed_at)
    )
    return [serialize_scene(scene) for scene in result.scalars()]


@router.get(
    "/{analysis_id}/timeseries",
    response_model=TimeseriesResponse,
    summary="NDVI time series (actual observation dates; never interpolated)",
)
async def get_timeseries(analysis_id: uuid.UUID, session: SessionDep) -> TimeseriesResponse:
    await _load_analysis(session, analysis_id)
    result = await session.execute(
        select(Observation, Scene)
        .join(Scene, Observation.scene_id == Scene.id)
        .where(Observation.analysis_id == analysis_id)
        .order_by(Scene.observed_at)
    )
    points = [serialize_timeseries_point(obs, scene) for obs, scene in result.all()]
    return TimeseriesResponse(analysis_id=analysis_id, points=points)


@router.get(
    "/{analysis_id}/artifacts",
    response_model=ArtifactListResponse,
    summary="Artifact metadata with short-lived download URLs",
)
async def list_artifacts(
    analysis_id: uuid.UUID,
    session: SessionDep,
    blob_store: BlobDep,
    settings: SettingsDep,
) -> ArtifactListResponse:
    await _load_analysis(session, analysis_id)
    result = await session.execute(
        select(Artifact, Scene.stac_item_id)
        .outerjoin(Scene, Artifact.scene_id == Scene.id)
        .where(Artifact.analysis_id == analysis_id)
        .order_by(Artifact.created_at)
    )
    items = []
    for artifact, stac_item_id in result.all():
        url = await artifact_service.download_url_for(artifact, blob_store, settings)
        items.append(
            ArtifactResponse(
                id=artifact.id,
                scene_id=artifact.scene_id,
                stac_item_id=stac_item_id,
                artifact_type=artifact.artifact_type.value,
                content_type=artifact.content_type,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
                crs=artifact.crs,
                created_at=artifact.created_at,
                grid_signature=(artifact.provenance or {}).get("grid_signature"),
                download_url=url,
                download_url_expires_in_seconds=settings.download_url_ttl_seconds,
            )
        )
    return ArtifactListResponse(analysis_id=analysis_id, items=items)


@router.get(
    "/{analysis_id}/provenance",
    summary="Machine-readable provenance document",
    response_class=JSONResponse,
)
async def get_provenance(
    analysis_id: uuid.UUID, session: SessionDep, blob_store: BlobDep
) -> Response:
    await _load_analysis(session, analysis_id)
    result = await session.execute(
        select(Artifact).where(
            Artifact.analysis_id == analysis_id,
            Artifact.artifact_type == ArtifactType.PROVENANCE,
        )
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise ProblemException(
            404,
            "Provenance not available",
            "Provenance is written when the analysis completes.",
        )
    data = await artifact_service.read_artifact_json(artifact, blob_store)
    return Response(content=data, media_type="application/json")
