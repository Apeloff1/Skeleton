"""Original end-to-end playable acceptance across all convoy production planes."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, digest, load_source
from skeleton.game.gameplay.harbor_crafting_convoy_acceptance import (
    accept_convoy, verify_convoy_acceptance,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_convoy.json").read_bytes())
    contracts = decode((FIXTURES / "harbor_lantern_quay_convoy_contracts.json").read_bytes())
    return source, board, contracts


def test_source_to_crafting_combat_quests_journal_package_both_endings():
    source, board, contracts = inputs()
    acceptance = accept_convoy(source, board, contracts)
    result = verify_convoy_acceptance(decode(canonical(acceptance)))
    assert result["verified"] and result["complete"]
    assert result["hull"] == 3 and result["bounty"] == 7
    assert result["contract_points"] == 20
    assert result["relief_reputation"] == 23
    assert result["salvage_credits"] == 27
    assert result["journal_entries"] >= 1


def test_unplayable_source_and_resealed_forged_receipts_fail_closed():
    source, board, contracts = inputs()
    impossible = deepcopy(board)
    impossible["encounters"][0]["strength"] = 2
    with pytest.raises(HarborError):
        accept_convoy(source, impossible, contracts)
    receipt = accept_convoy(source, board, contracts)
    forged = deepcopy(receipt)
    forged["summary"]["bounty"] = 999
    forged["acceptance_digest"] = digest({
        k: v for k, v in forged.items() if k != "acceptance_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_convoy_acceptance(forged)


def test_cli_original_game_acceptance_and_replay_verifier(tmp_path):
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    receipt = call(
        "convoy-accept",
        "--source", str(FIXTURES / "harbor_lantern_quay.json"),
        "--convoy-board", str(FIXTURES / "harbor_lantern_quay_convoy.json"),
        "--convoy-contracts", str(FIXTURES / "harbor_lantern_quay_convoy_contracts.json"),
    )
    path = tmp_path / "acceptance.json"
    path.write_bytes(canonical(receipt))
    assert call(
        "convoy-verify-accept", "--convoy-acceptance", str(path),
    )["verified"]
