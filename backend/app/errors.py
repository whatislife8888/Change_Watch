"""
errors.py — one error type for the whole API, and handlers that turn every error into the same JSON:

    { "error": { "code": "interval_out_of_range", "message": "Choose an interval between ..." } }

Who uses it: route handlers raise ApiError(...); main.py registers the handlers.
Why: the frontend can show `message` directly to the user and branch on `code`, for every endpoint.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """An error we expect and want to show to the user (bad input, not found, rate limited...)."""

    def __init__(self, status: int, code: str, message: str, headers: dict | None = None, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.extra = extra or {}


def error_json(status: int, code: str, message: str, headers: dict | None = None, extra: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, **(extra or {})}}
    return JSONResponse(body, status_code=status, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so every error response has the same shape."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_json(exc.status, exc.code, exc.message, exc.headers, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Turn Pydantic's detailed list into one readable sentence for the first problem.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = first.get("msg", "Invalid input")
        return error_json(422, "invalid_input", f"{field}: {message}" if field else message)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {401: "not_logged_in", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        return error_json(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))
