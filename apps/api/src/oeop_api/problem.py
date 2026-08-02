"""RFC 7807 problem-details responses and exception handlers.

Internal exception details never reach clients: unexpected errors are logged
server-side with a correlation id and returned as an opaque problem document
referencing that id.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from earth_observation.errors import DataError, UserInputError
from oeop_core.logging import get_logger

logger = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
_TYPE_BASE = (
    "https://github.com/raveheart1/Orbital-Earth-Observation-Platform/blob/main/docs/api-errors.md"
)


class ProblemException(Exception):
    """Raise anywhere in the API to return a structured problem document."""

    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        problem_type: str = "about:blank",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.problem_type = problem_type
        self.extra = extra or {}


def problem_response(
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    problem_type: str = "about:blank",
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status_code, media_type=PROBLEM_CONTENT_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemException)
    async def handle_problem(request: Request, exc: ProblemException) -> JSONResponse:
        return problem_response(
            request, exc.status_code, exc.title, exc.detail, exc.problem_type, exc.extra
        )

    @app.exception_handler(UserInputError)
    async def handle_user_input(request: Request, exc: UserInputError) -> JSONResponse:
        return problem_response(
            request,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid analysis request",
            str(exc),
            f"{_TYPE_BASE}#invalid-request",
        )

    @app.exception_handler(DataError)
    async def handle_data_error(request: Request, exc: DataError) -> JSONResponse:
        return problem_response(
            request,
            status.HTTP_409_CONFLICT,
            "Upstream data cannot satisfy the request",
            str(exc),
            f"{_TYPE_BASE}#data-error",
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": ".".join(str(part) for part in err.get("loc", [])),
                "message": err.get("msg", "invalid"),
            }
            for err in exc.errors()
        ]
        return problem_response(
            request,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Request validation failed",
            "One or more request fields are invalid.",
            f"{_TYPE_BASE}#validation",
            extra={"errors": errors},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = str(uuid.uuid4())
        logger.error(
            "unhandled_exception",
            correlation_id=correlation_id,
            path=str(request.url.path),
            exc_info=exc,
        )
        return problem_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal server error",
            f"An unexpected error occurred. Reference: {correlation_id}",
            f"{_TYPE_BASE}#internal",
        )
