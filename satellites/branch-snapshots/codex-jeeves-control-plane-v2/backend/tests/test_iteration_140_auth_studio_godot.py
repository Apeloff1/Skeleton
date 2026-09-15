"""Iteration 140 — Auth (JWT + Google session) + RBAC enforcement + Godot native engine.

Covers all backend items from the review request:
  • /api/auth/login (admin)
  • /api/auth/register (new user)
  • /api/auth/me (enforced flag, authenticated with/without bearer)
  • /api/auth/session (bogus session_id -> 401)
  • /api/auth/logout
  • RBAC on /api/gameforge/studio/vault/put (401 w/o token, allowed with admin)
  • /api/gameforge/build/godot -> engine_validated + engine 4.3.stable + importable
  • /api/gameforge/build/toolchains -> godot_engine + godot_headless_export true
  • /api/gameforge/build/download/{id} for a godot build -> zip 200
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("EXPO_PUBLIC_BACKEND_URL not set", allow_module_level=True)


ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASS = "GameForge#Admin2026"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("access_token"), data
    assert data.get("role") == "admin", data
    return data["access_token"]


# ---------- Auth flows ----------
class TestAuth:
    def test_login_admin_returns_jwt_and_admin_role(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("access_token") and d.get("role") == "admin"
        # JWTs are 3 dot-separated base64 segments
        assert d["access_token"].count(".") == 2, "access_token should look like a JWT (HS256)"

    def test_register_new_user_returns_viewer_token(self, s):
        email = f"testuser_{uuid.uuid4().hex[:10]}@gameforge.io"
        r = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "TestPass!2026"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("access_token") and d.get("role") == "viewer"

    def test_me_without_token_shows_enforced_true_unauth(self, s):
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("enforced") is True, f"expected enforced=true, got {d}"
        assert d.get("authenticated") is False

    def test_me_with_admin_token_authenticated_admin(self, s, admin_token):
        r = s.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("authenticated") is True
        assert d.get("enforced") is True
        assert (d.get("user") or {}).get("role") == "admin"

    def test_session_bogus_returns_401(self, s):
        r = s.post(f"{BASE_URL}/api/auth/session", json={"session_id": "bogus-" + uuid.uuid4().hex}, timeout=30)
        assert r.status_code == 401, f"expected 401 for bogus session, got {r.status_code} {r.text[:200]}"
        assert "Invalid" in (r.json().get("detail") or "") or "expired" in (r.json().get("detail") or "")

    def test_logout_returns_ok(self, s, admin_token):
        # logout with a JWT should still return ok (JWTs are stateless client-drop)
        r = s.post(f"{BASE_URL}/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------- RBAC enforcement on vault ----------
class TestRBAC:
    def test_vault_put_without_token_401(self, s):
        r = s.post(f"{BASE_URL}/api/gameforge/studio/vault/put",
                   json={"filename": "TEST_iter140_noauth.txt", "content": "x", "game_name": "Studio"}, timeout=20)
        assert r.status_code == 401, f"expected 401 for unauth vault/put, got {r.status_code} {r.text[:200]}"

    def test_vault_put_with_admin_token_authorized(self, s, admin_token):
        r = s.post(f"{BASE_URL}/api/gameforge/studio/vault/put",
                   headers={"Authorization": f"Bearer {admin_token}"},
                   json={"filename": f"TEST_iter140_{uuid.uuid4().hex[:6]}.txt",
                         "content": "iteration 140 rbac test", "game_name": "Studio"}, timeout=30)
        assert r.status_code not in (401, 403), f"admin should be authorized, got {r.status_code} {r.text[:200]}"


# ---------- Godot native engine build ----------
class TestGodotBuild:
    def test_toolchains_shows_godot_engine(self, s):
        r = s.get(f"{BASE_URL}/api/gameforge/build/toolchains", timeout=20)
        assert r.status_code == 200
        tc = (r.json() or {}).get("toolchains") or {}
        assert tc.get("godot_engine") is True, f"godot_engine should be true, got {tc}"
        assert tc.get("godot_headless_export") is True, f"godot_headless_export should be true, got {tc}"
        assert tc.get("godot_project") is True

    def test_build_godot_validates_engine(self, s):
        r = s.post(f"{BASE_URL}/api/gameforge/build/godot", json={"game_name": "Studio"}, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("importable_godot_project") is True, d
        assert d.get("engine_validated") is True, f"engine_validated must be true, got {d}"
        ver = d.get("engine_version") or ""
        assert ver.startswith("4.3.stable"), f"engine_version must start with 4.3.stable, got {ver!r}"
        # stash for download test
        pytest.godot_build_id = d.get("build_id")

    def test_download_godot_zip(self, s):
        bid = getattr(pytest, "godot_build_id", None)
        assert bid, "no godot build id from previous test"
        r = s.get(f"{BASE_URL}/api/gameforge/build/download/{bid}", timeout=60)
        assert r.status_code == 200, r.text[:200]
        # ZIP magic bytes
        assert r.content[:2] == b"PK", "download should be a real zip"
        assert len(r.content) > 200


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
