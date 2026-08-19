"""Standard response envelope used by every endpoint."""

from datetime import datetime, timezone

from fastapi.responses import JSONResponse


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def ok(data=None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "error": None,
            "timestamp": _timestamp(),
        },
    )


def fail(error: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": error,
            "timestamp": _timestamp(),
        },
    )
