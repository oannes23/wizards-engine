"""Response helper functions for consistent error envelopes.

Every error returned by the API passes through one of these helpers so
that the ``{"error": {"code": ..., "message": ..., "details": ...}}``
shape is applied uniformly regardless of which route raises the error.
"""

from fastapi.responses import JSONResponse


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    """Build a JSON error response using the standard error envelope.

    Parameters
    ----------
    status_code:
        HTTP status code to send (e.g. ``404``, ``409``).
    code:
        Machine-readable error identifier (e.g. ``"not_found"``).
    message:
        Human-readable description of the error.
    details:
        Optional mapping of additional context to include under
        ``error.details``.

    Returns
    -------
    JSONResponse
        ``{"error": {"code": ..., "message": ..., "details": ...}}``
    """
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def validation_error_response(fields: dict) -> JSONResponse:
    """Build a 422 Unprocessable Entity response for field-level validation errors.

    Parameters
    ----------
    fields:
        Mapping of field names to error messages, e.g.
        ``{"name": "must not be empty", "limit": "must be >= 1"}``.

    Returns
    -------
    JSONResponse
        ``{"error": {"code": "validation_error", "message": "Validation failed",
        "details": {"fields": {...}}}}`` with status 422.
    """
    return error_response(
        status_code=422,
        code="validation_error",
        message="Validation failed",
        details={"fields": fields},
    )
