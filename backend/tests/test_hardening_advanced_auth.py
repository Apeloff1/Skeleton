"""Security regression tests for backend hardening boundaries."""

from __future__ import annotations

from starlette.requests import Request

from middleware import hardening


def _request(
    path: str = "/api/advanced/settings",
    token: str | None = None,
    *,
    origin: str | None = None,
    host: str = "testserver",
    scheme: str = "http",
) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"host", host.encode("ascii"))]
    if token is not None:
        headers.append((b"x-codedock-admin-token", token.encode("utf-8")))
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 43210),
        "server": (host.split(":", 1)[0], 80),
    }
    return Request(scope)


def test_advanced_path_match_has_strict_namespace_boundary() -> None:
    assert hardening._is_advanced_api_path("/api/advanced")
    assert hardening._is_advanced_api_path("/api/advanced/settings")
    assert hardening._is_advanced_api_path("/api/advanced/unlock")
    assert not hardening._is_advanced_api_path("/api/advancedly")
    assert not hardening._is_advanced_api_path("/api/advance")
    assert not hardening._is_advanced_api_path("/advanced/settings")


def test_advanced_api_fails_closed_when_token_is_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv(hardening.ADVANCED_ADMIN_TOKEN_ENV, raising=False)

    response = hardening._advanced_api_auth_failure(_request())

    assert response is not None
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


def test_advanced_api_rejects_weak_configured_token(monkeypatch) -> None:
    monkeypatch.setenv(hardening.ADVANCED_ADMIN_TOKEN_ENV, "too-short")

    response = hardening._advanced_api_auth_failure(_request(token="too-short"))

    assert response is not None
    assert response.status_code == 503


def test_advanced_api_rejects_missing_or_wrong_token(monkeypatch) -> None:
    configured = "a" * hardening.MIN_ADVANCED_ADMIN_TOKEN_BYTES
    monkeypatch.setenv(hardening.ADVANCED_ADMIN_TOKEN_ENV, configured)

    missing = hardening._advanced_api_auth_failure(_request())
    wrong = hardening._advanced_api_auth_failure(_request(token="b" * 32))

    assert missing is not None and missing.status_code == 401
    assert wrong is not None and wrong.status_code == 401
    assert missing.headers["cache-control"] == "no-store"
    assert wrong.headers["cache-control"] == "no-store"


def test_advanced_api_accepts_exact_admin_token(monkeypatch) -> None:
    configured = "correct-admin-token-0123456789abcdef"
    monkeypatch.setenv(hardening.ADVANCED_ADMIN_TOKEN_ENV, configured)

    response = hardening._advanced_api_auth_failure(_request(token=configured))

    assert response is None


def test_production_cors_fails_closed_for_missing_or_wildcard_config(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    request = _request(path="/api/health", origin="https://attacker.example")

    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    missing = hardening._cors_origin_failure(request)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    wildcard = hardening._cors_origin_failure(request)

    assert missing is not None and missing.status_code == 403
    assert wildcard is not None and wildcard.status_code == 403


def test_production_cors_allows_only_explicit_cross_origin(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example,https://admin.example")

    allowed = hardening._cors_origin_failure(
        _request(path="/api/health", origin="https://app.example")
    )
    rejected = hardening._cors_origin_failure(
        _request(path="/api/health", origin="https://attacker.example")
    )

    assert allowed is None
    assert rejected is not None and rejected.status_code == 403


def test_same_origin_is_not_treated_as_cors(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    response = hardening._cors_origin_failure(
        _request(
            path="/api/health",
            origin="https://api.example:8443",
            host="api.example:8443",
            scheme="https",
        )
    )

    assert response is None


def test_development_wildcard_cors_remains_available(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    response = hardening._cors_origin_failure(
        _request(path="/api/health", origin="http://localhost")
    )

    assert response is None
