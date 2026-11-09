"""Iteration 151: Jeeves free-tier cascade + multi-format composer + chat + idle_augment."""
import base64
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
TIMEOUT = 60


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _min_pdf_b64() -> str:
    """Minimal valid PDF as base64."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import LETTER
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=LETTER)
        c.setTitle("Test Doc")
        c.drawString(72, 720, "Hello Jeeves multimodal PDF.")
        c.showPage()
        c.save()
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # Fallback: minimal PDF header bytes (may not parse but non-empty)
        return base64.b64encode(b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF").decode()


# ── COMPOSE ────────────────────────────────────────────────────
class TestCompose:
    def test_compose_all_forms_single_parse(self, api):
        r = api.post(f"{BASE_URL}/api/jeeves/compose",
                     json={"query": "summarize legion readiness",
                           "forms": ["text", "pdf", "spreadsheet", "charts", "graph", "visual"]},
                     timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["tier"] in ("local", "free", "paid")
        assert d["text"] and isinstance(d["text"], str)
        assert d["artifact_count"] >= 8, f"expected >=8, got {d['artifact_count']}"
        types = [a.get("type") for a in d["artifacts"]]
        # 4 chart variations + graph + visual + spreadsheet + pdf = 8
        assert types.count("chart") == 4
        assert "graph" in types and "visual" in types
        assert "spreadsheet" in types and "pdf" in types
        # every artifact has type/mime/base64 non-empty
        for a in d["artifacts"]:
            assert a["type"] and a.get("mime") and a.get("base64")
            assert len(a["base64"]) > 100

    def test_compose_subset_charts_only(self, api):
        r = api.post(f"{BASE_URL}/api/jeeves/compose",
                     json={"query": "chart competency", "forms": ["charts"]},
                     timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        types = [a["type"] for a in d["artifacts"]]
        kinds = [a.get("kind") for a in d["artifacts"]]
        assert d["artifact_count"] == 4
        assert set(types) == {"chart"}
        assert set(kinds) == {"bar", "line", "pie", "scatter"}


# ── CHAT ───────────────────────────────────────────────────────
class TestChat:
    def test_chat_autodetect_and_session_continuity(self, api):
        r = api.post(f"{BASE_URL}/api/jeeves/chat",
                     json={"message": "give me a report with a chart and spreadsheet of legion competency"},
                     timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        sid = d["session_id"]
        assert sid
        assert "pdf" in d["forms"] and "spreadsheet" in d["forms"] and "charts" in d["forms"]
        assert d["artifact_count"] > 0
        assert d["reply"]
        assert d["tier"] in ("local", "free", "paid")

        # follow-up in same session
        r2 = api.post(f"{BASE_URL}/api/jeeves/chat",
                      json={"session_id": sid, "message": "add another chart of readiness"},
                      timeout=TIMEOUT)
        assert r2.status_code == 200
        assert r2.json()["session_id"] == sid

        # history grew
        time.sleep(0.3)
        r3 = api.get(f"{BASE_URL}/api/jeeves/chat/{sid}", timeout=TIMEOUT)
        assert r3.status_code == 200
        h = r3.json()
        assert h["count"] >= 2

    def test_chat_force_all_forms(self, api):
        r = api.post(f"{BASE_URL}/api/jeeves/chat",
                     json={"message": "fire dragon boss", "force_all_forms": True},
                     timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert set(d["forms"]) == {"text", "pdf", "spreadsheet", "charts", "graph", "visual"}
        types = [a["type"] for a in d["artifacts"]]
        assert "pdf" in types and "spreadsheet" in types
        assert "chart" in types and "graph" in types and "visual" in types

    def test_chat_multimodal_pdf(self, api):
        r = api.post(f"{BASE_URL}/api/jeeves/chat",
                     json={"message": "analyze", "pdf_base64": _min_pdf_b64()},
                     timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "pdf" in d["modalities"]


# ── FREE-TIER ──────────────────────────────────────────────────
class TestFreeTier:
    def test_free_tier_stats(self, api):
        r = api.get(f"{BASE_URL}/api/jeeves/free-tier", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "free_remaining" in d
        assert d["free_units_per_window"] == 240
        assert d["idle_threshold_seconds"] == 14400
        assert isinstance(d["idle_seconds"], (int, float))
        assert "escalations_to_paid" in d


# ── IDLE AUGMENT ───────────────────────────────────────────────
class TestIdleAugment:
    def test_idle_augment_not_augmented_when_active(self, api):
        # ensure activity is fresh
        api.get(f"{BASE_URL}/api/jeeves/free-tier", timeout=TIMEOUT)
        r = api.post(f"{BASE_URL}/api/ops/scheduler/run",
                     json={"job_id": "idle_augment"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        # last_run.result.augmented must be False on fresh system
        result = (d.get("last_run") or {}).get("result") or {}
        assert result.get("augmented") is False, f"expected augmented=False on fresh system, got {result}"

    def test_scheduler_lists_idle_augment(self, api):
        r = api.get(f"{BASE_URL}/api/ops/scheduler", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        job_ids = [j["id"] for j in d.get("jobs", [])]
        assert "idle_augment" in job_ids


# ── REGRESSION ─────────────────────────────────────────────────
class TestRegression:
    def test_coverage_selftest_10_10(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/coverage/selftest", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        passed = d.get("passed", 0)
        total = d.get("total", 0)
        assert passed == 10 and total == 10, f"expected 10/10, got {passed}/{total}"
        assert d.get("ready") is True

    def test_prood_readiness_full(self, api):
        r = api.get(f"{BASE_URL}/api/prood/readiness", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        percent = d.get("overall_percent")
        live = d.get("capabilities_live")
        total = d.get("capabilities_total")
        assert percent == 100.0, f"expected 100%, got {percent}"
        assert live == 16 and total == 16, f"expected 16/16, got {live}/{total}"

    def test_omega_legions_16(self, api):
        r = api.get(f"{BASE_URL}/api/omega/legions", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        lc = d.get("legion_count") or d.get("count") or len(d.get("legions", []))
        assert lc == 16, f"expected 16 legions, got {lc}"

    def test_health_registry_ok_212(self, api):
        r = api.get(f"{BASE_URL}/api/health/registry", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        ok = d.get("ok_count") or d.get("ok") or 0
        skipped = d.get("skipped", 0)
        # ok can be True bool from wrapper — get the counter
        if isinstance(ok, bool):
            ok = d.get("ok_count") or d.get("passed") or 0
        assert ok >= 212, f"expected ok>=212, got {ok} (payload keys: {list(d.keys())})"
        assert skipped == 0, f"expected skipped=0, got {skipped}"

    def test_delta_stats_multimodal_true(self, api):
        r = api.get(f"{BASE_URL}/api/omega/delta/stats", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d.get("multimodal") is True, f"multimodal not true: {d}"
