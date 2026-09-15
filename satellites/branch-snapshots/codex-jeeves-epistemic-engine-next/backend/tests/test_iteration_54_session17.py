"""
Iteration 54 / Session 17 — Backend tests for:
  • Segment III: apply-sentience/async (LLM SLOW — long poll allowed up to ~8 min)
  • Segment IV : apply-aesthetics/async  (already verified on d02790; re-verify /raw markers)
  • iframe-error fix (preventDefault + window.onerror in first <script>)
  • worldforge_core refactor regression (biomes/scales/region/render/quest + determinism)
"""
from __future__ import annotations
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

READY_PID = "d02790d6d8174ff59bf7005221cd7609"      # already-aesthetic'd, v12 score 100
SENTIENCE_PID = "bf9fe0f879bc400a96678186840dcdfa"  # 2nd ready game — for sentience apply

POLL_INTERVAL = 10
SENTIENCE_TIMEOUT = 8 * 60  # 8 minutes — LLM ensemble can be slow

# Module-level requests session
SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})


# ─────────────────────────── iframe-error fix ───────────────────────────
class TestIframeErrorFix:
    def test_raw_first_script_has_preventdefault_and_window_onerror(self):
        r = SESSION.get(f"{BASE_URL}/api/playable/{READY_PID}/raw", timeout=30)
        assert r.status_code == 200, r.text[:300]
        html = r.text
        # Find first <script> block
        lo = html.lower()
        s = lo.find("<script")
        e = lo.find("</script>", s)
        assert s != -1 and e != -1, "no <script> found"
        first_script = html[s:e]
        assert "preventDefault" in first_script, "preventDefault missing in first <script>"
        assert "window.onerror" in first_script, "window.onerror missing in first <script>"


# ─────────────────────────── Segment IV: aesthetics ───────────────────────────
class TestAesthetics:
    def test_raw_has_aesthetics_markers(self):
        r = SESSION.get(f"{BASE_URL}/api/playable/{READY_PID}/raw", timeout=30)
        assert r.status_code == 200
        html = r.text
        assert "window.NEURAL_FX" in html, "NEURAL_FX missing from /raw"
        assert "window.ADAPTIVE_AUDIO" in html, "ADAPTIVE_AUDIO missing from /raw"
        assert "__aesthetics" in html, "id __aesthetics missing from /raw"


# ─────────────────────────── Segment III: sentience ───────────────────────────
class TestSentience:
    def test_bad_pid_returns_not_found(self):
        r = SESSION.post(f"{BASE_URL}/api/playable/nonexistent123/apply-sentience/async", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("error") == "not found", data

    @pytest.mark.timeout(SENTIENCE_TIMEOUT + 60)
    def test_apply_sentience_end_to_end(self):
        # Pre-check raw and remember version
        pre = SESSION.get(f"{BASE_URL}/api/playable/{SENTIENCE_PID}/raw", timeout=30)
        assert pre.status_code == 200, "pre-game /raw not 200"

        kick = SESSION.post(
            f"{BASE_URL}/api/playable/{SENTIENCE_PID}/apply-sentience/async", timeout=30,
        )
        assert kick.status_code == 200, kick.text[:300]
        kd = kick.json()
        if kd.get("error") == "rate_limited":
            pytest.skip("Rate-limited — try later")
        job_id = kd.get("job_id")
        assert job_id, f"no job_id: {kd}"

        # Poll up to SENTIENCE_TIMEOUT
        start = time.time()
        result = None
        last_status = None
        while time.time() - start < SENTIENCE_TIMEOUT:
            poll = SESSION.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=30)
            if poll.status_code != 200:
                time.sleep(POLL_INTERVAL)
                continue
            j = poll.json()
            last_status = j.get("job_status")
            if last_status == "done":
                result = j.get("result") or j
                break
            time.sleep(POLL_INTERVAL)

        assert result is not None, f"job didn't finish in {SENTIENCE_TIMEOUT}s, last status={last_status}"
        applied = result.get("applied")
        score = result.get("score")
        if applied is not True:
            pytest.fail(f"sentience NOT applied. result={result}")
        assert score is not None and int(score) >= 70, f"score too low: {score} result={result}"
        assert "version" in result and int(result["version"]) >= 2

        # Verify /raw now contains the engine markers
        raw = SESSION.get(f"{BASE_URL}/api/playable/{SENTIENCE_PID}/raw", timeout=30)
        assert raw.status_code == 200
        html = raw.text
        assert "window.SENTIENCE" in html, "window.SENTIENCE missing in /raw"
        assert "__sentience" in html, "id __sentience missing in /raw"


# ─────────────────────────── Worldforge refactor regression ───────────────────────────
class TestWorldforge:
    def test_biomes(self):
        r = SESSION.get(f"{BASE_URL}/api/worldforge/biomes", timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_scales(self):
        r = SESSION.get(f"{BASE_URL}/api/worldforge/scales", timeout=30)
        assert r.status_code == 200, r.text[:200]

    def test_region(self):
        r = SESSION.get(f"{BASE_URL}/api/worldforge/region?seed=7&size=24", timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_render_region(self):
        r = SESSION.get(f"{BASE_URL}/api/worldforge/render?scale=region&seed=7&size=24", timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_render_planet_globe(self):
        r = SESSION.get(f"{BASE_URL}/api/worldforge/render?scale=planet&mode=globe&seed=7", timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_render_thematic_plates(self):
        r = SESSION.get(f"{BASE_URL}/api/worldforge/render?mode=thematic&layer=plates&seed=7&size=24", timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_quest_imports(self):
        r = SESSION.post(
            f"{BASE_URL}/api/worldforge/quest",
            json={"seed": 7, "scale": "region", "size": 24},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert "name" in d, d
        assert "quest" in d, d
        assert "consistency" in d and isinstance(d["consistency"], dict), d
        assert d["consistency"].get("ok") is True, d["consistency"]

    def test_region_determinism(self):
        r1 = SESSION.get(f"{BASE_URL}/api/worldforge/region?seed=7&size=24", timeout=60).json()
        r2 = SESSION.get(f"{BASE_URL}/api/worldforge/region?seed=7&size=24", timeout=60).json()
        # Compare a stable-ish projection (drop any nondeterministic timestamp fields)
        def proj(d):
            return {k: d.get(k) for k in sorted(d.keys()) if k not in ("at", "generated_at", "timing", "elapsed_ms")}
        assert proj(r1) == proj(r2), "non-deterministic region for same seed"
