"""NPC ending coverage from canonical authored routes and replay."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.npc_schedule import NpcSchedule, NpcSession, play
from skeleton.game.gameplay.npc_ending_coverage import (
    SCHEMA, audit_endings, verify_coverage,
)


def _fixture() -> Path:
    return Path(__file__).parent / "fixtures/lantern_harbor_npc_schedule.json"


def _schedule() -> NpcSchedule:
    return NpcSchedule.parse(json.loads(_fixture().read_text(encoding="utf-8")))


def test_all_original_harbor_endings_have_real_witnesses() -> None:
    schedule = _schedule()
    report = audit_endings(schedule)
    assert report["schema_version"] == SCHEMA
    assert report["counts"]["solved"] == 2
    assert report["counts"]["inconclusive"] == 0
    assert report["all_endings_playable"]
    for row in report["endings"]:
        replay = play(schedule, row["commands"])
        assert replay.ending == row["ending_id"]
        assert replay.state_digest == row["state_digest"]
        assert (NpcSession.restore(schedule, row["snapshot"]).state_digest
                == replay.state_digest)
    assert verify_coverage(schedule, json.loads(json.dumps(report))) == report


def test_audit_deterministic_and_source_bound() -> None:
    schedule = _schedule()
    first = audit_endings(schedule)
    second = audit_endings(NpcSchedule.parse(schedule.as_dict()))
    assert first == second
    assert first["schedule_digest"] == schedule.digest


def test_small_budget_does_not_forge_unreachable_endings() -> None:
    report = audit_endings(_schedule(), max_nodes=1)
    assert report["counts"]["inconclusive"] >= 1
    assert not report["coverage_complete"]
    assert verify_coverage(_schedule(), report) == report


@pytest.mark.parametrize("field,value", [
    ("max_nodes", 0), ("max_nodes", True), ("max_nodes", 4097),
    ("max_depth", 0), ("max_depth", 65), ("max_depth", 1.5),
])
def test_invalid_audit_budget_rejected(field, value) -> None:
    with pytest.raises(GameplayContractError):
        audit_endings(_schedule(), **{field: value})


@pytest.mark.parametrize("key,value", [
    ("checksum", "0" * 64),
    ("all_endings_playable", False),
    ("counts", {"solved": 2, "unreachable": 0, "inconclusive": 0}),
    ("player_id", "forged_player"),
])
def test_tampered_coverage_rejected(key, value) -> None:
    schedule = _schedule()
    report = audit_endings(schedule)
    report[key] = value
    with pytest.raises(GameplayContractError):
        verify_coverage(schedule, report)


def test_source_mismatch_rejected() -> None:
    schedule = _schedule()
    report = audit_endings(schedule)
    raw = schedule.as_dict()
    raw["horizon_ticks"] += 1
    with pytest.raises(GameplayContractError, match="source"):
        verify_coverage(NpcSchedule.parse(raw), report)


def test_cli_audit_endings() -> None:
    run = subprocess.run([
        sys.executable, "scripts/npc_schedule_cli.py",
        "--schedule", str(_fixture()), "--audit-endings",
    ], capture_output=True, text=True, check=False, timeout=15)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["all_endings_playable"]
    assert verify_coverage(_schedule(), report) == report
