from __future__ import annotations

from skeleton.automation.studio_registry import (
    STUDIO,
    STUDIO_SIZE,
    find_specialist,
    registry_fingerprint,
    select_cohort,
)


def test_studio_has_exactly_one_thousand_unique_stable_workers() -> None:
    assert STUDIO_SIZE == 1000
    assert len(STUDIO) == 1000
    assert len({bot.bot_id for bot in STUDIO}) == 1000
    assert STUDIO[0].bot_id == "studio-0001"
    assert STUDIO[-1].bot_id == "studio-1000"


def test_registry_spans_twenty_divisions_and_five_modes() -> None:
    assert len({bot.division for bot in STUDIO}) == 20
    assert {bot.mode for bot in STUDIO} == {"scout", "builder", "reviewer", "tester", "integrator"}
    assert all(bot.mission for bot in STUDIO)


def test_cohort_is_bounded_deterministic_and_diverse() -> None:
    first = select_cohort("night-1", size=15)
    second = select_cohort("night-1", size=15)
    assert first == second
    assert len(first) == 15
    assert len({bot.division for bot in first}) == 15


def test_specialist_selection_is_stable() -> None:
    a = find_specialist("gameplay_systems", mode="builder", seed="x")
    b = find_specialist("gameplay_systems", mode="builder", seed="x")
    assert a == b
    assert a.division == "gameplay_systems"
    assert a.mode == "builder"


def test_registry_fingerprint_is_stable_shape() -> None:
    digest = registry_fingerprint()
    assert len(digest) == 64
    int(digest, 16)
