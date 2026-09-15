"""Regression tests for the privileged /api/advanced authentication boundary."""

from __future__ import annotations

from starlette.requests import Request

from middleware import hardening


def _request(path: str = "/api/advanced/settings", token: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"x-codedock-admin-token", token.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 43210),
        "server": ("testserver", 80),
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
