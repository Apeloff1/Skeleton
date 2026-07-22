"""
Iteration 139 — Ship It + Native Engine builds (PyInstaller + Godot) + Audit log
+ RBAC/JWT regression + build/runtime/vault regression.
"""
import io
import os
import zipfile
import time
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") \
    else "https://player-retention.preview.emergentagent.com"

ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PW = "GameForge#Admin2026"
GAME = "Studio"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    role = r.json().get("role")
    assert tok and role == "admin"
    return tok


# ── Toolchains
def test_toolchains(api):
    r = api.get(f"{BASE_URL}/api/gameforge/build/toolchains", timeout=30)
    assert r.status_code == 200
    tc = r.json().get("toolchains") or {}
    assert tc.get("desktop_pyinstaller") is True
    assert tc.get("godot_project") is True
    assert tc.get("web") is True
    assert tc.get("source_zip") is True


# ── Native desktop build via PyInstaller (slow)
def test_desktop_build_pyinstaller(api):
    r = api.post(f"{BASE_URL}/api/gameforge/build/desktop", json={"game_name": GAME}, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True, d
    assert d.get("platform") == "linux-x86_64"
    assert isinstance(d.get("binary_bytes"), int) and d["binary_bytes"] > 100000, d
    assert d.get("download_url", "").startswith("/api/gameforge/build/download/")
    dl = requests.get(f"{BASE_URL}{d['download_url']}", timeout=60)
    assert dl.status_code == 200
    assert "application/zip" in (dl.headers.get("content-type") or "")
    assert dl.content[:2] == b"PK"


# ── Godot importable project
def test_godot_project_build(api):
    r = api.post(f"{BASE_URL}/api/gameforge/build/godot", json={"game_name": GAME}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("importable_godot_project") is True
    assert d.get("download_url", "").startswith("/api/gameforge/build/download/")
    dl = requests.get(f"{BASE_URL}{d['download_url']}", timeout=60)
    assert dl.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(dl.content))
    names = set(z.namelist())
    for f in ("project.godot", "main.gd", "main.tscn"):
        assert f in names, f"{f} missing from Godot zip: {names}"


# ── Web + source still work
def test_web_and_source_builds(api):
    for kind in ("web", "source"):
        r = api.post(f"{BASE_URL}/api/gameforge/build/{kind}", json={"game_name": GAME}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("sha256") and len(d["sha256"]) == 64
        assert d.get("download_url", "").startswith("/api/gameforge/build/download/")


def test_build_list(api):
    r = api.get(f"{BASE_URL}/api/gameforge/build/list", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    assert isinstance(d.get("builds"), list) and len(d["builds"]) >= 1


# ── Ship It
def test_ship_it(api):
    r = api.post(f"{BASE_URL}/api/gameforge/studio/ship", json={"game_name": GAME, "push": True}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    steps = d.get("steps") or []
    for step in ("web_build", "source_build", "git_commit", "git_push"):
        assert step in steps, f"step {step} missing in {steps}"
    assert (d.get("web_build") or {}).get("ok") is True
    assert (d.get("source_build") or {}).get("ok") is True
    assert d.get("git_committed") is True, d
    assert d.get("pushed") is False
    assert "GITHUB_REMOTE" in (d.get("push_note") or "")
    assert "GITHUB_TOKEN" in (d.get("push_note") or "")


# ── Audit log
def test_audit_log_ship_and_deploy(api):
    # Trigger an additional ship + deploy
    api.post(f"{BASE_URL}/api/gameforge/studio/ship", json={"game_name": GAME, "push": False}, timeout=90)
    api.post(f"{BASE_URL}/api/gameforge/studio/deploy", json={"game_name": GAME}, timeout=60)
    time.sleep(0.5)
    r = api.get(f"{BASE_URL}/api/gameforge/studio/audit?limit=100", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    actions = [e.get("action") for e in (d.get("audit") or [])]
    assert "ship" in actions
    assert "deploy" in actions


# ── Auth flow
def test_auth_login_me_and_vault_put(api, admin_token):
    me = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert me.status_code == 200
    mj = me.json()
    assert mj.get("enforced") is False
    r = api.post(f"{BASE_URL}/api/gameforge/studio/vault/put",
                 headers={"Authorization": f"Bearer {admin_token}"},
                 json={"filename": "TEST_iter139.txt", "content": "hello-139", "metadata": {"kind": "test"}},
                 timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    assert r.json().get("file_id")


# ── Regression
def test_activate_and_map(api):
    r = api.post(f"{BASE_URL}/api/gameforge/activate", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d.get("activated") == d.get("total") == 4
    r2 = api.get(f"{BASE_URL}/api/gameforge/map/systems", timeout=30)
    assert r2.status_code == 200
    m = r2.json()
    assert m.get("total") == 19
    assert len(m.get("systems") or []) == 19
