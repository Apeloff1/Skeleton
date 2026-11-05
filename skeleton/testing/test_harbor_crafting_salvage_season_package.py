"""Championship package, portable replay and adversarial custody acceptance."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage_season_package import (
    build_season_package, play_season_package, verify_season_package,
    verify_season_package_play,
)
from skeleton.game.gameplay.harbor_crafting_salvage_season_acceptance import (
    accept_salvage_season, verify_salvage_season_acceptance,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions
from skeleton.testing.test_harbor_crafting_salvage_season import season_board, second_round


def test_portable_championship_package_and_acceptance():
    source, _ = inputs()
    package = build_season_package(source, season_board(), package_id="original_salvage")
    assert verify_season_package(package) == package
    rounds = [actions(), second_round()]
    play = play_season_package(package, rounds, require_complete=True)
    assert verify_season_package_play(play, require_complete=True)["score"] == 36
    acceptance = accept_salvage_season(source, season_board(), rounds)
    assert verify_salvage_season_acceptance(acceptance)["score"] == 36
    assert acceptance == accept_salvage_season(source, season_board(), rounds)


def test_package_refuses_unearned_round_and_tampered_play():
    source, _ = inputs()
    package = build_season_package(source, season_board(), package_id="original_salvage")
    with pytest.raises(HarborError):
        play_season_package(package, [actions()[:4]], require_complete=True)
    play = play_season_package(package, [actions(), second_round()], require_complete=True)
    damaged = deepcopy(play)
    damaged["save"]["score"] += 1000
    damaged["play_digest"] = digest({k: v for k, v in damaged.items()
                                      if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_season_package_play(damaged)


def test_acceptance_rejects_tampered_earned_ending():
    source, _ = inputs()
    accepted = accept_salvage_season(source, season_board(), [actions(), second_round()])
    damaged = deepcopy(accepted)
    damaged["play"]["save"]["reports"][0]["state"]["complete"] = False
    damaged["acceptance_digest"] = digest({k: v for k, v in damaged.items()
                                             if k != "acceptance_digest"})
    with pytest.raises(HarborError):
        verify_salvage_season_acceptance(damaged)
