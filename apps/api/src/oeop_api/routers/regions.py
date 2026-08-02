"""Predefined region endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from oeop_api.deps import SessionDep
from oeop_api.problem import ProblemException
from oeop_api.schemas import RegionResponse
from oeop_api.services.serializers import serialize_region
from oeop_core.db.models import Region

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("", response_model=list[RegionResponse], summary="List predefined regions")
async def list_regions(session: SessionDep) -> list[RegionResponse]:
    result = await session.execute(select(Region).order_by(Region.name))
    return [serialize_region(region) for region in result.scalars()]


@router.get("/{region_id}", response_model=RegionResponse, summary="Region detail")
async def get_region(region_id: uuid.UUID, session: SessionDep) -> RegionResponse:
    region = await session.get(Region, region_id)
    if region is None:
        raise ProblemException(404, "Region not found", f"No region with id {region_id}")
    return serialize_region(region)
