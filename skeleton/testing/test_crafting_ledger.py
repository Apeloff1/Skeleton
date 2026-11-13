"""Canonical crafting provenance, conservation and installed CLI acceptance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.crafting_ledger import (
    inspect_ledger, verify_ledger,
)
from skeleton.game.gameplay.crafting_runtime import (
    CraftAction, CraftEngine, CraftPlan, CraftRecipe, GameplayContractError,
)


def _plan() -> CraftPlan:
    return CraftPlan(
        "lantern_harbor",
        (
            CraftRecipe("make_wick", (("fiber", 2),), (("wick", 1),), 1,
                        (), ("wick_known",)),
            CraftRecipe("build_lantern", (("wick", 1), ("oil", 1)),
                        (("lantern", 1),), 3,
                        ("wick_known",), ("light_available",)),
        ),
        (("fiber", 4), ("oil", 2)), 10,
    )


def _save() -> dict[str, object]:
    engine = CraftEngine(_plan())
    return engine.replay([
        CraftAction(0, "make_wick"),
        CraftAction(1, "build_lantern"),
    ]).save_record()


def test_real_ingredient_and_currency_provenance() -> None:
    engine = CraftEngine(_plan())
    report = inspect_ledger(engine, _save())
    assert report["total_currency_spent"] == 4
    assert report["total_consumed"] == [
        ["fiber", 2], ["oil", 1], ["wick", 1],
    ]
    assert report["total_produced"] == [["lantern", 1], ["wick", 1]]
    assert report["events"][0]["new_flags"] == ["wick_known"]
    assert report["events"][1]["new_flags"] == ["light_available"]
    assert report["events"][1]["currency_after"] == 6
    assert verify_ledger(engine, json.loads(json.dumps(report))) == report


def test_event_receipts_bind_actual_inventory_deltas() -> None:
    report = inspect_ledger(CraftEngine(_plan()), _save())
    assert report["events"][0]["inventory_delta"] == [
        ["fiber", -2], ["wick", 1],
    ]
    assert report["events"][1]["inventory_delta"] == [
        ["lantern", 1], ["oil", -1], ["wick", -1],
    ]
    assert report["events"][0]["before_digest"] == report["initial_state_digest"]
    assert report["events"][-1]["after_digest"] == report["final_state_digest"]


def test_empty_crafting_history_has_no_fabricated_spend() -> None:
    engine = CraftEngine(_plan())
    report = inspect_ledger(engine, engine.start().save_record())
    assert report["events"] == []
    assert report["total_currency_spent"] == 0
    assert report["total_consumed"] == []
    assert report["total_produced"] == []
    assert verify_ledger(engine, report) == report


def test_forged_event_or_summary_is_rejected() -> None:
    engine = CraftEngine(_plan())
    original = inspect_ledger(engine, _save())
    for field in ("events", "total_currency_spent", "checksum"):
        report = copy.deepcopy(original)
        if field == "events":
            report[field][0]["currency_spent"] = 0
        elif field == "total_currency_spent":
            report[field] = 0
        else:
            report[field] = "0" * 64
        with pytest.raises(GameplayContractError):
            verify_ledger(engine, report)


def test_recomputed_checksum_cannot_authorize_forged_save() -> None:
    from skeleton.game.gameplay.crafting_runtime import _digest
    engine = CraftEngine(_plan())
    report = inspect_ledger(engine, _save())
    report["save"]["state"]["currency"] = 999
    report["checksum"] = _digest({
        key: value for key, value in report.items() if key != "checksum"
    })
    with pytest.raises(GameplayContractError):
        verify_ledger(engine, report)


def test_different_plan_cannot_reuse_ledger() -> None:
    report = inspect_ledger(CraftEngine(_plan()), _save())
    other = CraftPlan("different_world", _plan().recipes,
                      _plan().initial_inventory, 10)
    with pytest.raises(GameplayContractError):
        verify_ledger(CraftEngine(other), report)


def test_batch_actions_account_for_actual_multiplier() -> None:
    engine = CraftEngine(_plan())
    save = engine.replay([CraftAction(0, "make_wick", 2)]).save_record()
    report = inspect_ledger(engine, save)
    assert report["total_currency_spent"] == 2
    assert report["total_consumed"] == [["fiber", 4]]
    assert report["total_produced"] == [["wick", 2]]
    assert verify_ledger(engine, report) == report


def test_unknown_fields_and_nonfinite_values_fail_closed() -> None:
    engine = CraftEngine(_plan())
    report = inspect_ledger(engine, _save())
    report["extra"] = "untrusted"
    with pytest.raises(GameplayContractError):
        verify_ledger(engine, report)
    report = inspect_ledger(engine, _save())
    report["total_currency_spent"] = float("nan")
    with pytest.raises(GameplayContractError):
        verify_ledger(engine, report)


def test_installed_crafting_cli_ledger_and_verification(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    save = tmp_path / "save.json"
    report = tmp_path / "ledger.json"
    plan.write_text(json.dumps(_plan().record()))
    save.write_text(json.dumps(_save()))
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli"]
    output = subprocess.run(
        command + ["ledger", "--plan", str(plan), "--save", str(save)],
        capture_output=True, text=True,
    )
    assert output.returncode == 0, output.stderr
    report.write_text(output.stdout)
    result = subprocess.run(
        command + ["verify-ledger", "--plan", str(plan), "--report", str(report)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["checksum"] == json.loads(output.stdout)["checksum"]


def test_cli_rejects_missing_report_and_untrusted_extra_options(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(_plan().record()))
    command = [sys.executable, "-m", "skeleton.game.gameplay.crafting_cli"]
    missing = subprocess.run(
        command + ["verify-ledger", "--plan", str(plan)],
        capture_output=True, text=True,
    )
    assert missing.returncode == 2
    extra = subprocess.run(
        command + ["inspect", "--plan", str(plan), "--report", str(plan)],
        capture_output=True, text=True,
    )
    assert extra.returncode == 2
