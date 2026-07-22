"""
Phase V.1 — Real Playable Export tests.

Deterministic coverage of the playability gate primitives (_extract_html,
_sanitize, _validate, _resolve_brief) + live coverage of the /list and /{id}/raw
endpoints. The full /generate path makes a large codegen LLM call and is verified
end-to-end by the testing agent; here we lock the contract that makes a returned
artifact actually runnable + offline-safe.
"""
import os

import pytest
import requests

from routes.playable import (
    _extract_html, _sanitize, _validate, PLAYABILITY_THRESHOLD,
)

_GOOD_GAME = """<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width"><style>body{margin:0}</style></head>
<body><canvas id="c"></canvas><div id="hud">Score 0</div>
<script>
const cv=document.getElementById('c');const ctx=cv.getContext('2d');
function resize(){cv.width=window.innerWidth;cv.height=window.innerHeight;}resize();
window.addEventListener('resize',resize);
window.addEventListener('touchstart',()=>{});
let over=false;
function loop(){ctx.clearRect(0,0,cv.width,cv.height);if(over){/* game over restart */}requestAnimationFrame(loop);}
loop();
</script></body></html>"""


class TestExtractHtml:
    def test_plain_doctype(self):
        assert _extract_html(_GOOD_GAME).startswith("<!DOCTYPE html")

    def test_fenced(self):
        wrapped = "```html\n" + _GOOD_GAME + "\n```"
        out = _extract_html(wrapped)
        assert out.startswith("<!DOCTYPE html") and out.rstrip().endswith("</html>")

    def test_prose_prefix(self):
        out = _extract_html("Sure! Here is your game:\n\n" + _GOOD_GAME)
        assert out.startswith("<!DOCTYPE html")

    def test_garbage(self):
        assert _extract_html("I cannot build that.") == ""

    def test_empty(self):
        assert _extract_html("") == ""


class TestSanitize:
    def test_strips_external_script(self):
        bad = '<html><script src="https://cdn.example.com/x.js"></script><canvas></canvas></html>'
        clean, removed = _sanitize(bad)
        assert "https://cdn.example.com" not in clean
        assert removed and "external <script src>" in removed

    def test_strips_external_link(self):
        bad = '<html><head><link rel="stylesheet" href="https://fonts.example.com/a.css"></head></html>'
        clean, removed = _sanitize(bad)
        assert "https://fonts.example.com" not in clean
        assert any("link" in r for r in removed)

    def test_keeps_clean(self):
        clean, removed = _sanitize(_GOOD_GAME)
        assert removed == [] and clean == _GOOD_GAME


class TestValidate:
    def test_good_game_passes_gate(self):
        v = _validate(_GOOD_GAME)
        assert v["score"] >= PLAYABILITY_THRESHOLD
        assert v["core_ok"] is True
        assert v["checks"]["has_canvas_or_render"]
        assert v["checks"]["has_game_loop"]
        assert v["checks"]["has_touch_input"]
        assert v["checks"]["self_contained"]
        # intricacy checks may be missing on a minimal fixture — that's expected
        assert all(c not in v["missing"] for c in
                   ("is_html_document", "has_canvas_or_render", "has_game_loop", "has_touch_input"))

    def test_intricacy_scored(self):
        rich = _GOOD_GAME.replace(
            "<script>",
            "<script>const ac=new AudioContext();let particles=[];let level=1;"
            "let state='menu';localStorage.getItem('hi');const dpr=window.devicePixelRatio;let dt=0;")
        v = _validate(rich)
        assert v["intricacy"] >= 5
        assert v["score"] > _validate(_GOOD_GAME)["score"]

    def test_fragment_fails(self):
        v = _validate("<div>just a fragment, no game</div>")
        assert v["score"] < PLAYABILITY_THRESHOLD
        assert v["core_ok"] is False
        assert "has_canvas_or_render" in v["missing"]
        assert "has_game_loop" in v["missing"]

    def test_cdn_dependent_not_self_contained(self):
        bad = _GOOD_GAME.replace("<script>", '<script src="https://cdn.x/phaser.js"></script><script>')
        v = _validate(bad)
        assert v["checks"]["self_contained"] is False


def _base_url() -> str:
    base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
    if not base:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    assert base
    return base


BASE_URL = _base_url()


