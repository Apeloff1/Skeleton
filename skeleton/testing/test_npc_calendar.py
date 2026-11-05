"""Playable NPC calendar hints, verified replay, and CLI acceptance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.npc_calendar import forecast_calendar, verify_calendar
from skeleton.game.gameplay.npc_schedule import (
    NpcCommand, NpcSchedule, NpcSession,
)

FIXTURE = Path(__file__).resolve().parents[1] / "testing" / "fixtures" / "lantern_harbor_npc_schedule.json"


def _schedule() -> NpcSchedule:
    return NpcSchedule.parse(json.loads(FIXTURE.read_text()))


def test_original_calendar_exposes_real_authored_stops() -> None:
    schedule = _schedule()
    result = forecast_calendar(schedule, NpcSession.start(schedule))
    assert result["tick"] == 0
    assert result["ending"] == "in_progress"
    assert result["entries"]
    assert result["entries"][0]["npc_id"] == "harbor_council"
    assert result["entries"][0]["availability"] == "available_now"
    assert result["suggestion"]["resulting_ending"] == "harbor_sealed"
    assert verify_calendar(schedule, copy.deepcopy(result)) == result


def test_unlocks_new_npc_interaction_after_actual_player_action() -> None:
    schedule = _schedule()
    session = NpcSession.start(schedule).apply(
        NpcCommand("interact", 0, "mira_keeper", "ask_for_lens", "player")
    )
    result = forecast_calendar(schedule, session)
    sol = next(row for row in result["entries"]
               if row["interaction_id"] == "repair_lens")
    assert sol["missing_facts"] == []
    assert sol["availability"] == "available_now"
    assert verify_calendar(schedule, result) == result


def test_calendar_never_invents_unearned_facts() -> None:
    schedule = _schedule()
    result = forecast_calendar(schedule, NpcSession.start(schedule))
    sol = next(row for row in result["entries"]
               if row["interaction_id"] == "repair_lens")
    assert sol["missing_facts"] == ["lens_request"]
    assert sol["availability"] == "missing_facts"


def test_terminal_npc_story_has_no_future_interaction_hints() -> None:
    schedule = _schedule()
    session = NpcSession.start(schedule).apply(
        NpcCommand("interact", 0, "harbor_council", "seal_harbor", "player")
    )
    result = forecast_calendar(schedule, session)
    assert result["ending"] == "harbor_sealed"
    assert result["entries"] == []
    assert result["suggestion"] is None


def test_truncated_calendar_does_not_claim_complete_coverage() -> None:
    schedule = _schedule()
    result = forecast_calendar(schedule, NpcSession.start(schedule), max_entries=1)
    assert result["truncated"] is True
    assert len(result["entries"]) == 1
    assert verify_calendar(schedule, result) == result


def test_invalid_limit_and_player_identity_rejected() -> None:
    schedule = _schedule()
    for limit in (0, 129, True):
        with pytest.raises(GameplayContractError):
            forecast_calendar(schedule, NpcSession.start(schedule), max_entries=limit)
    with pytest.raises(GameplayContractError):
        forecast_calendar(schedule, NpcSession.start(schedule), player_id="../bad")


def test_forged_facts_or_calendar_suggestion_rejected() -> None:
    schedule = _schedule()
    session = NpcSession.start(schedule)
    original = forecast_calendar(schedule, session)
    for field in ("facts", "suggestion", "checksum"):
        forged = copy.deepcopy(original)
        if field == "facts":
            forged[field].append("beacon_lit")
        elif field == "suggestion":
            forged[field]["resulting_ending"] = "harbor_restored"
        else:
            forged[field] = "0" * 64
        with pytest.raises(GameplayContractError):
            verify_calendar(schedule, forged)


def test_recomputed_checksum_does_not_authorize_forged_snapshot() -> None:
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    schedule = _schedule()
    forged = forecast_calendar(schedule, NpcSession.start(schedule))
    forged["snapshot"]["state_digest"] = "0" * 64
    forged["checksum"] = dig({
        key: value for key, value in forged.items() if key != "checksum"
    })
    with pytest.raises(GameplayContractError):
        verify_calendar(schedule, forged)


def test_source_identity_mismatch_rejected() -> None:
    schedule = _schedule()
    raw = schedule.as_dict()
    raw["world_id"] = "another_world"
    other = NpcSchedule.parse(raw)
    result = forecast_calendar(schedule, NpcSession.start(schedule))
    with pytest.raises(GameplayContractError):
        verify_calendar(other, result)


def test_cli_calendar_and_verify_from_original_fixture(tmp_path: Path) -> None:
    report = tmp_path / "calendar.json"
    command = [sys.executable, "-m", "scripts.npc_schedule_cli",
               "--schedule", str(FIXTURE)]
    first = subprocess.run(
        command + ["--calendar"], capture_output=True, text=True,
    )
    assert first.returncode == 0, first.stderr
    report.write_text(first.stdout)
    verified = subprocess.run(
        command + ["--verify-calendar", str(report)],
        capture_output=True, text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(first.stdout) == json.loads(verified.stdout)


def test_cli_rejects_calendar_conflicting_playback_options() -> None:
    command = [sys.executable, "-m", "scripts.npc_schedule_cli",
               "--schedule", str(FIXTURE)]
    rejected = subprocess.run(
        command + ["--calendar", "--interactive"],
        capture_output=True, text=True,
    )
    assert rejected.returncode == 2
