from __future__ import annotations

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_benchmark import (
    GameEngineBenchmarkArena,
    QualityExpectation,
    build_game_engine_benchmark_arena,
)
from skeleton.jeeves.game_engine_lab import EngineEra, GameEngineLabError


def test_quality_expectation_rejects_invalid_bounds() -> None:
    with pytest.raises(GameEngineLabError):
        QualityExpectation(minimum_score=0)
    with pytest.raises(GameEngineLabError):
        QualityExpectation(maximum_failures=-1)
    with pytest.raises(GameEngineLabError):
        QualityExpectation(max_candidates=0)


def test_cross_era_benchmark_is_complete_deterministic_and_green() -> None:
    arena = GameEngineBenchmarkArena()

    first = arena.benchmark_all("soulslike")
    second = arena.benchmark_all("soulslike")

    assert first == second
    assert first.all_meet_expectation
    assert first.minimum_score == 1.0
    assert len(first.entries) == len(EngineEra)
    assert [entry.era for entry in first.entries] == list(EngineEra)
    assert all(entry.passed for entry in first.entries)
    assert all(entry.failures == () for entry in first.entries)
    assert all(len(entry.tree_digest) == 64 for entry in first.entries)
    assert all(len(entry.probe_digest) == 64 for entry in first.entries)
    assert len(first.digest) == 64


@pytest.mark.parametrize("era", list(EngineEra))
def test_each_era_tournament_detects_and_recovers_all_attacks(
    era: EngineEra,
) -> None:
    arena = GameEngineBenchmarkArena()
    report = arena.tournament(era, "roguelike")

    assert report.passed
    assert report.baseline_score == 1.0
    assert len(report.baseline_digest) == 64
    assert len(report.digest) == 64
    assert tuple(attack.name for attack in report.attacks) == (
        "tuning_overflow",
        "contract_delete",
        "stale_patch",
    )

    tuning, contract, stale = report.attacks
    for attack in (tuning, contract):
        assert attack.detected
        assert attack.candidate_count == 3
        assert attack.accepted
        assert attack.recovered
        assert attack.attacked_score < attack.recovered_score
        assert attack.recovered_score == 1.0
        assert attack.checkpoint_count == 2
        assert attack.selected_digest == report.baseline_digest

    assert stale.detected
    assert not stale.accepted
    assert stale.recovered
    assert stale.candidate_count == 1
    assert stale.attacked_score == 1.0
    assert stale.recovered_score == 1.0
    assert stale.selected_digest is None


def test_tournament_all_is_deterministic_and_covers_every_era() -> None:
    arena = GameEngineBenchmarkArena()

    first = arena.tournament_all("metroidvania")
    second = arena.tournament_all("metroidvania")

    assert first == second
    assert [report.era for report in first] == list(EngineEra)
    assert all(report.passed for report in first)


def test_custom_expectation_is_enforced() -> None:
    expectation = QualityExpectation(
        minimum_score=0.95,
        maximum_failures=0,
        require_passed=True,
        max_rounds=4,
        max_candidates=8,
    )
    arena = build_game_engine_benchmark_arena(expectation)
    report = arena.benchmark_all()

    assert report.expectation == expectation
    assert report.all_meet_expectation


def test_attacks_do_not_mutate_canonical_baseline() -> None:
    arena = GameEngineBenchmarkArena()
    baseline = arena.lab.create(EngineEra.NEXT, "immersive_sim")
    digest = baseline.tree.digest

    tuning = arena.tuning_overflow_attack(baseline)
    deleted = arena.contract_delete_attack(baseline)

    assert tuning.tree.digest != digest
    assert deleted.tree.digest != digest
    assert baseline.tree.digest == digest
    assert arena.lab.evaluate(baseline).passed


def test_tournament_requires_canonical_engine_to_meet_expectation() -> None:
    expectation = QualityExpectation(
        minimum_score=1.0,
        maximum_failures=0,
        require_passed=True,
    )
    arena = GameEngineBenchmarkArena(expectation=expectation)
    original = arena.lab.evaluate

    class WeakReport:
        score = 0.9
        failed = ("forced",)
        passed = False
        probes = ()

    def weak(sandbox):
        del sandbox
        return WeakReport()

    arena.lab.evaluate = weak
    try:
        with pytest.raises(
            GameEngineLabError,
            match="does not meet",
        ):
            arena.tournament(EngineEra.PONG)
    finally:
        arena.lab.evaluate = original


def test_jeeves_owns_cross_era_benchmark_and_red_team_surface() -> None:
    jeeves = Jeeves()

    matrix = jeeves.benchmark_game_engines(
        gameplay_dialect="arcade_golden_age"
    )
    tournament = jeeves.red_team_game_engine(
        EngineEra.PONG,
        gameplay_dialect="arcade_golden_age",
    )

    assert matrix.all_meet_expectation
    assert len(matrix.entries) == len(EngineEra)
    assert tournament.passed
    assert tournament.era is EngineEra.PONG
    assert tuple(
        attack.name
        for attack in tournament.attacks
    ) == (
        "tuning_overflow",
        "contract_delete",
        "stale_patch",
    )
