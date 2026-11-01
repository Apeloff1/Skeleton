"""Cross-chapter deterministic execution, bounds, and replay assurance."""
from dataclasses import replace

import pytest

from skeleton.game.expedition_ledger import (
    CHAPTER_IDS, ExpeditionError, evidence, load_episode,
    new_game, restore, run_episode, shortest_plan, snapshot, step,
)


def test_catalog_is_complete_and_namespaced() -> None:
    assert len(CHAPTER_IDS) == 49
    assert len(set(CHAPTER_IDS)) == len(CHAPTER_IDS)
    assert all("__" in chapter for chapter in CHAPTER_IDS)


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_bounded_planner_can_finish_every_authored_chapter(chapter_id: str) -> None:
    ep = load_episode(chapter_id)
    plan = shortest_plan(ep)
    assert len(plan) <= 48
    finished = run_episode(ep, plan)
    assert finished.status == "won"
    assert finished.has_key and finished.objective
    assert "expedition_completed" in finished.events
    assert evidence(ep, finished)["source_digest"] == ep.source_digest


@pytest.mark.parametrize("chapter_id", CHAPTER_IDS)
def test_every_chapter_save_is_source_bound_and_replayable(chapter_id: str) -> None:
    ep = load_episode(chapter_id)
    finished = run_episode(ep, shortest_plan(ep))
    stored = snapshot(ep, finished)
    assert restore(ep, stored) == finished
    assert snapshot(ep, restore(ep, stored)) == stored


def test_catalog_refuses_path_injection_and_unpublished_source() -> None:
    for invalid in ("../private", "/etc/passwd", "", "ash__unknown", 2):
        with pytest.raises(ExpeditionError, match="outside published catalog"):
            load_episode(invalid)  # type: ignore[arg-type]


def test_exit_requires_objective_and_key_cannot_be_bypassed() -> None:
    ep = load_episode(CHAPTER_IDS[0])
    state = replace(new_game(ep), x=10, y=1)
    unfinished = step(ep, state, "east")
    assert unfinished.status == "active"
    assert "exit_requires_objective" in unfinished.events


def test_terminal_game_is_immutable_and_bad_commands_fail() -> None:
    ep = load_episode(CHAPTER_IDS[0])
    complete = run_episode(ep, shortest_plan(ep))
    with pytest.raises(ExpeditionError, match="terminal"):
        step(ep, complete, "east")
    with pytest.raises(ExpeditionError, match="unsupported movement"):
        step(ep, new_game(ep), "../../etc/passwd")


def test_valid_digest_cannot_hide_unreachable_forged_state() -> None:
    from skeleton.game.expedition_ledger.runtime import digest

    ep = load_episode(CHAPTER_IDS[0])
    stored = snapshot(ep, new_game(ep))
    stored["state"]["score"] = 1000
    stored["digest"] = digest(stored["state"])
    with pytest.raises(ExpeditionError, match="verified replay"):
        restore(ep, stored)


def test_snapshot_refuses_unreachable_typed_state() -> None:
    ep = load_episode(CHAPTER_IDS[0])
    fake = replace(new_game(ep), has_key=True, score=500)
    with pytest.raises(ExpeditionError, match="deterministic replay"):
        snapshot(ep, fake)


def test_chapter_cannot_rebind_state_to_different_layout_digest() -> None:
    first = load_episode(CHAPTER_IDS[0])
    second = load_episode(CHAPTER_IDS[1])
    with pytest.raises(ExpeditionError, match="another source"):
        step(second, new_game(first), "east")

def test_locked_objective_is_recoverable_after_source_key_is_found() -> None:
    """A denied first pickup cannot destroy the only winning route."""
    ep = load_episode(CHAPTER_IDS[0])
    reach_objective_without_key = (
        ("south",) + ("east",) * 6 + ("north",)
    )
    denied = run_episode(ep, reach_objective_without_key)
    assert denied.status == "active"
    assert not denied.objective and not denied.has_key
    assert denied.events.count("objective_locked") == 1

    recovered = run_episode(
        ep, reach_objective_without_key + ("west",) * 4 + ("east",) * 4
    )
    assert recovered.has_key and recovered.objective
    assert recovered.events.count("objective_recovered") == 1
    assert recovered.score >= 25
    assert restore(ep, snapshot(ep, recovered)) == recovered
