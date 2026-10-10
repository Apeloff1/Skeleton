"""Dragon Game Forge deterministic design competition tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import (
    GameMechanicsMemory, GameObservation, Mechanic, PreferenceSignal,
)
from skeleton.ai.webcrawler.dragon_game_forge import (
    DragonGameForge, ForgePolicy, GameDesignConstraint,
)


def taste():
    store = GameMechanicsMemory(sqlite3.connect(":memory:"))
    observations = (
        GameObservation(1000, Mechanic.EXPLORATION, "Exploring secret paths",
                        0.95, PreferenceSignal.ENJOYED, True),
        GameObservation(2000, Mechanic.PHYSICS, "Objects have momentum",
                        0.85, PreferenceSignal.ENJOYED, True),
        GameObservation(3000, Mechanic.COMBAT, "Repetitive fights",
                        0.9, PreferenceSignal.DISLIKED, True),
    )
    session = store.build_session(
        "alice", "Example", 10000, observations,
        capture_consent=True, analysis_consent=True,
    )
    store.record(session, authorized=True)
    return store.distill("alice", authorized=True)


def constraints():
    return GameDesignConstraint(
        "adventure", "desktop", ("keyboard navigation",),
        ("original character and world",), max_complexity=4,
    )


def test_forge_selects_confirmed_positive_mechanics():
    spec = DragonGameForge().propose(taste(), constraints(), authorized=True)
    mechanics = {x.mechanic for x in spec.mechanics}
    assert Mechanic.EXPLORATION in mechanics
    assert Mechanic.PHYSICS in mechanics
    assert Mechanic.COMBAT not in mechanics
    assert spec.original_assets_required


def test_forge_proposal_is_deterministic():
    forge = DragonGameForge()
    profile = taste()
    assert forge.propose(profile, constraints(), authorized=True) == forge.propose(
        profile, constraints(), authorized=True,
    )


def test_competition_is_deterministic():
    forge = DragonGameForge()
    profile = taste()
    a = forge.compete(profile, constraints(), authorized=True, rounds=4)
    b = forge.compete(profile, constraints(), authorized=True, rounds=4)
    assert a == b
    assert a.winner_score.total >= a.runner_up_score.total
    assert a.rounds == 4


def test_competition_requires_authorization():
    with pytest.raises(PermissionError):
        DragonGameForge().compete(
            taste(), constraints(), authorized=False, rounds=2,
        )


def test_competition_respects_budget():
    forge = DragonGameForge(ForgePolicy(max_candidates=3))
    with pytest.raises(ValueError, match="budget"):
        forge.compete(taste(), constraints(), authorized=True, rounds=4)


def test_stale_taste_rejected():
    from dataclasses import replace
    forge = DragonGameForge()
    profile = taste()
    spec = forge.propose(profile, constraints(), authorized=True)
    with pytest.raises(ValueError, match="stale"):
        forge.evaluate(
            spec, replace(profile, fingerprint="different"), authorized=True,
        )


def test_accessibility_and_originality_warnings():
    forge = DragonGameForge()
    profile = taste()
    bare = GameDesignConstraint("adventure", "desktop")
    spec = forge.propose(profile, bare, authorized=True)
    result = forge.evaluate(spec, profile, authorized=True)
    assert len(result.warnings) >= 2


def test_no_positive_taste_is_not_fabricated():
    from dataclasses import replace
    forge = DragonGameForge()
    profile = taste()
    negative = replace(
        profile, insights=tuple(
            replace(x, preference_score=-1) for x in profile.insights
        ),
    )
    with pytest.raises(ValueError, match="positive"):
        forge.propose(negative, constraints(), authorized=True)


def test_invalid_genre_fails_closed():
    with pytest.raises(ValueError, match="genre"):
        DragonGameForge().propose(
            taste(), GameDesignConstraint("", "desktop"), authorized=True,
        )
