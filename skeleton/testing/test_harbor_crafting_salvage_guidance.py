"""NPC-aware bounded legal-action hints and earned salvage contract scoring."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage import build_salvage
from skeleton.game.gameplay.harbor_crafting_salvage_guidance import (
    build_salvage_guidance, verify_salvage_guidance,
)
from skeleton.game.gameplay.harbor_crafting_salvage_contracts import (
    build_salvage_contract_report, verify_salvage_contract_report,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def contract_board():
    return json.loads((FIXTURES / "harbor_lantern_quay_salvage_contracts.json").read_text())


def test_legal_hint_is_earned_and_deterministic():
    source, board = inputs()
    report = build_salvage(source, board, [])
    guidance = build_salvage_guidance(report, horizon=8)
    assert guidance["recommended"] == {"op": "move", "direction": "east"}
    assert guidance["recommended"] in guidance["legal_actions"]
    assert verify_salvage_guidance(guidance)["goal"] == "salvage:wrecked_skiff"
    assert guidance == build_salvage_guidance(report, horizon=8)


def test_terminal_guidance_has_no_legal_actions():
    source, board = inputs()
    report = build_salvage(source, board, actions(), require_complete=True)
    guidance = build_salvage_guidance(report)
    assert guidance["legal_actions"] == []
    assert guidance["recommended"] is None


def test_hint_tampering_even_with_resealed_digest_fails():
    source, board = inputs()
    guidance = build_salvage_guidance(build_salvage(source, board, []))
    damaged = deepcopy(guidance)
    damaged["legal_actions"].append({"op": "rescue"})
    damaged["guidance_digest"] = digest({k: v for k, v in damaged.items()
                                          if k != "guidance_digest"})
    with pytest.raises(HarborError):
        verify_salvage_guidance(damaged)


def test_contracts_require_replay_earned_site_and_ending():
    source, board = inputs()
    report = build_salvage(source, board, actions(), require_complete=True)
    contracts = build_salvage_contract_report(report, contract_board(), require_all=True)
    result = verify_salvage_contract_report(contracts, require_all=True)
    assert result["score"] == 55
    assert len(result["earned"]) == 6
    assert contracts["events"][-1]["objectives"] == ["signal_rescue"]


def test_contracts_refuse_unearned_and_resealed_scores():
    source, board = inputs()
    report = build_salvage(source, board, actions()[:4])
    with pytest.raises(HarborError, match="not earned"):
        build_salvage_contract_report(report, contract_board(), require_all=True)
    completed = build_salvage_contract_report(
        build_salvage(source, board, actions()), contract_board())
    damaged = deepcopy(completed)
    damaged["score"] += 100
    damaged["contract_digest"] = digest({k: v for k, v in damaged.items()
                                          if k != "contract_digest"})
    with pytest.raises(HarborError):
        verify_salvage_contract_report(damaged)


def test_contract_rejects_unrecognized_site_and_duplicate_objective():
    source, board = inputs()
    report = build_salvage(source, board, [])
    invalid = contract_board()
    invalid["objectives"][0]["target"] = "not_in_world"
    with pytest.raises(HarborError):
        build_salvage_contract_report(report, invalid)
    invalid = contract_board()
    invalid["objectives"][1]["id"] = invalid["objectives"][0]["id"]
    with pytest.raises(HarborError):
        build_salvage_contract_report(report, invalid)
