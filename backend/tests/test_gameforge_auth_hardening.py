from __future__ import annotations

from dataclasses import dataclass, field

import jwt
import pytest

from core.auth_security import AuthConfigurationError
from routes import gameforge_auth as auth


STRONG_SECRET = "route-test-secret-" + "s" * 48
SEED_PASSWORD = "Bootstrap-Admin-Password-2026!"


@dataclass
class FakeCollection:
    rows: list[dict] = field(default_factory=list)
    indexes: list[tuple[str, dict]] = field(default_factory=list)

    def create_index(self, field_name: str, **kwargs):
        self.indexes.append((field_name, kwargs))
        return field_name

    def find_one(self, query, projection=None):
        del projection
        email = query.get("email") if isinstance(query, dict) else None
        if email is not None:
            return next((row for row in self.rows if row.get("email") == email), None)
        token = query.get("session_token") if isinstance(query, dict) else None
        if token is not None:
            return next((row for row in self.rows if row.get("session_token") == token), None)
        return None

    def insert_one(self, row):
        self.rows.append(dict(row))
        return object()


@pytest.fixture(autouse=True)
def secure_test_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("GAMEFORGE_AUTH_ENFORCE", "0")
    monkeypatch.setenv("GAMEFORGE_JWT_SECRET", STRONG_SECRET)
    monkeypatch.delenv("GAMEFORGE_SEED_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("GAMEFORGE_SEED_ADMIN_PASSWORD", raising=False)


def test_access_token_uses_current_pyjwt_contract_and_verified_claims():
    token = auth.create_access_token(sub="operator@example.com", role="admin")
    payload = jwt.decode(
        token,
        STRONG_SECRET,
        algorithms=[auth.ALGORITHM],
        audience=auth.JWT_AUDIENCE,
        issuer=auth.JWT_ISSUER,
    )
    assert payload["sub"] == "operator@example.com"
    assert payload["role"] == "admin"
    assert payload["iss"] == auth.JWT_ISSUER
    assert payload["aud"] == auth.JWT_AUDIENCE
    assert isinstance(payload["jti"], str) and len(payload["jti"]) == 32
    assert payload["exp"] > payload["iat"]


def test_current_user_rejects_wrong_audience_before_database_identity_lookup(monkeypatch):
    sessions = FakeCollection()
    users = FakeCollection(rows=[{"email": "operator@example.com", "role": "admin"}])
    monkeypatch.setattr(auth, "_sessions", lambda: sessions)
    monkeypatch.setattr(auth, "_users", lambda: users)

    valid = auth.create_access_token(sub="operator@example.com", role="admin")
    assert auth.get_current_user(valid)["email"] == "operator@example.com"

    wrong_audience = jwt.encode(
        {
            "sub": "operator@example.com",
            "role": "admin",
            "iat": 1_800_000_000,
            "exp": 4_000_000_000,
            "iss": auth.JWT_ISSUER,
            "aud": "attacker-service",
            "jti": "bad-audience-token",
        },
        STRONG_SECRET,
        algorithm=auth.ALGORITHM,
    )
    assert auth.get_current_user(wrong_audience) is None


def test_seed_admin_is_disabled_without_explicit_bootstrap_credentials(monkeypatch):
    users = FakeCollection()
    sessions = FakeCollection()
    monkeypatch.setattr(auth, "_users", lambda: users)
    monkeypatch.setattr(auth, "_sessions", lambda: sessions)

    auth.seed_admin()

    assert users.rows == []
    assert ("email", {"unique": True}) in users.indexes
    assert ("session_token", {"unique": True}) in sessions.indexes
    assert ("expires_at", {"expireAfterSeconds": 0}) in sessions.indexes


def test_explicit_seed_admin_is_created_without_repository_default_credentials(monkeypatch):
    users = FakeCollection()
    sessions = FakeCollection()
    monkeypatch.setattr(auth, "_users", lambda: users)
    monkeypatch.setattr(auth, "_sessions", lambda: sessions)
    monkeypatch.setenv("GAMEFORGE_SEED_ADMIN_EMAIL", "bootstrap@example.com")
    monkeypatch.setenv("GAMEFORGE_SEED_ADMIN_PASSWORD", SEED_PASSWORD)

    auth.seed_admin()

    assert len(users.rows) == 1
    created = users.rows[0]
    assert created["email"] == "bootstrap@example.com"
    assert created["role"] == "admin"
    assert created["auth"] == "password"
    assert SEED_PASSWORD not in created.values()
    assert auth.verify_password(SEED_PASSWORD, created["password_hash"])


def test_production_token_minting_fails_closed_without_configured_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("GAMEFORGE_AUTH_ENFORCE", raising=False)
    monkeypatch.delenv("GAMEFORGE_JWT_SECRET", raising=False)

    with pytest.raises(AuthConfigurationError, match="required"):
        auth.create_access_token(sub="operator@example.com", role="admin")
