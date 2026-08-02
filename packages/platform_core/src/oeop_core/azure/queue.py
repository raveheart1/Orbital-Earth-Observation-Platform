"""Analysis queue with visibility management and a poison queue.

Messages are small JSON envelopes — ``{"analysis_id": "...", "enqueued_at": ...}``
— the worker always loads the authoritative configuration from PostgreSQL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from azure.core.exceptions import ResourceExistsError
from azure.storage.queue import QueueClient, QueueServiceClient

from oeop_core.settings import Settings


@dataclass
class QueueMessage:
    id: str
    pop_receipt: str
    dequeue_count: int
    analysis_id: str
    enqueued_at: str | None
    raw_content: str


class AnalysisQueue:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if settings.storage_connection_string:
            self._service = QueueServiceClient.from_connection_string(
                settings.storage_connection_string
            )
        elif settings.queue_account_url:
            from azure.identity import DefaultAzureCredential

            self._service = QueueServiceClient(
                account_url=settings.queue_account_url,
                credential=DefaultAzureCredential(),
            )
        else:
            raise ValueError(
                "Queue storage is not configured: set OEOP_STORAGE_CONNECTION_STRING "
                "(local) or OEOP_QUEUE_ACCOUNT_URL (managed identity)."
            )
        self._queue: QueueClient = self._service.get_queue_client(settings.analysis_queue_name)
        self._poison: QueueClient = self._service.get_queue_client(settings.poison_queue_name)

    def ensure_queues(self) -> None:
        for queue in (self._queue, self._poison):
            try:
                queue.create_queue()
            except ResourceExistsError:
                pass

    def send_analysis(self, analysis_id: str) -> None:
        payload = json.dumps(
            {"analysis_id": analysis_id, "enqueued_at": datetime.now(UTC).isoformat()}
        )
        self._queue.send_message(payload)

    def receive(self, visibility_timeout: int) -> QueueMessage | None:
        messages = self._queue.receive_messages(
            messages_per_page=1, visibility_timeout=visibility_timeout
        )
        for msg in messages:
            content = msg.content or ""
            analysis_id, enqueued_at = _parse_content(content)
            return QueueMessage(
                id=msg.id,
                pop_receipt=msg.pop_receipt or "",
                dequeue_count=int(msg.dequeue_count or 1),
                analysis_id=analysis_id,
                enqueued_at=enqueued_at,
                raw_content=content,
            )
        return None

    def delete(self, message: QueueMessage) -> None:
        self._queue.delete_message(message.id, message.pop_receipt)

    def renew_visibility(self, message: QueueMessage, visibility_timeout: int) -> QueueMessage:
        """Extend the invisibility window of an in-flight message."""
        updated = self._queue.update_message(
            message.id,
            message.pop_receipt,
            visibility_timeout=visibility_timeout,
        )
        message.pop_receipt = updated.pop_receipt or message.pop_receipt
        return message

    def move_to_poison(self, message: QueueMessage, reason: str) -> None:
        envelope: dict[str, Any] = {
            "original": message.raw_content,
            "reason": reason,
            "dequeue_count": message.dequeue_count,
            "moved_at": datetime.now(UTC).isoformat(),
        }
        self._poison.send_message(json.dumps(envelope))
        self._queue.delete_message(message.id, message.pop_receipt)

    def approximate_depth(self) -> int:
        props = self._queue.get_queue_properties()
        return int(props.approximate_message_count or 0)


def _parse_content(content: str) -> tuple[str, str | None]:
    try:
        data = json.loads(content)
        return str(data["analysis_id"]), data.get("enqueued_at")
    except (json.JSONDecodeError, KeyError, TypeError):
        return "", None
