"""Source-to-quest event chain, prerequisite and adversarial replay tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_patrol import build_patrol
from skeleton.game.gameplay.harbor_crafting_patrol_quests import (
    build_patrol_quests, validate_patrol_quest_board, verify_patrol_quests,
)
from skeleton.game.gameplay.harbor_crafting_patrol_cli import main
from skeleton.testing.test_harbor_crafting_patrol import inputs, actions

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def inputs_with_quests():
    source, board = inputs()
    patrol = build_patrol(source, board, actions(), require_complete=True)
    quests = json.loads((FIXTURES / "harbor_lantern_quay_patrol_quests.json").read_text())
    return patrol, quests


def test_five_earned_quests_and_full_event_chain():
    patrol, quests = inputs_with_quests()
    ledger = build_patrol_quests(patrol, quests, require_all=True)
    status = verify_patrol_quests(ledger, require_all=True)
    assert status["reward"] == 30
    assert status["completed"] == [
        "recover_registry", "forge_lantern", "secure_manifest",
        "dock_delivery", "quiet_extraction",
    ]
    assert [event["sequence"] for event in ledger["events"]] == list(range(5))
    assert ledger == build_patrol_quests(patrol, quests, require_all=True)


def test_partial_source_cannot_claim_unearned_quests():
    source, board = inputs()
    patrol = build_patrol(source, board, actions()[:4])
    quests = json.loads((FIXTURES / "harbor_lantern_quay_patrol_quests.json").read_text())
    ledger = build_patrol_quests(patrol, quests)
    assert ledger["completed"] == ["recover_registry"]
    with pytest.raises(HarborError, match="not earned"):
        build_patrol_quests(patrol, quests, require_all=True)


@pytest.mark.parametrize("mutate", [
    lambda q: q["quests"][1].update(requires=["quiet_extraction"]),
    lambda q: q["quests"][0].update(trigger="admin"),
    lambda q: q["quests"][0].update(target="not_an_objective"),
    lambda q: q["quests"][2].update(id="recover_registry"),
    lambda q: q["quests"][2].update(reward=True),
    lambda q: q.update(patrol_board_digest="0" * 64),
])
def test_hostile_quest_board_rejected(mutate):
    patrol, quests = inputs_with_quests()
    mutate(quests)
    with pytest.raises(HarborError):
        validate_patrol_quest_board(quests, patrol)


def test_forged_event_with_recomputed_outer_digest_rejected():
    patrol, quests = inputs_with_quests()
    ledger = build_patrol_quests(patrol, quests)
    forged = deepcopy(ledger)
    forged["events"][0]["reward"] = 99
    forged["ledger_digest"] = digest({k: v for k, v in forged.items()
                                       if k != "ledger_digest"})
    with pytest.raises(HarborError):
        verify_patrol_quests(forged)


def test_quest_cli_source_to_ledger_roundtrip(tmp_path, capsys):
    patrol, quests = inputs_with_quests()
    path = tmp_path / "patrol.json"
    path.write_text(json.dumps(patrol))
    assert main(["quest-run", "--report", str(path), "--require-all"]) == 0
    ledger = json.loads(capsys.readouterr().out)
    out = tmp_path / "quests.json"
    out.write_text(json.dumps(ledger))
    assert main(["quest-verify", "--quest-ledger", str(out), "--require-all"]) == 0
    assert json.loads(capsys.readouterr().out)["reward"] == 30
