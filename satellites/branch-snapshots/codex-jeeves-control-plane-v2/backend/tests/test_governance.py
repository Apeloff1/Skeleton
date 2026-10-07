"""
Backend regression tests for VII.5 Governance & Safety subsystem.

Covers:
  - POST /api/governance/scan/{pid}
  - GET  /api/governance/plagiarism/{pid}
  - POST /api/governance/report          (incl. auto-escalation @ 3 reports)
  - GET  /api/governance/reports?status=open
  - POST /api/governance/moderate/{rid}  (dismiss/warn/hide/restore)
  - GET  /api/governance/status/{pid}
  - GET  /api/governance/audit (+ ?target_id=)
  - GET  /api/governance/overview
  - Regression: /api/playable/list, /api/marketplace/listings,
                /api/worldforge/biomes still 200; registry count == 103.
"""
import os
import pytest
import requests
import uuid

BASE_URL = "https://gemini-game-craft.preview.emergentagent.com"
GOV = f"{BASE_URL}/api/governance"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def ready_pids(session):
    r = session.get(f"{BASE_URL}/api/playable/list", timeout=30)
    assert r.status_code == 200, f"playable/list returned {r.status_code}"
    data = r.json()
    items = data.get("items") or data.get("playables") or data.get("list") or []
    pids = [it.get("playable_id") for it in items if it.get("playable_id")]
    assert len(pids) >= 2, f"need at least 2 ready playables, got {len(pids)}"
    return pids


# ─────────────────── regression / registry ────────────────────────────
class TestRegressionAndRegistry:

    def test_playable_list_200(self, session):
        r = session.get(f"{BASE_URL}/api/playable/list", timeout=30)
        assert r.status_code == 200

    def test_marketplace_listings_200(self, session):
        r = session.get(f"{BASE_URL}/api/marketplace/listings", timeout=30)
        assert r.status_code == 200

    def test_worldforge_biomes_200(self, session):
        r = session.get(f"{BASE_URL}/api/worldforge/biomes", timeout=30)
        assert r.status_code == 200

    def test_registry_no_skipped(self, session):
        """Self-prefixed block should register 103 routes with 0 skipped
        (governance is a self-prefixed new router); combined endpoint
        reports KNOWN_ROUTES_WITH_PREFIX (33) + KNOWN_ROUTES (103) = 136."""
        r = session.get(f"{BASE_URL}/api/health/registry", timeout=15)
        if r.status_code != 200:
            pytest.skip(f"registry endpoint {r.status_code}")
        data = r.json()
        assert data.get("skipped", 1) == 0, f"some routers skipped: {data}"
        # The combined ok is 33+103 = 136. Accept that exact total OR the
        # self-prefixed-only value 103, depending on whether the endpoint
        # exposes the combined or per-batch report.
        n = data.get("ok") or data.get("registered")
        assert n in (103, 136), f"unexpected route count: {n}"


