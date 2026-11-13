"""Source-bound convoy quests, earned endings and transactional authoring."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy import build_convoy
from skeleton.game.gameplay.harbor_crafting_convoy_contracts import (
    build_convoy_contract_report, verify_convoy_contract_report,
    validate_convoy_contracts, convoy_contract_status,
)
from skeleton.game.gameplay.harbor_crafting_convoy_contract_authoring import (
    edit_convoy_contracts, verify_convoy_contract_revision,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_convoy.json").read_bytes())
    contracts = decode((FIXTURES / "harbor_lantern_quay_convoy_contracts.json").read_bytes())
    actions = demo_actions()[:12] + [
        {"op": "escort"}, {"op": "move", "direction": "east"},
        {"op": "escort"}, {"op": "strike"},
        {"op": "move", "direction": "east"}, {"op": "escort"},
        {"op": "move", "direction": "east"}, {"op": "escort"},
    ]
    return source, board, contracts, actions


def test_earned_contract_chain_and_exclusive_choice_consequences():
    source, board, contracts, actions = inputs()
    convoy = build_convoy(source, board, actions, require_complete=True)
    relief = build_convoy_contract_report(convoy, contracts, choice="relief", require_all=True)
    salvage = build_convoy_contract_report(convoy, contracts, choice="salvage", require_all=True)
    assert relief["complete"] and salvage["complete"]
    assert relief["points"] == 20 and relief["reputation"] == 23 and relief["credits"] == 0
    assert salvage["credits"] == 27 and salvage["reputation"] == 0
    assert [a["id"] for a in relief["awards"]] == [
        "forge_lantern", "first_crossing", "repel_raider",
        "protect_cargo", "dock_delivery",
    ]
    assert verify_convoy_contract_report(decode(canonical(relief)), require_all=True)["complete"]
    assert convoy_contract_status(relief)["remaining"] == []


def test_incomplete_and_defeated_convoy_cannot_claim_ending():
    source, board, contracts, actions = inputs()
    partial = build_convoy(source, board, actions[:15])
    report = build_convoy_contract_report(partial, contracts)
    assert not report["complete"] and "dock_delivery" in convoy_contract_status(report)["remaining"]
    with pytest.raises(HarborError, match="not earned"):
        build_convoy_contract_report(partial, contracts, require_all=True)
    defeated = build_convoy(source, board, actions[:15] + [{"op": "wait"}] * 3)
    assert not build_convoy_contract_report(defeated, contracts)["complete"]


def test_invalid_contract_graph_foreign_target_and_forged_awards():
    source, board, contracts, actions = inputs()
    convoy = build_convoy(source, board, actions)
    for field, value in (
        ("source_id", "foreign"), ("contracts", contracts["contracts"] * 2),
    ):
        bad = deepcopy(contracts)
        bad[field] = value
        with pytest.raises(HarborError):
            validate_convoy_contracts(bad, convoy)
    for bad_target in ("unknown_enemy", "0"):
        bad = deepcopy(contracts)
        bad["contracts"][2 if bad_target == "unknown_enemy" else 1]["target"] = bad_target
        with pytest.raises(HarborError):
            validate_convoy_contracts(bad, convoy)
    original = build_convoy_contract_report(convoy, contracts)
    forged = deepcopy(original)
    forged["credits"] = 999
    forged["report_digest"] = digest({
        k: v for k, v in forged.items() if k != "report_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_convoy_contract_report(forged)


def test_contract_editor_replays_preview_and_rejects_stale_and_tampered_revision():
    source, board, contracts, actions = inputs()
    convoy = build_convoy(source, board, actions)
    report = build_convoy_contract_report(convoy, contracts, choice="salvage")
    edits = [{"id": "dock_delivery", "field": "points", "value": 9}]
    revision = edit_convoy_contracts(
        convoy, contracts, edits, expected_board_digest=digest(contracts),
        preview_report=report,
    )
    assert revision["result"]["credits"] == 29
    assert verify_convoy_contract_revision(decode(canonical(revision)))["preview_complete"]
    with pytest.raises(HarborError, match="stale"):
        edit_convoy_contracts(convoy, contracts, edits, expected_board_digest="0" * 64)
    forged = deepcopy(revision)
    forged["result"]["credits"] = 100
    forged["result"]["report_digest"] = digest({
        k: v for k, v in forged["result"].items() if k != "report_digest"
    })
    forged["revision_digest"] = digest({
        k: v for k, v in forged.items() if k != "revision_digest"
    })
    with pytest.raises(HarborError):
        verify_convoy_contract_revision(forged)


def test_cli_contract_report_status_and_editor(tmp_path):
    source, board, contracts, actions = inputs()
    convoy = build_convoy(source, board, actions)
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        proc = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode()
        return decode(proc.stdout)
    convoy_file = write("convoy", convoy)
    board_file = str(FIXTURES / "harbor_lantern_quay_convoy_contracts.json")
    report = call(
        "convoy-contract-run", "--convoy-report", convoy_file,
        "--convoy-contracts", board_file, "--convoy-choice", "relief", "--require-all",
    )
    report_file = write("contract-report", report)
    assert call(
        "convoy-contract-verify", "--convoy-contract-report", report_file,
        "--require-all",
    )["reputation"] == 23
    assert call(
        "convoy-contract-status", "--convoy-contract-report", report_file,
    )["remaining"] == []
    revision = call(
        "convoy-contract-author", "--convoy-report", convoy_file,
        "--convoy-contracts", board_file,
        "--convoy-contract-edits", write("edits", [
            {"id": "dock_delivery", "field": "points", "value": 9}
        ]),
        "--expected-convoy-contract-digest", digest(contracts),
        "--convoy-contract-report", report_file,
    )
    assert call(
        "convoy-contract-verify-author",
        "--convoy-contract-revision", write("revision", revision),
    )["verified"]
