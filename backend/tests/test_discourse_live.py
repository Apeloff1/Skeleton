"""
Live end-to-end test for the Discourse & Discord deliberation endpoint.

This makes a REAL multi-LLM call through the Emergent Model Router and can
take ~30-90s. We use a generous 180s timeout. The test runs with discord=False
(faster: skips the cross red-team round).
"""
import os
import pytest
import requests


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


class TestLiveDeliberation:
    """Real multi-LLM panel through /api/discourse/deliberate."""

    def test_panel_endpoint_reachable(self):
        r = requests.get(f"{BASE_URL}/api/discourse/panel", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["default_judge"]
        assert isinstance(d["default_panel"], list) and len(d["default_panel"]) >= 2

    def test_deliberate_no_discord_returns_winner_shape(self):
        """The hot path used by the /discourse screen — discord=False."""
        body = {
            "task": "creative",
            "prompt": "Design one original core mechanic for a calm puzzle game about light.",
            "discord": False,
        }
        r = requests.post(
            f"{BASE_URL}/api/discourse/deliberate",
            json=body,
            timeout=180,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # No top-level error.
        assert "error" not in d or not d["error"], f"deliberation error: {d.get('error')}"
        # Required shape.
        for k in ("winner_index", "winner_model", "winner_content",
                  "judge_model", "panel", "candidates"):
            assert k in d, f"missing field {k} in response: {list(d.keys())}"
        assert isinstance(d["panel"], list) and len(d["panel"]) >= 2
        assert isinstance(d["candidates"], list) and len(d["candidates"]) >= 1
        assert isinstance(d["winner_index"], int)
        assert 0 <= d["winner_index"] < len(d["candidates"])
        assert d["winner_model"]
        # Winner content non-trivial.
        assert isinstance(d["winner_content"], str) and len(d["winner_content"]) > 20
        # Each candidate has model + content
        for c in d["candidates"]:
            assert c.get("model")
            assert isinstance(c.get("content"), str)
        # discord flag honoured (no critique on candidates)
        # (tolerant: empty string is OK)
        for c in d["candidates"]:
            assert not c.get("critique"), "expected no critique when discord=False"

    def test_short_prompt_rejected(self):
        r = requests.post(
            f"{BASE_URL}/api/discourse/deliberate",
            json={"task": "creative", "prompt": "hi", "discord": False},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json().get("error") == "prompt too short"
