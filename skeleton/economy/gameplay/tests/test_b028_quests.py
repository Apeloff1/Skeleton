"""B028: governed quest-reward faucet."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.quests import QuestBoard, QuestSpec
from skeleton.economy.gameplay.tests.conftest import build_econ
from skeleton.simulation.economy.sim import EconomySimError


def _board(econ):
    return QuestBoard(
        econ,
        [
            QuestSpec("intro", reward_faucet="bounty", reward_items={"herb": 2}),
            QuestSpec("smith", reward_faucet="daily", reward_items={"sword": 1}, prerequisites=("intro",)),
            QuestSpec("patrol", reward_faucet="bounty", repeat_ticks=50),
        ],
    )


def test_quest_pays_once_and_respects_prerequisites():
    econ = build_econ()
    board = _board(econ)
    with pytest.raises(EconomySimError, match="prerequisites"):
        board.complete("ana", "smith", tick=0)
    assert board.complete("ana", "intro", tick=0) == {"money": 100, "items": {"herb": 2}}
    with pytest.raises(EconomySimError, match="already completed"):
        board.complete("ana", "intro", tick=1)
    board.complete("ana", "smith", tick=2)
    assert econ.balance("ana", "gold") == 1_100
    assert econ.item_report("sword")["by_source"] == {"quest:smith": 1}


def test_repeatable_quest_window():
    econ = build_econ()
    board = _board(econ)
    board.complete("bo", "patrol", tick=0)
    with pytest.raises(EconomySimError, match="not yet repeatable"):
        board.complete("bo", "patrol", tick=49)
    board.complete("bo", "patrol", tick=50)
    with pytest.raises(EconomySimError, match="backwards"):
        board.complete("bo", "patrol", tick=10)
    assert econ.balance("bo", "gold") == 200


def test_refused_claim_pays_nothing():
    econ = build_econ(slots=1)
    board = _board(econ)
    econ.grant_items("x", "ana", "ore", 1)
    with pytest.raises(EconomySimError, match="inventory full"):
        board.complete("ana", "intro", tick=0)
    assert econ.balance("ana", "gold") == 0 and not board.completed("ana", "intro")
    capped = build_econ(cap=50)
    board2 = _board(capped)
    with pytest.raises(EconomySimError, match="supply cap"):
        board2.complete("ana", "patrol", tick=0)
    assert not board2.completed("ana", "patrol")


def test_board_validation():
    econ = build_econ()
    with pytest.raises(EconomySimError, match="cycle"):
        QuestBoard(econ, [QuestSpec("a", prerequisites=("b",)), QuestSpec("b", prerequisites=("a",))])
    with pytest.raises(EconomySimError, match="unknown prerequisite"):
        QuestBoard(econ, [QuestSpec("a", prerequisites=("zzz",))])
    with pytest.raises(EconomySimError, match="unknown faucet"):
        QuestBoard(econ, [QuestSpec("a", reward_faucet="nope")])
    with pytest.raises(EconomySimError, match="itself"):
        QuestSpec("a", prerequisites=("a",))
