"""Dependency injection: settings, database sessions, storage clients.

Heavy clients live on ``app.state`` (created at startup); request handlers
receive them through these dependencies so tests can substitute fakes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from oeop_core.azure.blob import BlobStore
from oeop_core.azure.queue import AnalysisQueue
from oeop_core.settings import Settings


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_blob_store(request: Request) -> BlobStore:
    store: BlobStore = request.app.state.blob_store
    return store


def get_queue(request: Request) -> AnalysisQueue:
    queue: AnalysisQueue = request.app.state.queue
    return queue


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
BlobDep = Annotated[BlobStore, Depends(get_blob_store)]
QueueDep = Annotated[AnalysisQueue, Depends(get_queue)]
