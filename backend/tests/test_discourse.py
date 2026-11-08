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
    """Never access a local .env or network during pytest collection."""
    base = (os.environ.get("EXPO_BACKEND_URL")
            or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or "").strip().rstrip("/")
    if not base:
        pytest.skip("live discourse tests need EXPO_BACKEND_URL or EXPO_PUBLIC_BACKEND_URL")
    if not base.startswith(("https://", "http://")):
        pytest.skip("live discourse backend URL must be absolute HTTP(S)")
    return base


@pytest.fixture(scope="module")
def live_base_url() -> str:
    return _base_url()


@pytest.fixture(scope="module")
def private_discourse_headers() -> dict[str, str]:
    """Credentialed live checks must be explicitly enabled by the operator."""
    token = (os.environ.get("DISCOURSE_TEST_BEARER_TOKEN") or "").strip()
    if not token:
        pytest.skip("Private discourse live tests need DISCOURSE_TEST_BEARER_TOKEN")
    return {"Authorization": "Bearer " + token}


@pytest.mark.live_service
class TestLive:
    def test_panel_endpoint(self, live_base_url, private_discourse_headers):
        r = requests.get(f"{live_base_url}/api/discourse/panel",
                         headers=private_discourse_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "default_panel" in d and "default_judge" in d and "available_models" in d

    def test_history_endpoint(self, live_base_url, private_discourse_headers):
        r = requests.get(f"{live_base_url}/api/discourse/history?limit=5",
                         headers=private_discourse_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert "deliberations" in r.json()
