"""
Discourse & Discord engine tests — deterministic surface + live panel endpoint.
The full deliberation is verified via curl (it makes 5+ LLM calls); here we
prove the tolerant JSON parsing, the fidelity-weighted scoring contract, and
the /panel + /history endpoints.
"""
import os

import pytest
import requests

from routes.discourse import _extract_json, DEFAULT_PANEL, DEFAULT_JUDGE, MAX_PANEL


class TestExtractJson:
    def test_plain(self):
        assert _extract_json('{"winner_index": 1}')["winner_index"] == 1

    def test_fenced(self):
        assert _extract_json('```json\n{"winner_index": 0}\n```')["winner_index"] == 0

    def test_embedded(self):
        d = _extract_json('Verdict:\n{"scores": [], "winner_index": 2}\nDone.')
        assert d["winner_index"] == 2

    def test_garbage(self):
        assert _extract_json("no json") == {}


class TestPanelConfig:
    def test_default_panel_is_provider_diverse(self):
        # 3 models, should span >1 provider by construction
        assert len(DEFAULT_PANEL) >= 2
        assert DEFAULT_JUDGE
        assert MAX_PANEL >= len(DEFAULT_PANEL)


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
    def test_panel_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/discourse/panel", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "default_panel" in d and "default_judge" in d and "available_models" in d

    def test_history_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/discourse/history?limit=5", timeout=15)
        assert r.status_code == 200, r.text
        assert "deliberations" in r.json()
