"""Public HTTP error helpers — never stringify caught exceptions into responses."""
from __future__ import annotations

import logging
import math
import re
from inspect import isawaitable
from itertools import islice
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("codedock.http_errors")

PUBLIC_INTERNAL_ERROR = "internal server error"
REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "credential",
    "credentials",
    "session",
    "session_token",
    "session_key",
    "client_key",
    "private_key",
    "x_api_key",
    "api_secret",
    "id_token",
    "jwt",
    "bearer",
}

_AUTHORIZATION_RE = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*(?:(?:basic|bearer)\s+)?[^\s,;]+"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password)"
    r"\b\s*[:=]\s*([^\s,;&#}]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:token|access[-_]?token|refresh[-_]?token|session|"
    r"api[-_]?key|secret|password|code|client[-_]?secret)=)[^&#\s]+"
)
_JSON_SECRET_RE = re.compile(
    r'(?i)"(?:token|password|secret|authorization|api[_-]?key|'
    r'access[_-]?token|refresh[_-]?token)"\s*:\s*"[^"\r\n]*"'
)
_MAX_REDACTED_TEXT = 16_384


def redact_client_text(value: str, *, max_len: int = 2000) -> str:
    """Bound before pattern matching, including JSON and URL credential forms.

    Inputs may contain hostile network error bodies or exception traces. Never
    regex-scan unbounded text, and never serialize unknown objects to text.
    """
    if not isinstance(value, str):
        return "[UNSUPPORTED]"
    if type(max_len) is not int or not 0 <= max_len <= _MAX_REDACTED_TEXT:
        raise ValueError("redaction character budget exceeds maximum")
    # Include a bounded lookahead to redact credentials crossing the output
    # boundary; processing is capped even for gigabyte-sized exceptions.
    text = value[:max_len + 256]
    text = _AUTHORIZATION_RE.sub(f"authorization={REDACTED}", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}", text
    )
    text = _QUERY_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED}", text
    )
    text = _JSON_SECRET_RE.sub(REDACTED, text)
    # Do not split the redaction marker at the output budget: that can
    # turn an otherwise redacted value into a misleading partial token.
    result = text[:max_len]
    if result.endswith("[REDACT"):
        result = result[:-7]
    return result


