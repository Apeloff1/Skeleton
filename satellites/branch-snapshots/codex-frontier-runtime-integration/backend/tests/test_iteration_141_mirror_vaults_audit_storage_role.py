"""Iteration 141 — Unified Vault mirror, Audit feed, Storage dashboard, Build
ledger context, and admin-only Role Management endpoints.

Exercises:
  • GET  /api/gameforge/studio/vault/unified  (route resolves; not caught by /vault/{file_id})
  • GET  /api/gameforge/studio/audit
  • GET  /api/storage/savings
  • GET  /api/storage/lazy
  • GET  /api/galaxy-studio/builds
  • POST /api/auth/set-role  (admin gated)
  • GET  /api/auth/users     (admin gated)
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL not set"
BASE_URL = BASE_URL.rstrip("/")

ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASSWORD = "GameForge#Admin2026"


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("role") == "admin"
    tok = data.get("access_token")
    assert tok
    return tok


# ── Unified Vault (mirror) ────────────────────────────────────────────────────
class TestUnifiedVault:
    def test_unified_route_resolves(self, s):
        r = s.get(f"{BASE_URL}/api/gameforge/studio/vault/unified?limit=60", timeout=20)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d.get("ok") is True, f"expected ok true, got: {d}"
        # Not caught by /vault/{file_id} which returns {ok:false,error:'not found'}
        assert "items" in d and isinstance(d["items"], list)

    def test_unified_counts_and_item_shape(self, s):
        r = s.get(f"{BASE_URL}/api/gameforge/studio/vault/unified?limit=60", timeout=20)
        d = r.json()
        counts = d.get("counts") or {}
        for k in ("boardroom", "agents", "worldforge"):
            assert k in counts, f"missing count key {k}: {counts}"
        items = d["items"]
        if items:
            it = items[0]
            for k in ("id", "name", "source", "kind"):
                assert k in it, f"item missing {k}: {it}"

    def test_boardroom_items_appear_first(self, s):
        r = s.get(f"{BASE_URL}/api/gameforge/studio/vault/unified?limit=60", timeout=20)
        d = r.json()
        items = d.get("items") or []
        counts = d.get("counts") or {}
        if counts.get("boardroom", 0) > 0 and len(items) > 0:
            # First N items where N = boardroom count should all be boardroom-sourced
            n = counts["boardroom"]
            head_sources = {i.get("source") for i in items[:n]}
            assert head_sources == {"boardroom"}, f"boardroom not first: {head_sources}"


# ── Audit feed ────────────────────────────────────────────────────────────────
class TestAudit:
    def test_audit_shape(self, s):
        r = s.get(f"{BASE_URL}/api/gameforge/studio/audit?limit=12", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("audit"), list)
        if d["audit"]:
            row = d["audit"][0]
            for k in ("action", "target", "actor", "ts"):
                assert k in row, f"audit row missing {k}: {row}"


# ── Storage dashboard ─────────────────────────────────────────────────────────
class TestStorage:
    def test_savings(self, s):
        r = s.get(f"{BASE_URL}/api/storage/savings", timeout=20)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert "saved_pct" in d
        assert "human" in d and isinstance(d["human"], dict)
        for k in ("raw", "stored", "saved"):
            assert k in d["human"], f"missing human.{k}: {d['human']}"
        assert "namespaces" in d and isinstance(d["namespaces"], list)

    def test_lazy(self, s):
        r = s.get(f"{BASE_URL}/api/storage/lazy", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # groups exist with total/loaded/deferred
        assert "core" in d and "seeds" in d
        for group in ("core", "seeds"):
            g = d[group]
            for k in ("total", "loaded", "deferred"):
                assert k in g, f"lazy group {group} missing {k}: {g}"


# ── Per-build context ledger ─────────────────────────────────────────────────
class TestBuildLedger:
    def test_builds_list(self, s):
        r = s.get(f"{BASE_URL}/api/galaxy-studio/builds?limit=20", timeout=20)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        # response may be either {builds:[...]} or list; accept both, normalise
        builds = d.get("builds") if isinstance(d, dict) else d
        assert isinstance(builds, list), f"expected list of builds: {d}"


# ── Admin RBAC: set-role + users list ─────────────────────────────────────────
class TestAdminRBAC:
    def test_set_role_no_token_401(self, s):
        r = s.post(f"{BASE_URL}/api/auth/set-role",
                   json={"email": ADMIN_EMAIL, "role": "admin"}, timeout=10)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_users_no_token_401(self, s):
        r = s.get(f"{BASE_URL}/api/auth/users", timeout=10)
        assert r.status_code == 401

    def test_set_role_admin_ok(self, s, admin_token):
        r = s.post(f"{BASE_URL}/api/auth/set-role",
                   json={"email": ADMIN_EMAIL, "role": "admin"},
                   headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d.get("ok") is True
        assert d.get("email") == ADMIN_EMAIL
        assert d.get("role") == "admin"

    def test_set_role_nonexistent_404(self, s, admin_token):
        r = s.post(f"{BASE_URL}/api/auth/set-role",
                   json={"email": "TEST_nobody_iter141@gameforge.io", "role": "editor"},
                   headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"

    def test_users_admin_ok(self, s, admin_token):
        r = s.get(f"{BASE_URL}/api/auth/users",
                  headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("users"), list)
        emails = [u.get("email") for u in d["users"]]
        assert ADMIN_EMAIL in emails, f"admin not listed: {emails[:10]}"
