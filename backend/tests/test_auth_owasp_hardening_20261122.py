"""OWASP A02/A07 hardening of /api/auth against a real MongoDB (``MONGO_URL``)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MONGO_URL = os.environ.get("MONGO_URL", "").strip()
pytestmark = pytest.mark.skipif(not MONGO_URL, reason="MONGO_URL not set; auth storage needs a real mongod")

RAW_TOKEN = "provider-session-" + "x" * 32


@pytest.fixture()
def auth(monkeypatch: pytest.MonkeyPatch):
    import pymongo

    from routes import gameforge_auth as g

    client: pymongo.MongoClient[dict[str, Any]] = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client[f"laneb_auth_{uuid.uuid4().hex[:10]}"]
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("GAMEFORGE_AUTH_ENFORCE", "false")
    monkeypatch.setattr(g, "_users", lambda: db["gameforge_users"])
    monkeypatch.setattr(g, "_sessions", lambda: db["user_sessions"])
    monkeypatch.setattr(g, "_seed_initialized", False)
    g.seed_admin()

    provider: dict[str, Any] = {"status": 200, "json": {"email": "Player@Example.com", "session_token": RAW_TOKEN}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(provider["status"], json=provider["json"])

    real_client = httpx.AsyncClient

    class ProviderClient(real_client):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", ProviderClient)
    app = FastAPI()
    app.include_router(g.router)
    try:
        yield g, db, TestClient(app), provider
    finally:
        client.drop_database(db.name)
        client.close()


def _me(http: TestClient, token: str) -> dict[str, Any]:
    return http.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()


def test_register_rejects_passwords_bcrypt_would_truncate(auth):
    _, _, http, _ = auth
    too_long = "p" * 73
    assert http.post("/api/auth/register", json={"email": "a@example.com", "password": too_long}).status_code == 422
    multibyte = "é" * 37  # 74 bytes in UTF-8
    assert http.post("/api/auth/register", json={"email": "b@example.com", "password": multibyte}).status_code == 422
    ok = http.post("/api/auth/register", json={"email": "c@example.com", "password": "p" * 72})
    assert ok.status_code == 200
    assert _me(http, ok.json()["access_token"])["authenticated"] is True


def test_login_input_is_bounded(auth):
    _, _, http, _ = auth
    response = http.post("/api/auth/login", json={"email": "a@example.com", "password": "x" * 1025})
    assert response.status_code == 422


def test_jwt_without_required_claims_is_rejected(auth):
    g, db, http, _ = auth
    db["gameforge_users"].insert_one({"email": "ed@example.com", "role": "editor", "disabled": False})
    now = datetime.now(timezone.utc)
    full = {
        "sub": "ed@example.com",
        "role": "editor",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    assert _me(http, jwt.encode(full, g._secret(), algorithm="HS256"))["authenticated"] is True
    for missing in ("exp", "iat", "sub"):
        claims = {k: v for k, v in full.items() if k != missing}
        assert _me(http, jwt.encode(claims, g._secret(), algorithm="HS256"))["authenticated"] is False
    forged = jwt.encode(full, "x" * 48, algorithm="HS256")
    assert _me(http, forged)["authenticated"] is False


def test_session_tokens_are_stored_hashed_and_hash_is_not_a_bearer(auth):
    g, db, http, _ = auth
    response = http.post("/api/auth/session", json={"session_id": "sid"})
    assert response.status_code == 200 and response.json()["access_token"] == RAW_TOKEN
    rows = list(db["user_sessions"].find({}))
    assert len(rows) == 1
    stored = rows[0]["session_token"]
    assert stored == g._session_key(RAW_TOKEN) and RAW_TOKEN not in str(rows[0])
    assert _me(http, RAW_TOKEN)["user"]["email"] == "player@example.com"
    assert _me(http, stored)["authenticated"] is False  # a leaked DB row is not a credential
    # Re-login with the same provider token reuses the row.
    http.post("/api/auth/session", json={"session_id": "sid"})
    assert db["user_sessions"].count_documents({}) == 1
    assert http.post("/api/auth/logout", headers={"Authorization": f"Bearer {RAW_TOKEN}"}).json() == {"ok": True}
    assert db["user_sessions"].count_documents({}) == 0
    assert _me(http, RAW_TOKEN)["authenticated"] is False


def test_legacy_plaintext_session_still_works_and_is_migrated(auth):
    g, db, http, _ = auth
    db["gameforge_users"].insert_one({"email": "old@example.com", "role": "viewer", "disabled": False})
    legacy = "legacy-session-" + "y" * 30
    db["user_sessions"].insert_one(
        {
            "session_token": legacy,
            "email": "old@example.com",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        }
    )
    assert _me(http, legacy)["authenticated"] is True
    assert db["user_sessions"].find_one({})["session_token"] == g._session_key(legacy)
    assert _me(http, legacy)["authenticated"] is True


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "a", "dict"],
        {"email": "p@example.com", "session_token": 12345678901234567},
        {"email": "p@example.com", "session_token": "short"},
        {"email": ["p@example.com"], "session_token": RAW_TOKEN},
        {"email": "no-at-sign", "session_token": RAW_TOKEN},
        {"email": "p@example.com", "session_token": "sha256:" + "0" * 64},
    ],
)
def test_malformed_provider_responses_are_rejected(auth, payload):
    _, db, http, provider = auth
    provider["json"] = payload
    response = http.post("/api/auth/session", json={"session_id": "sid"})
    assert response.status_code == 401
    assert db["user_sessions"].count_documents({}) == 0


def test_oversized_bearer_is_ignored(auth):
    _, _, http, _ = auth
    assert _me(http, "z" * 5000)["authenticated"] is False