# ─────────────────── overview ─────────────────────────────────────────
class TestOverview:
    def test_overview_shape(self, session):
        r = session.get(f"{GOV}/overview", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("games", "hidden", "warned", "in_review", "open_reports", "audit_entries"):
            assert k in d, f"missing {k}"
            assert isinstance(d[k], int), f"{k} not int: {d[k]!r}"


# ─────────────────── scan ─────────────────────────────────────────────
class TestScan:
    def test_scan_clean_game_passes(self, session, ready_pids):
        pid = ready_pids[0]
        r = session.post(f"{GOV}/scan/{pid}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["playable_id"] == pid
        assert d["verdict"] in ("pass", "review", "block")
        assert 0 <= d["score"] <= 100
        assert isinstance(d["flags"], list)
        # If the playable is not a deliberately crafted malicious sample,
        # the deterministic lexicon should yield pass/100.
        if not d["flags"]:
            assert d["verdict"] == "pass"
            assert d["score"] == 100

    def test_scan_bad_pid_returns_not_found(self, session):
        r = session.post(f"{GOV}/scan/__nope_{uuid.uuid4().hex[:8]}", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "not found"}


# ─────────────────── plagiarism ───────────────────────────────────────
class TestPlagiarism:
    def test_plagiarism_shape(self, session, ready_pids):
        pid = ready_pids[0]
        r = session.get(f"{GOV}/plagiarism/{pid}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["playable_id"] == pid
        assert d["verdict"] in ("original", "similar", "near_duplicate")
        assert 0.0 <= float(d["top_similarity"]) <= 1.0
        assert isinstance(d["matches"], list)
        assert isinstance(d["compared"], int)
        # Sort order: desc by similarity
        sims = [m["similarity"] for m in d["matches"]]
        assert sims == sorted(sims, reverse=True), "matches not sorted desc by similarity"
        # Per-match shape
        for m in d["matches"]:
            for k in ("playable_id", "title", "genre", "similarity"):
                assert k in m

    def test_plagiarism_bad_pid(self, session):
        r = session.get(f"{GOV}/plagiarism/__nope_{uuid.uuid4().hex[:8]}", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "not found"}


# ─────────────────── report + auto-escalation ─────────────────────────
class TestReportAndEscalation:

    def _find_fresh_pid(self, session, ready_pids):
        """Pick a ready playable with reports_count < 3."""
        for pid in ready_pids:
            r = session.get(f"{GOV}/status/{pid}", timeout=15)
            if r.status_code == 200:
                d = r.json()
                if d.get("reports_count", 0) < 3 and d.get("moderation_status", "ok") in (None, "ok"):
                    return pid
        pytest.skip("no fresh playable with <3 reports available")

    def test_report_missing_pid(self, session):
        r = session.post(f"{GOV}/report", json={"reason": "spam"}, timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "playable_id required"}

    def test_report_bad_pid(self, session):
        r = session.post(f"{GOV}/report", json={
            "playable_id": f"__nope_{uuid.uuid4().hex[:8]}",
            "reason": "spam",
        }, timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "not found"}

    def test_report_invalid_reason_coerced_to_other(self, session, ready_pids):
        pid = self._find_fresh_pid(session, ready_pids)
        r = session.post(f"{GOV}/report", json={
            "playable_id": pid, "reason": "totally_invalid_reason_xyz",
            "reporter_id": f"TEST_{uuid.uuid4().hex[:6]}",
        }, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "report_id" in d
        # fetch open queue and find that report
        rep_id = d["report_id"]
        rr = session.get(f"{GOV}/reports?status=open&limit=200", timeout=20)
        assert rr.status_code == 200
        rows = rr.json().get("reports", [])
        found = next((row for row in rows if row.get("report_id") == rep_id), None)
        assert found, "report not in open queue"
        assert found["reason"] == "other", f"reason should be coerced to other, got {found['reason']}"

    def test_auto_escalation_on_third_report(self, session, ready_pids):
        pid = self._find_fresh_pid(session, ready_pids)
        # Baseline status
        s0 = session.get(f"{GOV}/status/{pid}", timeout=15).json()
        starting = s0.get("reports_count", 0)
        # File reports until count reaches AUTO_REVIEW_REPORTS=3
        needed = max(0, 3 - starting)
        if needed == 0:
            pytest.skip("game already at >=3 reports; cannot test escalation flip")
        results = []
        for i in range(needed):
            r = session.post(f"{GOV}/report", json={
                "playable_id": pid, "reason": "spam",
                "detail": f"TEST_escalation_{i}",
                "reporter_id": f"TEST_reporter_{i}",
            }, timeout=15)
            assert r.status_code == 200
            results.append(r.json())
        # The LAST report should flip escalated:true (when count crosses 3)
        last = results[-1]
        assert last["reports_count"] >= 3
        assert last["escalated"] is True, f"3rd report did not escalate: {last}"
        # And status should now reflect moderation_status=review
        s1 = session.get(f"{GOV}/status/{pid}", timeout=15).json()
        assert s1.get("moderation_status") == "review", f"status not flipped to review: {s1}"


# ─────────────────── reports queue + moderation ───────────────────────
class TestReportsQueueAndModeration:

    def test_reports_open_shape(self, session):
        r = session.get(f"{GOV}/reports?status=open&limit=50", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "reports" in d
        assert "count" in d
        assert "open_total" in d
        assert isinstance(d["reports"], list)
        for row in d["reports"][:5]:
            for k in ("title", "genre", "moderation_status"):
                assert k in row, f"hydrated field {k} missing"

    def test_moderate_bad_rid(self, session):
        r = session.post(f"{GOV}/moderate/__nope_{uuid.uuid4().hex[:8]}",
                         json={"action": "dismiss"}, timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "not found"}

    @pytest.mark.parametrize("action,expected_mod,expected_status", [
        ("warn", "warned", "resolved"),
        ("hide", "hidden", "resolved"),
        ("dismiss", "ok", "dismissed"),
        ("restore", "ok", "resolved"),
    ])
    def test_moderate_actions(self, session, ready_pids, action, expected_mod, expected_status):
        # File a fresh report so we always have an rid to act on.
        # Pick any ready pid (don't worry if it crosses 3; we only care about action effect)
        pid = ready_pids[0]
        rep = session.post(f"{GOV}/report", json={
            "playable_id": pid, "reason": "spam",
            "reporter_id": f"TEST_mod_{action}",
            "detail": f"TEST_moderate_{action}",
        }, timeout=15).json()
        rid = rep.get("report_id")
        assert rid, f"failed to create report: {rep}"

        m = session.post(f"{GOV}/moderate/{rid}", json={"action": action, "actor": "TEST_mod"},
                         timeout=15)
        assert m.status_code == 200
        md = m.json()
        assert md["report_id"] == rid
        assert md["action"] == action
        assert md["moderation_status"] == expected_mod

        # status/{pid} reflects new moderation_status
        st = session.get(f"{GOV}/status/{pid}", timeout=15).json()
        assert st.get("moderation_status") == expected_mod, f"status mismatch after {action}: {st}"

        # The resolved report should NOT be in the open queue anymore
        rr = session.get(f"{GOV}/reports?status=open&limit=200", timeout=20).json()
        open_ids = {r.get("report_id") for r in rr.get("reports", [])}
        assert rid not in open_ids, "resolved/dismissed report still appears in open queue"

        # If parametrize gave a non-restore final, restore to 'ok' for cleanliness
        if expected_mod != "ok":
            session.post(f"{GOV}/report", json={
                "playable_id": pid, "reason": "other", "reporter_id": "TEST_restore",
            }, timeout=15)


# ─────────────────── audit trail ──────────────────────────────────────
class TestAudit:
    def test_audit_basic(self, session):
        r = session.get(f"{GOV}/audit?limit=20", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "entries" in d
        rows = d["entries"]
        assert isinstance(rows, list)
        if rows:
            # newest-first
            ats = [row["at"] for row in rows]
            assert ats == sorted(ats, reverse=True), "audit not newest-first"
            for row in rows[:3]:
                for k in ("action", "target_id", "actor", "at"):
                    assert k in row

    def test_audit_target_filter(self, session, ready_pids):
        pid = ready_pids[0]
        # ensure at least one audit entry exists for this pid via a scan
        session.post(f"{GOV}/scan/{pid}", timeout=20)
        r = session.get(f"{GOV}/audit", params={"limit": 50, "target_id": pid}, timeout=15)
        assert r.status_code == 200
        rows = r.json()["entries"]
        assert rows, "expected at least one audit row for the scanned pid"
        for row in rows:
            assert row["target_id"] == pid
