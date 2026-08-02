"""Private blob storage with checksum uploads and short-lived download URLs.

Two authentication modes, selected by configuration:

- **Connection string** (Azurite / local dev): account-key SAS for downloads.
- **Account URL + DefaultAzureCredential** (Azure): user-delegation SAS, so
  the platform never handles storage account keys in the cloud.

Containers are always private; the ONLY way clients read artifacts is through
short-lived SAS URLs generated per request by the API.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    UserDelegationKey,
    generate_blob_sas,
)

from oeop_core.settings import Settings


@dataclass
class UploadResult:
    blob_path: str
    size_bytes: int
    sha256: str


class BlobStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._container = settings.artifacts_container
        if settings.storage_connection_string:
            self._client = BlobServiceClient.from_connection_string(
                settings.storage_connection_string
            )
            self._uses_key = True
        elif settings.blob_account_url:
            from azure.identity import DefaultAzureCredential

            self._client = BlobServiceClient(
                account_url=settings.blob_account_url,
                credential=DefaultAzureCredential(),
            )
            self._uses_key = False
        else:
            raise ValueError(
                "Blob storage is not configured: set OEOP_STORAGE_CONNECTION_STRING "
                "(local) or OEOP_BLOB_ACCOUNT_URL (managed identity)."
            )
        self._delegation_key: UserDelegationKey | None = None
        self._delegation_key_expiry: datetime | None = None

    def ensure_container(self) -> None:
        try:
            self._client.create_container(self._container)
        except ResourceExistsError:
            pass

    def upload_file(self, local_path: Path, blob_path: str, content_type: str) -> UploadResult:
        data = Path(local_path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        blob = self._client.get_blob_client(self._container, blob_path)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return UploadResult(blob_path=blob_path, size_bytes=len(data), sha256=digest)

    def download_bytes(self, blob_path: str) -> bytes:
        blob = self._client.get_blob_client(self._container, blob_path)
        return blob.download_blob().readall()

    def exists(self, blob_path: str) -> bool:
        return bool(self._client.get_blob_client(self._container, blob_path).exists())

    def delete_prefix(self, prefix: str) -> int:
        """Delete all blobs under a prefix (admin cleanup); returns count."""
        container = self._client.get_container_client(self._container)
        count = 0
        for blob in container.list_blobs(name_starts_with=prefix):
            container.delete_blob(blob.name)
            count += 1
        return count

    def _get_delegation_key(self) -> UserDelegationKey:
        now = datetime.now(UTC)
        if (
            self._delegation_key is None
            or self._delegation_key_expiry is None
            or self._delegation_key_expiry - now < timedelta(minutes=10)
        ):
            expiry = now + timedelta(hours=1)
            self._delegation_key = self._client.get_user_delegation_key(
                key_start_time=now - timedelta(minutes=5), key_expiry_time=expiry
            )
            self._delegation_key_expiry = expiry
        return self._delegation_key

    def generate_download_url(self, blob_path: str, ttl_seconds: int) -> str:
        """Short-lived read-only SAS URL for one blob."""
        expiry = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        account_name = self._client.account_name
        assert account_name is not None
        if self._uses_key:
            sas = generate_blob_sas(
                account_name=account_name,
                container_name=self._container,
                blob_name=blob_path,
                account_key=self._client.credential.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
            )
        else:
            sas = generate_blob_sas(
                account_name=account_name,
                container_name=self._container,
                blob_name=blob_path,
                user_delegation_key=self._get_delegation_key(),
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
            )
        blob = self._client.get_blob_client(self._container, blob_path)
        return f"{blob.url}?{sas}"
