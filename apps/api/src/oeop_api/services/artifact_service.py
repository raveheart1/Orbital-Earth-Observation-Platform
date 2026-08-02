"""Artifact download URLs.

Blob containers are private; clients receive short-lived read-only SAS URLs
generated per request. Blob paths always come from the artifacts table —
user input never reaches blob-path construction.
"""

from __future__ import annotations

import anyio

from oeop_core.azure.blob import BlobStore
from oeop_core.db.models import Artifact
from oeop_core.settings import Settings


async def download_url_for(artifact: Artifact, blob_store: BlobStore, settings: Settings) -> str:
    return await anyio.to_thread.run_sync(
        blob_store.generate_download_url,
        artifact.blob_path,
        settings.download_url_ttl_seconds,
    )


async def read_artifact_json(artifact: Artifact, blob_store: BlobStore) -> bytes:
    return await anyio.to_thread.run_sync(blob_store.download_bytes, artifact.blob_path)