class TestLive:
    def test_list_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/playable/list?limit=5", timeout=30)
        assert r.status_code == 200, r.text
        assert "playables" in r.json()

    def test_generate_requires_input(self):
        r = requests.post(f"{BASE_URL}/api/playable/generate", json={}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("error")

    def test_raw_404_for_unknown(self):
        r = requests.get(f"{BASE_URL}/api/playable/doesnotexist/raw", timeout=30)
        assert r.status_code == 404
        assert "text/html" in r.headers.get("content-type", "")

    def test_async_kick_returns_immediately(self):
        # The async kick must return a job_id fast (no event-loop blocking).
        import time as _t
        t0 = _t.time()
        r = requests.post(f"{BASE_URL}/api/playable/generate/async",
                          json={"brief": "tiny tap-the-dot reflex game"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("job_id") and d.get("job_status") == "running"
        assert (_t.time() - t0) < 10, "kick should return well under 10s"
        # job lookup works
        j = requests.get(f"{BASE_URL}/api/playable/job/{d['job_id']}", timeout=30)
        assert j.status_code == 200 and "job_status" in j.json()

    def test_job_unknown(self):
        r = requests.get(f"{BASE_URL}/api/playable/job/nope", timeout=30)
        assert r.status_code == 200
        assert r.json().get("job_status") == "unknown"

    def test_remix_requires_valid_base(self):
        r = requests.post(f"{BASE_URL}/api/playable/nope/remix/async",
                          json={"tweak": "make it harder"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_remix_requires_tweak(self):
        r = requests.post(f"{BASE_URL}/api/playable/anything/remix/async",
                          json={"tweak": ""}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_sequel_requires_valid_base(self):
        r = requests.post(f"{BASE_URL}/api/playable/nope/sequel/async", json={}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_competitor_requires_valid_base(self):
        r = requests.post(f"{BASE_URL}/api/playable/nope/competitor/async", json={}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_lineage_unknown(self):
        r = requests.get(f"{BASE_URL}/api/playable/nope/lineage", timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_vote_invalid_winner(self):
        r = requests.post(f"{BASE_URL}/api/playable/aaa/vote",
                          json={"opponent_id": "bbb", "winner_id": "ccc"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_vote_missing_opponent(self):
        r = requests.post(f"{BASE_URL}/api/playable/aaa/vote",
                          json={"winner_id": "aaa"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_leaderboard(self):
        r = requests.get(f"{BASE_URL}/api/playable/leaderboard?limit=5", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "leaderboard" in body
        for row in body["leaderboard"]:
            assert "rank" in row and "playable_id" in row and "score" in row

    def test_import_builds_list(self):
        r = requests.get(f"{BASE_URL}/api/playable/import/builds", timeout=30)
        assert r.status_code == 200
        assert "builds" in r.json()

    def test_import_requires_build_id(self):
        r = requests.post(f"{BASE_URL}/api/playable/import-build/async", json={}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_import_unknown_build(self):
        r = requests.post(f"{BASE_URL}/api/playable/import-build/async",
                          json={"build_id": "does-not-exist"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")

    def test_lineage_shape(self):
        # known remix child has 1 ancestor (created in earlier runs); tolerate empty
        r = requests.get(f"{BASE_URL}/api/playable/list?limit=1", timeout=30)
        items = r.json().get("playables", [])
        if not items:
            return
        pid = items[0]["playable_id"]
        lr = requests.get(f"{BASE_URL}/api/playable/{pid}/lineage", timeout=30)
        assert lr.status_code == 200
        body = lr.json()
        assert "ancestors" in body and "children" in body and "node" in body

    def test_evaluate_unknown(self):
        r = requests.post(f"{BASE_URL}/api/playable/nope/evaluate", timeout=30)
        assert r.status_code == 200
        assert r.json().get("error")


class TestExtractJson:
    def test_plain(self):
        from routes.playable import _extract_json
        assert _extract_json('{"overall": 88}')["overall"] == 88

    def test_fenced(self):
        from routes.playable import _extract_json
        assert _extract_json('```json\n{"verdict":"ship"}\n```')["verdict"] == "ship"

    def test_embedded(self):
        from routes.playable import _extract_json
        assert _extract_json('Verdict:\n{"overall": 72, "verdict":"polish"}\nend')["overall"] == 72

    def test_garbage(self):
        from routes.playable import _extract_json
        assert _extract_json("no json here") == {}
