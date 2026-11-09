"""
Iteration 129 — Snowball one-tap 'Ship It' verification.
Tests:
  * /api/playable/list  -> reachable, returns playables[]
  * /api/binary/package -> clean 404 (no 500) for invalid + real-playable IDs
  * /api/snowball/<id>  -> 200 for a real id from playable/list
  * /api/galaxy-studio/my-builds -> 200, returns {builds, count}
"""
import os, requests, pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def real_playable_id(session):
    r = session.get(f"{BASE_URL}/api/playable/list", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    plist = data.get("playables", [])
    assert plist, "no playables returned"
    return plist[0]["playable_id"]


class TestPlayableList:
    def test_playable_list_ok(self, session):
        r = session.get(f"{BASE_URL}/api/playable/list", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "playables" in d and isinstance(d["playables"], list)
        assert len(d["playables"]) > 0


class TestMyBuilds:
    def test_my_builds_shape(self, session):
        r = session.get(f"{BASE_URL}/api/galaxy-studio/my-builds", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "builds" in d and "count" in d
        assert isinstance(d["builds"], list)


class TestBinaryPackage:
    """The 'Ship It' backend.  We accept 200-with-artifacts OR a clean
    404 'build_id not found' — anything else (500/timeouts) is a bug."""

    def test_package_invalid_id_returns_404_not_500(self, session):
        r = session.post(
            f"{BASE_URL}/api/binary/package",
            json={"build_id": "__invalid_xyz__", "kinds": ["zip", "apk"]},
            timeout=60,
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"
        body = r.json()
        # FastAPI HTTPException → {detail: "..."}
        assert "detail" in body
        assert "build_id" in body["detail"].lower() or "not found" in body["detail"].lower()

    def test_package_real_playable_id(self, session, real_playable_id):
        """Real playable_id may not exist in galaxy_builds → expect 200 OR 404,
        never 500."""
        r = session.post(
            f"{BASE_URL}/api/binary/package",
            json={"build_id": real_playable_id, "kinds": ["zip", "apk"]},
            timeout=180,
        )
        assert r.status_code in (200, 404), f"unexpected {r.status_code}: {r.text[:300]}"
        if r.status_code == 200:
            d = r.json()
            assert d.get("build_id") == real_playable_id
            assert "artifacts" in d
            assert isinstance(d["artifacts"], list)

    def test_package_zip_only_no_500(self, session):
        r = session.post(
            f"{BASE_URL}/api/binary/package",
            json={"build_id": "__nope__", "kinds": ["zip"]},
            timeout=60,
        )
        assert r.status_code in (200, 404)


class TestSnowballEndpoint:
    def test_snowball_real_id(self, session, real_playable_id):
        r = session.get(f"{BASE_URL}/api/snowball/{real_playable_id}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # Either the snowball doc or {error:...} — must not 500
        assert isinstance(d, dict)

    def test_snowball_invalid_id_clean(self, session):
        r = session.get(f"{BASE_URL}/api/snowball/__invalid__", timeout=20)
        # Should return 200 with {error:...} OR 404 — never 500
        assert r.status_code in (200, 404)
