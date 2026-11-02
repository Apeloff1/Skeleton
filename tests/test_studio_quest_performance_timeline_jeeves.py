"""Typed Jeeves performance timeline authority and source lease tests."""
from __future__ import annotations

import pytest

from skeleton.ai.game_builder.jeeves_app_capabilities import CapabilityRegistry
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_performance_timeline import PROMPT
from skeleton.ai.game_builder.studio_quest_performance_timeline_jeeves import (
    register_quest_performance_timeline_tools,
)
from tests.test_studio_quest_performance_timeline import prepared


def test_jeeves_cross_vertical_proposal_compile():
    parts, kwargs, plan = prepared()
    registry = CapabilityRegistry()
    register_quest_performance_timeline_tools(registry, *parts, **kwargs)
    request = {
        "prompt": PROMPT,
        "expected_voice_digest": kwargs["voice_receipt"]["voice_direction_digest"],
        "expected_chronology_digest": kwargs["chronology_receipt"]["chronology_digest"],
    }
    with pytest.raises(PermissionError):
        registry.execute("studio_quest_performance_proposal", request,
                         authorized=False, dry_run=False)
    assert registry.execute("studio_quest_performance_proposal", request,
                            authorized=True)["executed"] is False
    proposed = registry.execute("studio_quest_performance_proposal", request,
                                authorized=True, dry_run=False)
    assert proposed["rows"][0]["reviewed"] is False
    result = registry.execute("studio_quest_performance_compile", {
        "plan": plan,
        "expected_voice_digest": request["expected_voice_digest"],
        "expected_chronology_digest": request["expected_chronology_digest"],
    }, authorized=True, dry_run=False)
    assert result["authored_window_fit_verified"] is True
    assert result["audio_generated"] is False


def test_jeeves_rejects_mutated_canonical_source():
    parts, kwargs, plan = prepared()
    registry = CapabilityRegistry()
    register_quest_performance_timeline_tools(registry, *parts, **kwargs)
    parts[0]["quest"]["stage_graph"][0]["reward"] = "tampered"
    with pytest.raises(StudioQuestError):
        registry.execute("studio_quest_performance_proposal", {
            "prompt": PROMPT,
            "expected_voice_digest": kwargs["voice_receipt"]["voice_direction_digest"],
            "expected_chronology_digest": kwargs["chronology_receipt"]["chronology_digest"],
        }, authorized=True, dry_run=False)
