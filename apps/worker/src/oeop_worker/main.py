"""Worker entry point.

Modes:
  (default)                  Poll the queue until stopped (SIGTERM-safe).
  --once                     Handle at most one queue message, then exit.
  --analysis-id <uuid>       Process one analysis directly (local debugging;
                             bypasses the queue entirely).

While a message is being processed, a background thread renews its visibility
timeout so long-running work is never redelivered mid-flight. Messages are
deleted only after durable completion (success OR terminal failure recorded
in the database); transient faults leave the message to reappear, and
messages that exceed the dequeue-count limit move to the poison queue.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import threading
import uuid
from datetime import UTC, datetime

from oeop_core.azure.blob import BlobStore
from oeop_core.azure.queue import AnalysisQueue, QueueMessage
from oeop_core.db.session import create_engine, create_session_factory
from oeop_core.logging import configure_logging, get_logger
from oeop_core.settings import Settings, get_settings
from oeop_core.telemetry import WorkerMetrics, setup_telemetry
from oeop_worker.runner import Outcome, process_analysis

logger = get_logger(__name__)


class VisibilityRenewer:
    """Renews a message's visibility timeout on an interval, in a thread.

    Uses its own queue client: Azure SDK clients are not guaranteed
    thread-safe, and the renewal must keep working while the asyncio loop is
    blocked in raster processing.
    """

    def __init__(self, settings: Settings, message: QueueMessage) -> None:
        self._settings = settings
        self._message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> QueueMessage:
        self._thread.start()
        return self._message

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _run(self) -> None:
        queue = AnalysisQueue(self._settings)
        interval = max(self._settings.queue_visibility_timeout_seconds // 3, 10)
        while not self._stop.wait(interval):
            try:
                queue.renew_visibility(
                    self._message, self._settings.queue_visibility_timeout_seconds
                )
                logger.debug("visibility_renewed", message_id=self._message.id)
            except Exception as exc:
                logger.warning("visibility_renewal_failed", error=str(exc))
                return


class Worker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.queue = AnalysisQueue(settings)
        self.blob = BlobStore(settings)
        self.engine = create_engine(settings)
        self.session_factory = create_session_factory(self.engine)
        self.metrics = WorkerMetrics()
        self.shutdown = asyncio.Event()

    async def close(self) -> None:
        await self.engine.dispose()

    async def run_direct(self, analysis_id: uuid.UUID) -> int:
        """--analysis-id mode: process one analysis without the queue."""
        outcome = await process_analysis(
            analysis_id,
            settings=self.settings,
            session_factory=self.session_factory,
            blob=self.blob,
            metrics=self.metrics,
        )
        logger.info("direct_run_complete", status=outcome.status, detail=outcome.detail)
        return 0 if outcome.status in ("succeeded", "skipped") else 1

    async def handle_one_message(self) -> bool:
        """Receive and fully handle a single message. Returns False if queue empty."""
        message = await asyncio.to_thread(
            self.queue.receive, self.settings.queue_visibility_timeout_seconds
        )
        if message is None:
            return False

        if not message.analysis_id:
            logger.warning("malformed_message_poisoned", message_id=message.id)
            await asyncio.to_thread(self.queue.move_to_poison, message, "malformed message body")
            return True

        if message.dequeue_count > self.settings.max_dequeue_count:
            logger.warning(
                "message_poisoned_max_dequeue",
                message_id=message.id,
                analysis_id=message.analysis_id,
                dequeue_count=message.dequeue_count,
            )
            await asyncio.to_thread(
                self.queue.move_to_poison,
                message,
                f"exceeded max dequeue count ({self.settings.max_dequeue_count})",
            )
            return True

        if message.enqueued_at:
            try:
                enqueued = datetime.fromisoformat(message.enqueued_at)
                delay = (datetime.now(UTC) - enqueued).total_seconds()
                self.metrics.queue_delay.record(max(delay, 0.0))
            except ValueError:
                pass

        analysis_id = uuid.UUID(message.analysis_id)
        with VisibilityRenewer(self.settings, message):
            try:
                outcome: Outcome = await process_analysis(
                    analysis_id,
                    settings=self.settings,
                    session_factory=self.session_factory,
                    blob=self.blob,
                    metrics=self.metrics,
                )
            except Exception as exc:
                # Transient (or unexpected infrastructure) failure: leave the
                # message; visibility expiry will redeliver, and the dequeue
                # counter above eventually poisons persistent offenders.
                logger.warning(
                    "message_left_for_redelivery",
                    analysis_id=message.analysis_id,
                    error=type(exc).__name__,
                )
                return True

        # Durable completion (succeeded, terminally failed, or skipped).
        await asyncio.to_thread(self.queue.delete, message)
        logger.info(
            "message_completed",
            analysis_id=message.analysis_id,
            status=outcome.status,
        )
        return True

    async def poll_forever(self) -> None:
        logger.info(
            "worker_polling",
            queue=self.settings.analysis_queue_name,
            interval=self.settings.queue_poll_interval_seconds,
        )
        while not self.shutdown.is_set():
            try:
                handled = await self.handle_one_message()
            except Exception as exc:
                logger.error("poll_iteration_failed", error=str(exc))
                handled = False
            if not handled:
                try:
                    await asyncio.wait_for(
                        self.shutdown.wait(),
                        timeout=self.settings.queue_poll_interval_seconds,
                    )
                except TimeoutError:
                    pass
        logger.info("worker_stopped")


async def _amain(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, service="oeop-worker")
    setup_telemetry("oeop-worker", settings)
    worker = Worker(settings)

    if settings.environment == "local":
        await asyncio.to_thread(worker.blob.ensure_container)
        await asyncio.to_thread(worker.queue.ensure_queues)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.shutdown.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX platforms
            pass

    try:
        if args.analysis_id:
            return await worker.run_direct(uuid.UUID(args.analysis_id))
        if args.once:
            handled = await worker.handle_one_message()
            logger.info("once_mode_complete", handled=handled)
            return 0
        await worker.poll_forever()
        return 0
    finally:
        await worker.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="oeop-worker", description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Handle at most one message, then exit")
    mode.add_argument("--analysis-id", help="Process this analysis directly, bypassing the queue")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
