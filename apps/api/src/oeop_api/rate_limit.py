"""Best-effort per-client submission throttling.

A fixed-window in-memory counter keyed by client IP. This is intentionally
simple and per-replica: with the small replica counts this platform runs, it
is an adequate abuse brake for a public demo, and the limitation is
documented (docs/security.md). Terminal protection is the DEMO_MODE +
submissions_enabled configuration, enforced server-side regardless.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from oeop_api.problem import ProblemException

_WINDOW_SECONDS = 3600.0


class SubmissionRateLimiter:
    def __init__(self, limit_per_hour: int) -> None:
        self.limit = limit_per_hour
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_key: str) -> None:
        now = time.monotonic()
        events = self._events[client_key]
        while events and now - events[0] > _WINDOW_SECONDS:
            events.popleft()
        if len(events) >= self.limit:
            raise ProblemException(
                status_code=429,
                title="Too many submissions",
                detail=(
                    "Submission rate limit reached for this client. "
                    "Try again later or explore the precomputed demonstration analysis."
                ),
                extra={"retry_after_seconds": int(_WINDOW_SECONDS)},
            )
        events.append(now)
        # Bound memory: drop empty/stale buckets occasionally.
        if len(self._events) > 10_000:
            stale = [k for k, v in self._events.items() if not v]
            for key in stale:
                del self._events[key]


def client_key_from_request(request: Request) -> str:
    """Client identity for throttling: X-Forwarded-For (first hop) or peer IP."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
