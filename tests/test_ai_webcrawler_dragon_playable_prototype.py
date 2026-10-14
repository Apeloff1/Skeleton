"""Offline tests for the original game prototype renderer."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_game_mechanics import (
    GameMechanicsMemory, GameObservation, Mechanic, PreferenceSignal,
)
from skeleton.ai.webcrawler.dragon_game_forge import (
    DragonGameForge, GameDesignConstraint,
)
from skeleton.ai.webcrawler.dragon_playable_prototype import (
    render_playable_prototype,
)


def spec():
    store = GameMechanicsMemory(sqlite3.connect(":memory:"))
    item = GameObservation(
        1000, Mechanic.PLATFORMING, "Responsive jumping",
        0.95, PreferenceSignal.ENJOYED, True,
    )
    session = store.build_session(
        "alice", "Example", 10000, (item,),
        capture_consent=True, analysis_consent=True,
    )
    store.record(session, authorized=True)
    taste = store.distill("alice", authorized=True)
    return DragonGameForge().propose(
        taste, GameDesignConstraint(
            "platform adventure", "desktop",
            ("keyboard support",), ("original shapes",),
        ), authorized=True,
    )


def test_playable_html_is_self_contained():
    result = render_playable_prototype(spec(), authorized=True)
    assert "<canvas" in result.html
    assert "requestAnimationFrame" in result.html
    assert "connect-src 'none'" in result.html
    assert "platforming" in result.supported_mechanics


def test_playable_generation_is_deterministic():
    candidate = spec()
    assert render_playable_prototype(
        candidate, authorized=True,
    ) == render_playable_prototype(candidate, authorized=True)


def test_prototype_requires_authorization():
    with pytest.raises(PermissionError):
        render_playable_prototype(spec(), authorized=False)


def test_prototype_does_not_embed_external_assets():
    html = render_playable_prototype(spec(), authorized=True).html
    assert "<iframe" not in html
    assert "<img" not in html
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