def redact_client_payload(value: Any, *, depth: int = 0, max_depth: int = 4) -> Any:
    """Never run arbitrary object repr/getters or allocate unbounded key lists."""
    if depth >= max_depth:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return redact_client_text(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in islice(value.items(), 50):
            if not isinstance(key, str) or key in {"__proto__", "prototype", "constructor"}:
                continue
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS:
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_client_payload(
                    child, depth=depth + 1, max_depth=max_depth
                )
        return redacted
    if isinstance(value, (list, tuple)):
        return [
            redact_client_payload(child, depth=depth + 1, max_depth=max_depth)
            for child in islice(value, 50)
        ]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if not isinstance(value, float) or math.isfinite(value) else None
    return "[UNSUPPORTED]"


# This closed catalogue contains no exception text, provider output, or
# caller-controlled messages. The HTTP boundary recognizes only these typed
# constructors, not ordinary JSON bodies that happen to contain a known code.
_UNAVAILABLE_MESSAGES = {
    "marketplace_release_unavailable": "Selling and purchasing games is unavailable until gameplay and buyer access can be verified.",
    "premium_release_unavailable": "Premium checkout is unavailable until payment and entitlement delivery can be verified.",
}
_WEBHOOK_UNAVAILABLE = frozenset({"payment_details_unreconciled", "webhook_unavailable"})
_MODEL_FAILURE_CODES = frozenset({
    "project_model_transfer_denied", "project_model_context_unavailable",
    "project_model_execution_failed", "project_model_execution_unconfirmed",
    "project_model_configuration_unavailable", "project_model_generation_failed",
})
_PUBLIC_ENGINE_KEY = re.compile(r"engine-chat:[0-9a-f]{64}\Z")


def _unavailable_payload(code: str, request_key: str | None = None) -> dict[str, Any]:
    if type(code) is not str:
        return {"detail": PUBLIC_INTERNAL_ERROR}
    if code in _UNAVAILABLE_MESSAGES:
        return {"code": code, "error": _UNAVAILABLE_MESSAGES[code]}
    if code in _WEBHOOK_UNAVAILABLE:
        return {"received": False, "error": code}
    if code == "artifact_owner_unavailable":
        return {"detail": {
            "code": code,
            "message": "Governed GameForge export is unavailable. Use the Studio project source export.",
            "action": "Use the existing Studio project source export until governed artifact delivery is connected.",
        }}
    if code in _MODEL_FAILURE_CODES:
        uncertain = code == "project_model_execution_unconfirmed"
        key = (
            request_key
            if uncertain and type(request_key) is str and len(request_key) == 76
            and _PUBLIC_ENGINE_KEY.fullmatch(request_key)
            else None
        )
        return {"detail": {
            "error": ("Model execution could not be confirmed; retain this job."
                      if uncertain else "Model generation is unavailable for this project."),
            "error_code": code,
            "retry_same_request": uncertain,
            "engine_request_key": key,
        }}
    return {"detail": PUBLIC_INTERNAL_ERROR}


class PublicUnavailableResponse(JSONResponse):
    """A server-owned, closed-catalogue 503 response; no arbitrary envelope."""

    def __init__(self, code: str, *, request_key: str | None = None) -> None:
        self.public_code = code
        self.public_request_key = request_key
        super().__init__(status_code=503, content=_unavailable_payload(code, request_key),
                         headers={"Cache-Control": "no-store"})

    def sanitized(self) -> JSONResponse:
        return PublicUnavailableResponse(self.public_code, request_key=self.public_request_key)


class PublicUnavailableError(HTTPException):
    """Typed 503 for first-party service admission; never forwards headers."""

    def __init__(self, code: str, *, request_key: str | None = None) -> None:
        self.public_code = code
        self.public_request_key = request_key
        super().__init__(status_code=503, detail=PUBLIC_INTERNAL_ERROR)

    def sanitized(self) -> JSONResponse:
        return PublicUnavailableResponse(self.public_code, request_key=self.public_request_key)


_HEALTH_CHECKS = frozenset({
    "mongo", "ai_provider", "vault_galaxy", "vault_builds", "critical_routes",
    "uptime_ok", "feature_flags_loaded", "vault_module", "galaxy_vault",
    "build_vault", "disk_pressure", "vault",
})
_HEALTH_ERRORS = frozenset({
    "probe_failed", "probe_timeout_or_unavailable", "registry_probe_failed",
})
_HEALTH_NUMBERS = frozenset({"latency_ms_lt", "free_pct", "count", "zips",
                             "builds", "uptime_seconds"})


def _public_health_payload(observation: Any) -> dict[str, Any]:
    """Project only known health fields; never emit paths or diagnostic text."""
    if type(observation) is not dict:
        return {"status": "degraded", "checks": {}}
    status = observation.get("status")
    body: dict[str, Any] = {
        "status": status if type(status) is str and status in
        {"not_ready", "starting", "degraded"} else "degraded",
        "checks": {},
    }
    checks = observation.get("checks")
    if type(checks) is dict:
        for name in sorted(_HEALTH_CHECKS):
            item = checks.get(name)
            if type(item) is not dict:
                continue
            check: dict[str, Any] = {"ok": item.get("ok") is True}
            error = item.get("error")
            if type(error) is str and error in _HEALTH_ERRORS:
                check["error"] = error
            for key in _HEALTH_NUMBERS:
                value = item.get(key)
                if ((type(value) is int and 0 <= value <= 10**12)
                        or (type(value) is float and math.isfinite(value)
                            and 0 <= value <= 10**12)):
                    check[key] = value
            if type(item.get("report_available")) is bool:
                check["report_available"] = item["report_available"]
            body["checks"][name] = check
    identity = observation.get("canonical_application")
    if type(identity) is dict:
        version = identity.get("version")
        if (identity.get("name") == "Skeleton" and identity.get("component") == "backend"
                and identity.get("ingress_prefix") == "/api"
                and type(version) is str and len(version) <= 40
                and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version)):
            body["canonical_application"] = {
                "name": "Skeleton", "version": version,
                "component": "backend", "ingress_prefix": "/api",
            }
    return body


class PublicHealthUnavailable(JSONResponse):
    """An explicitly typed health observation rather than a generic 5xx."""

    def __init__(self, observation: Any) -> None:
        self.public_observation = _public_health_payload(observation)
        super().__init__(status_code=503, content=self.public_observation,
                         headers={"Cache-Control": "no-store"})

    def sanitized(self) -> JSONResponse:
        return PublicHealthUnavailable(self.public_observation)


def public_http_error(
    status_code: int,
    public_detail: str,
    exc: BaseException | None = None,
) -> HTTPException:
    """Stable public HTTP error. Logs the exception type, never the text."""
    if exc is not None:
        log.warning(
            "public failure %s (%s): %s", status_code, public_detail, type(exc).__name__
        )
    return HTTPException(status_code=status_code, detail=public_detail)


def internal_http_error(public_detail: str, exc: BaseException | None = None) -> HTTPException:
    """Stable 500 for caught failures. Logs the exception type, never the text."""
    return public_http_error(500, public_detail, exc)


PROBLEM_JSON = "application/problem+json"
_PROBLEM_TITLES = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 409: "Conflict", 410: "Gone", 413: "Content Too Large",
    415: "Unsupported Media Type", 422: "Unprocessable Content", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable",
    504: "Gateway Timeout",
}


