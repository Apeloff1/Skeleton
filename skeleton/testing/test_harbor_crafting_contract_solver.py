"""Deterministic bounded route solving for earned contracts and CAS custody."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_contracts import build_save, verify_save
from skeleton.game.gameplay.harbor_crafting_contract_solver import (
    solve_contract, verify_contract_plan,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def start():
    source = load_source(ROOT / "harbor_lantern_quay.json")
    board = decode((ROOT / "harbor_lantern_quay_contracts.json").read_bytes())
    return build_save(source, board, [])


def test_source_to_bounded_plan_real_actions_and_portable_replay():
    root = start()
    result = solve_contract(root)
    assert result["order_id"] == "beacon_supply"
    assert result["plan"]["bundle"]["state"]["ending"] == "beacon"
    assert verify_save(result["after"])["next_order"] == 1
    assert verify_contract_plan(decode(canonical(result)))["next_order"] == 1
    assert canonical(result) == canonical(solve_contract(root))


def test_two_consequences_are_earned_by_real_planner():
    first = solve_contract(start())
    second = solve_contract(first["after"])
    assert second["order_id"] == "shelter_relief"
    assert second["after"]["complete"]
    assert second["plan"]["bundle"]["state"]["ending"] == "safe_harbor"
    assert verify_contract_plan(second)["complete"]
    with pytest.raises(HarborError, match="no pending"):
        solve_contract(second["after"])


@pytest.mark.parametrize("field", ["order_id", "after_digest", "plan"])
def test_resealed_forgery_does_not_override_replay(field):
    original = solve_contract(start())
    forged = deepcopy(original)
    if field == "order_id":
        forged["order_id"] = "wrong"
    elif field == "after_digest":
        forged["after_digest"] = "0" * 64
    else:
        forged["plan"]["actions"][0] = {"op": "wait"}
    forged["plan_digest"] = digest({k: v for k, v in forged.items() if k != "plan_digest"})
    with pytest.raises(HarborError):
        verify_contract_plan(forged)


def test_unreachable_contract_fails_closed_without_fake_plan():
    root = start()
    root["board"]["orders"][0]["rules"]["min_trades"] = 1
    root = build_save(root["source"], root["board"], [])
    with pytest.raises(HarborError, match="activity not earned"):
        solve_contract(root)


def test_cli_plan_export_and_verification(tmp_path):
    root = start()
    path = tmp_path / "save.json"
    path.write_bytes(canonical(root))
    run = subprocess.run(CLI + ["contract-plan", "--contract-save", str(path)],
                         capture_output=True, check=False)
    assert run.returncode == 0, run.stderr.decode()
    plan = decode(run.stdout)
    path.write_bytes(canonical(plan))
    check = subprocess.run(CLI + ["contract-verify-plan", "--contract-plan", str(path)],
                           capture_output=True, check=False)
    assert check.returncode == 0, check.stderr.decode()
    assert decode(check.stdout)["verified"]
