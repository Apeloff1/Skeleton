"""Iteration 121 — Galaxy Studio Gamefile Command Center backend tests.

Validates:
  • /api/galaxy-studio/text-gamefile/generators returns 150 total
    (100 standard + 50 advanced) with required shape and unique keys.
  • POST /{key}/generate for STANDARD and ADVANCED generators returns a
    gamefile with id + non-empty fields derived from the input text.
  • GET /{build_id}/list returns the generated gamefiles.
  • POST /api/galaxy-studio/gates/target/{build_id}/{gid}/run-all returns
    overall_score, passed, 14 stages, aaa_passed bool (gates crosswired
    to gamefile target).
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
    "https://player-retention.preview.emergentagent.com"

BUILD_ID = "qa_cc_001"
STANDARD_KEY = "quest_from_text"
ADVANCED_KEYS = ["ai_behavior_tree", "netcode_model", "economy_sim"]
SAMPLE_TEXT = (
    "A desert oasis caravan is haunted by a ghost djinn that bargains with "
    "travellers for their dreams. The party must choose between freeing the "
    "djinn or stealing its lantern, leading to two distinct endings."
)


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Generators registry ────────────────────────────────────────────────────
class TestGenerators:
    def test_generators_counts_and_shape(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/text-gamefile/generators",
                       timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["count"] == 150, f"expected 150 generators, got {d.get('count')}"
        assert d["standard_count"] == 100, d.get("standard_count")
        assert d["advanced_count"] == 50, d.get("advanced_count")
        assert isinstance(d.get("group_counts"), dict) and d["group_counts"]
        gens = d["generators"]
        assert isinstance(gens, list) and len(gens) == 150
        keys = [g["key"] for g in gens]
        assert len(set(keys)) == 150, "generator keys are not unique"
        required = {"key", "label", "icon", "type", "fields", "group", "advanced"}
        for g in gens:
            missing = required - set(g.keys())
            assert not missing, f"{g.get('key')} missing fields: {missing}"
            assert isinstance(g["fields"], list) and len(g["fields"]) >= 3
            assert isinstance(g["advanced"], bool)


# ── Standard generator ────────────────────────────────────────────────────
class TestGenerateStandard:
    def test_quest_generation_returns_structured_gamefile(self, client):
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/{STANDARD_KEY}/generate",
            json={"build_id": BUILD_ID, "text": SAMPLE_TEXT, "enrich": False},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        gf = r.json()
        assert "error" not in gf, gf
        assert gf.get("id", "").startswith("gf_quest_from_text_")
        assert gf["build_id"] == BUILD_ID
        assert gf["system"] == STANDARD_KEY
        assert gf["kind"] == "gamefile"
        fields = gf.get("fields") or {}
        for k in ["title", "giver", "objectives", "stages", "rewards"]:
            assert k in fields, f"missing field {k}"
            v = fields[k]
            assert v not in (None, "", [], {}), f"empty field {k}: {v!r}"
        # list-fields should have multiple derived items
        assert isinstance(fields["objectives"], list) and len(fields["objectives"]) >= 2


# ── Advanced generators ───────────────────────────────────────────────────
class TestGenerateAdvanced:
    @pytest.mark.parametrize("key", ADVANCED_KEYS)
    def test_advanced_generation(self, client, key):
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/{key}/generate",
            json={"build_id": BUILD_ID, "text": SAMPLE_TEXT, "enrich": False},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        gf = r.json()
        assert "error" not in gf, gf
        assert gf["id"].startswith(f"gf_{key}_")
        assert gf["system"] == key
        fields = gf.get("fields") or {}
        assert len(fields) >= 3
        # At least one field must have a non-trivial value
        nonempty = [v for v in fields.values() if v not in (None, "", [], {})]
        assert len(nonempty) >= 3, f"too few populated fields: {fields}"


# ── Listing ───────────────────────────────────────────────────────────────
class TestListGamefiles:
    def test_list_returns_generated_files(self, client):
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/{BUILD_ID}/list",
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["build_id"] == BUILD_ID
        assert d["count"] >= 1
        assert isinstance(d.get("gamefiles"), list)
        systems = {gf["system"] for gf in d["gamefiles"]}
        assert STANDARD_KEY in systems
        # at least one advanced should be present too (from parametrized run)
        assert systems & set(ADVANCED_KEYS)


# ── 14-gate run-all on gamefile target ────────────────────────────────────
class TestGatesOnGamefile:
    def test_run_all_target_gamefile(self, client):
        # generate a fresh gamefile so we have a guaranteed gid
        gen = client.post(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/{STANDARD_KEY}/generate",
            json={"build_id": BUILD_ID, "text": SAMPLE_TEXT + " gate test.",
                  "enrich": False},
            timeout=30,
        ).json()
        gid = gen["id"]
        r = client.post(
            f"{BASE_URL}/api/galaxy-studio/gates/target/{BUILD_ID}/{gid}/run-all",
            json={"kind": "gamefile", "ai": False},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "overall_score" in d
        assert isinstance(d["overall_score"], (int, float))
        assert 0 <= d["overall_score"] <= 100
        assert "passed" in d and isinstance(d["passed"], int)
        assert d.get("gate_count") == 14, d.get("gate_count")
        assert isinstance(d.get("aaa_passed"), bool)
        stages = d.get("stages") or []
        assert len(stages) == 14, f"expected 14 stages, got {len(stages)}"
        for s in stages:
            assert "score" in s and "passed" in s
            assert isinstance(s["passed"], bool)
            assert 0 <= float(s["score"]) <= 100
