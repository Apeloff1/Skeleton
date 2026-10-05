"""Iteration 126 — Tier→page scaling + prune endpoint regression.

Tests the new tier-volume scaling built into ALL 14 gates and the prune endpoint
on /api/galaxy-studio/text-gamefile.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "http://localhost:8001").rstrip("/")

API = f"{BASE_URL}/api/galaxy-studio/text-gamefile"
PIPE = f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline"

TEXT = ("Crimson tide boss design. Two phases, three abilities, an arena hazard, "
        "and a final enrage. Tells include a wide red telegraph and a slam recoil.")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── module: tier→page scaling ────────────────────────────────────────────────
class TestTierScaling:

    def test_generators_count(self, client):
        r = client.get(f"{API}/generators")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 150, f"expected 150, got {data['count']}"
        assert data["tiered_count"] == 22, f"expected tiered_count=22, got {data['tiered_count']}"

    def test_tier1_vs_tier5_scales_5x(self, client):
        build_id = "qa_scale_1"
        # prune scope first to ensure clean state
        client.post(f"{API}/prune", json={"build_id": build_id})

        # Generate same text twice — once tier='1', once tier='5'
        g1 = client.post(f"{API}/boss_design/generate",
                         json={"build_id": build_id, "text": TEXT, "tier": "1"})
        g5 = client.post(f"{API}/boss_design/generate",
                         json={"build_id": build_id, "text": TEXT, "tier": "5"})
        assert g1.status_code == 200, g1.text
        assert g5.status_code == 200, g5.text
        gid1, gid5 = g1.json()["id"], g5.json()["id"]
        assert g1.json().get("tier_index") == 1
        assert g5.json().get("tier_index") == 5

        # Run pipeline
        r1 = client.post(f"{PIPE}/{build_id}/{gid1}/run")
        r5 = client.post(f"{PIPE}/{build_id}/{gid5}/run")
        assert r1.status_code == 200, r1.text
        assert r5.status_code == 200, r5.text
        d1, d5 = r1.json(), r5.json()

        # Verify volume blocks
        v1, v5 = d1["volume"], d5["volume"]
        assert v1["tier_index"] == 1 and v1["tier_weight"] == 1.0
        assert v5["tier_index"] == 5 and v5["tier_weight"] == 5.0
        assert v1["effective_pages_per_choice"] == 200
        assert v5["effective_pages_per_choice"] == 1000
        # Choices are same → tier5 must be 5× tier1
        assert v1["choices"] == v5["choices"]
        assert v5["total_pages"] == 5 * v1["total_pages"], (
            f"tier5 {v5['total_pages']} not 5× tier1 {v1['total_pages']}")
        # pages also reflected at top level
        assert d1["pages"] == v1["total_pages"]
        assert d5["pages"] == v5["total_pages"]

    def test_untiered_defaults_weight_1(self, client):
        build_id = "qa_scale_1"
        g = client.post(f"{API}/quest_from_text/generate",
                        json={"build_id": build_id, "text": "Find the lost relic in the cave."})
        assert g.status_code == 200, g.text
        gid = g.json()["id"]
        assert g.json().get("tier_index") in (None,)
        r = client.post(f"{PIPE}/{build_id}/{gid}/run")
        assert r.status_code == 200, r.text
        v = r.json()["volume"]
        assert v["tier_weight"] == 1.0
        assert v["tier_index"] is None
        assert v["effective_pages_per_choice"] == 200


# ── module: scale block on ALL 14 gates ──────────────────────────────────────
class TestScaleOnAllGates:

    def test_every_gate_has_scale_block(self, client):
        build_id = "qa_scale_1"
        g = client.post(f"{API}/boss_design/generate",
                        json={"build_id": build_id, "text": TEXT, "tier": "3"})
        gid = g.json()["id"]
        r = client.post(f"{PIPE}/{build_id}/{gid}/run")
        data = r.json()
        stages = data["stages"]
        assert len(stages) == 14
        build_pages = data["volume"]["total_pages"]
        expected_gate_pages = round(build_pages / 14)
        for st in stages:
            scale = st.get("scale")
            assert scale, f"gate {st['key']} missing scale block"
            assert scale["tier_index"] == 3
            assert scale["tier_weight"] == 2.25
            assert scale["pages_per_choice"] == round(200 * 2.25)  # 450
            assert scale["build_pages"] == build_pages
            assert scale["gate_pages"] == expected_gate_pages
            # consistency: gate_pages ≈ build_pages/14
            assert abs(scale["gate_pages"] * 14 - build_pages) <= 14


# ── module: prune endpoint ───────────────────────────────────────────────────
class TestPrune:

    def test_scoped_prune(self, client):
        build_id = "qa_prune_1"
        # Generate a few gamefiles
        for _ in range(3):
            r = client.post(f"{API}/quest_from_text/generate",
                            json={"build_id": build_id, "text": TEXT})
            assert r.status_code == 200

        # List > 0
        lst = client.get(f"{API}/{build_id}/list").json()
        assert lst["count"] > 0, lst

        # Prune scoped
        pr = client.post(f"{API}/prune", json={"build_id": build_id})
        assert pr.status_code == 200, pr.text
        pj = pr.json()
        assert pj["gamefiles_deleted"] > 0, pj
        assert pj["scope"] == build_id

        # List now empty
        lst2 = client.get(f"{API}/{build_id}/list").json()
        assert lst2["count"] == 0

    def test_prune_all_empty_body(self, client):
        # Use empty body — should not error, scope: ALL
        # Note: this is destructive; intentionally last test.
        pr = client.post(f"{API}/prune", json={})
        assert pr.status_code == 200, pr.text
        pj = pr.json()
        assert "gamefiles_deleted" in pj
        assert "history_deleted" in pj
        assert pj["scope"] == "ALL"


# ── module: regression — pipeline shape preserved ────────────────────────────
class TestPipelineRegression:

    def test_pipeline_shape(self, client):
        build_id = "qa_scale_1"
        g = client.post(f"{API}/boss_design/generate",
                        json={"build_id": build_id, "text": TEXT, "tier": "2"})
        gid = g.json()["id"]
        r = client.post(f"{PIPE}/{build_id}/{gid}/run")
        assert r.status_code == 200, r.text
        d = r.json()
        # 14 stages
        assert len(d["stages"]) == 14
        # set_a.segments_detail (7 segs × 6 paragraphs)
        for st in d["stages"]:
            sa = st.get("set_a") or {}
            segs = sa.get("segments_detail") or []
            assert len(segs) == 7, f"gate {st['key']} segments={len(segs)}"
            for seg in segs:
                assert seg["paragraph_count"] == 6
                assert len(seg["paragraphs"]) == 6
        # overall_score + aaa block
        assert "overall_score" in d and isinstance(d["overall_score"], (int, float))
        assert "aaa" in d and isinstance(d["aaa"], dict)
        assert "overall_score" in d["aaa"]
