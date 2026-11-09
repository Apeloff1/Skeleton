"""
Phase I.4 — Design-Spec Compiler tests.

Deterministic surface (no network): tolerant JSON extraction, schema
normalisation (the anti-KeyError contract), and the coherence gate. Plus the
live /compile (one real reasoning call) and /list endpoints.
"""
import os

import pytest
import requests

from routes.design_spec import (
    _extract_json, _normalize, _coherence, _GDD_SKELETON, COHERENCE_THRESHOLD,
)


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"title": "X"}') == {"title": "X"}

    def test_fenced_json(self):
        assert _extract_json('```json\n{"title": "X"}\n```')["title"] == "X"

    def test_embedded_prose(self):
        out = _extract_json('Sure! Here it is:\n{"title": "Y", "genre": "rpg"}\nHope that helps.')
        assert out["genre"] == "rpg"

    def test_garbage_returns_empty(self):
        assert _extract_json("not json at all") == {}


class TestNormalize:
    def test_fills_all_skeleton_keys(self):
        g = _normalize({"title": "Z"})
        for k in _GDD_SKELETON:
            assert k in g
        assert g["title"] == "Z"

    def test_coerces_wrong_types(self):
        g = _normalize({"pillars": "single", "content_plan": "oops"})
        assert g["pillars"] == ["single"]
        assert isinstance(g["content_plan"], dict)
        assert g["content_plan"]["levels"] == 0

    def test_non_dict_input(self):
        g = _normalize("garbage")
        assert g == _normalize({})  # full skeleton


class TestCoherenceGate:
    def test_empty_spec_low_score(self):
        score, gaps = _coherence(_normalize({}))
        assert score < COHERENCE_THRESHOLD
        assert len(gaps) > 0

    def test_complete_spec_high_score(self):
        good = _normalize({
            "logline": "A bold game.",
            "pillars": ["a", "b", "c"],
            "core_loop": "loop",
            "mechanics": [{"name": "m1"}, {"name": "m2"}, {"name": "m3"}],
            "systems": [{"name": "s1"}, {"name": "s2"}],
            "coherence_self": 90,
        })
        score, gaps = _coherence(good)
        assert score >= COHERENCE_THRESHOLD
        assert gaps == []


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
    def test_compile_returns_typed_gdd(self):
        r = requests.post(f"{BASE_URL}/api/design-spec/compile",
                          json={"brief": "A cozy fishing roguelike on a haunted lake."},
                          timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "gdd" in d and "coherence_score" in d and "status" in d
        assert d["status"] in ("ready", "needs_revision")
        for k in _GDD_SKELETON:
            assert k in d["gdd"]
        assert "build_plan" in d

    def test_list_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/design-spec/list?limit=5", timeout=15)
        assert r.status_code == 200, r.text
        assert "specs" in r.json()