def wants_problem_json(request: Any) -> bool:
    """RFC 9457 content negotiation: opt-in through the Accept header.

    Existing clients keep the historical ``{"detail": ...}`` body; callers
    that ask for ``application/problem+json`` get the standard shape (which
    still carries ``detail``), so both representations stay compatible.
    """
    try:
        accept = request.headers.get("accept", "")
    except Exception:
        return False
    if type(accept) is not str or len(accept) > 1024:
        return False
    return PROBLEM_JSON in accept.lower()


def problem_document(
    status: int,
    detail: Any,
    *,
    instance: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Build an RFC 9457 problem object with only public, bounded fields."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _PROBLEM_TITLES.get(status, "Error"),
        "status": status,
    }
    if type(detail) is str:
        body["detail"] = redact_client_text(detail, max_len=512)
    elif type(detail) is list:
        # FastAPI validation errors: keep the structured list as an extension.
        body["detail"] = "request validation failed"
        body["errors"] = redact_client_payload(detail)
    elif detail is not None:
        body["detail"] = _PROBLEM_TITLES.get(status, "Error").lower()
    if instance and type(instance) is str and len(instance) <= 512:
        body["instance"] = instance
    if request_id and type(request_id) is str and len(request_id) <= 128:
        body["request_id"] = request_id
    if trace_id and type(trace_id) is str and re.fullmatch(r"[0-9a-f]{32}", trace_id):
        body["trace_id"] = trace_id
    return body


def _request_identity(request: Any) -> tuple[str | None, str | None, str | None]:
    try:
        state = request.state
        rid = getattr(state, "request_id", None)
        trace_id = getattr(state, "trace_id", None)
        instance = request.url.path
    except Exception:
        return None, None, None
    return instance, rid, trace_id


def as_problem_response(request: Any, response: Any) -> Any:
    """Re-render a JSON error response as problem+json when negotiated."""
    if not wants_problem_json(request) or not isinstance(response, JSONResponse):
        return response
    status = response.status_code
    if status < 400:
        return response
    try:
        import json as _json

        payload = _json.loads(bytes(response.body))
    except Exception:
        payload = None
    detail = payload.get("detail") if type(payload) is dict else None
    instance, rid, trace_id = _request_identity(request)
    body = problem_document(
        status, detail, instance=instance, request_id=rid, trace_id=trace_id
    )
    if type(payload) is dict:
        code = payload.get("code")
        if type(code) is str and len(code) <= 80:
            body["code"] = code
    headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in {"content-length", "content-type"}
    }
    return JSONResponse(
        status_code=status, content=body, headers=headers, media_type=PROBLEM_JSON
    )


def install_public_error_handlers(app: FastAPI) -> None:
    """Register fail-closed handlers for explicit 5xx and unhandled failures.

    Starlette considers HTTPException a handled exception, not an unexpected
    failure. Protecting only Exception leaves explicit 500/502/503 route
    details and their headers untouched. Preserve the registered 4xx handler.
    Every handler honours RFC 9457 ``application/problem+json`` negotiation.
    """
    previous_http_handler = app.exception_handlers.get(
        StarletteHTTPException, http_exception_handler
    )

    @app.exception_handler(StarletteHTTPException)
    async def public_http_exception_handler(
        request: Any, exc: StarletteHTTPException
    ) -> Any:
        if type(exc) is PublicUnavailableError:
            return as_problem_response(request, exc.sanitized())
        if exc.status_code < 500:
            result = previous_http_handler(request, exc)
            result = await result if isawaitable(result) else result
            return as_problem_response(request, result)
        # Do not include the public path, arbitrary detail, or upstream
        # headers; all of these may contain network/provider credentials.
        log.warning("server HTTP failure (%s)", exc.status_code)
        return as_problem_response(request, JSONResponse(
            status_code=exc.status_code,
            content={"detail": PUBLIC_INTERNAL_ERROR},
            headers={"Cache-Control": "no-store"},
        ))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Any, exc: Exception) -> JSONResponse:
        log.warning("unhandled exception: %s", type(exc).__name__)
        return as_problem_response(request, JSONResponse(
            status_code=500,
            content={"detail": PUBLIC_INTERNAL_ERROR},
            headers={"Cache-Control": "no-store"},
        ))

    try:
        from fastapi.exceptions import RequestValidationError
        from fastapi.exception_handlers import request_validation_exception_handler
    except Exception:  # pragma: no cover - FastAPI always ships these
        return
    previous_validation_handler = app.exception_handlers.get(
        RequestValidationError, request_validation_exception_handler
    )

    @app.exception_handler(RequestValidationError)
    async def problem_validation_handler(request: Any, exc: Any) -> Any:
        result = previous_validation_handler(request, exc)
        result = await result if isawaitable(result) else result
        return as_problem_response(request, result)
