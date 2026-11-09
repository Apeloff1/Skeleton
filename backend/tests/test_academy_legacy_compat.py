from __future__ import annotations

import asyncio

import routes.academy_legacy_compat as compat
from core.routes_registry import KNOWN_ROUTES


def test_academy_legacy_compat_is_registered():
    assert ("routes.academy_legacy_compat", "router") in KNOWN_ROUTES


def test_academy_topic_module_compat_preserves_legacy_envelope(monkeypatch):
    async def fake_section(topic_id: str, module_id: str):
        assert topic_id == "system_design"
        assert module_id == "sd_fundamentals"
        return {
            "section": {"id": module_id, "name": "Fundamentals"},
            "bible_name": "System Design Bible",
        }

    monkeypatch.setattr(compat, "get_bible_section", fake_section)
    result = asyncio.run(
        compat.get_topic_module_compat("system_design", "sd_fundamentals")
    )

    assert result == {
        "module": {"id": "sd_fundamentals", "name": "Fundamentals"},
        "topic_name": "System Design Bible",
    }
