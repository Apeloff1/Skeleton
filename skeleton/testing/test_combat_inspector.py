"""Actual canonical combat replay diagnostics, comparison and CLI acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_inspector import (
    cli, compare_sessions, inspect_session,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, original_demo, simulate,
)


def _full():
    source, actions = original_demo()
    return simulate(source, actions)


def test_timeline_reconstructs_authoritative_damage_and_winner() -> None:
    snapshot = _full()
    report = inspect_session(snapshot)
    assert report["source_digest"] == snapshot["source_digest"]
    assert report["state_digest"] == snapshot["state_digest"]
    assert report["event_bus_digest"] == snapshot["event_bus_digest"]
    assert report["turn_count"] == 3
    assert report["phase"] == "won"
    assert report["winner"] == "wayfarers"
    assert [turn["turn"] for turn in report["timeline"]] == [0, 1, 2]
    first = report["timeline"][0]
    assert first["changes"]["warden"]["hp_before"] == 7
    assert first["changes"]["warden"]["hp_after"] == 3
    assert first["action"]["actor_id"] == "scout"
    assert report["timeline"][-1]["changes"]["warden"]["hp_after"] == 0


def test_branch_comparison_reports_identical_prefix_and_divergence() -> None:
    source, actions = original_demo()
    left = simulate(source, actions[:2])
    full = simulate(source, actions)
    alternate = simulate(source, [
        {"kind": "guard", "actor_id": "scout"},
        {"kind": "attack", "actor_id": "warden", "target_id": "scout"},
    ])
    assert compare_sessions(left, copy.deepcopy(left))["relationship"] == "identical"
    prefix = compare_sessions(left, full)
    assert prefix["relationship"] == "prefix"
    assert prefix["common_turns"] == 2
    assert prefix["first_divergent_turn"] is None
    divergent = compare_sessions(left, alternate)
    assert divergent["relationship"] == "divergent"
    assert divergent["first_divergent_turn"] == 0
    assert divergent["common_turns"] == 0


def test_inspector_fails_closed_on_forged_state_or_receipt() -> None:
    for path in ("state", "receipt", "source"):
        snapshot = _full()
        if path == "state":
            snapshot["state"]["actors"]["scout"]["hp"] = 999
        elif path == "receipt":
            snapshot["journal"][0]["receipt"] = "0" * 64
        else:
            snapshot["source_digest"] = "0" * 64
        with pytest.raises(CombatSessionError):
            inspect_session(snapshot)


def test_comparison_rejects_different_authored_source() -> None:
    left = _full()
    source, actions = original_demo()
    source["encounter_id"] = "different"
    right = simulate(source, actions)
    with pytest.raises(CombatSessionError, match="different authored"):
        compare_sessions(left, right)


def test_inspector_rejects_extra_fields_and_malformed_journal() -> None:
    snapshot = _full()
    snapshot["unexpected"] = "data"
    with pytest.raises(CombatSessionError):
        inspect_session(snapshot)
    snapshot = _full()
    snapshot["journal"][0]["action"]["kind"] = "eval"
    with pytest.raises(CombatSessionError):
        inspect_session(snapshot)


def test_inspector_cli_roundtrip_and_comparison(capsys) -> None:
    source, actions = original_demo()
    first = simulate(source, actions[:1])
    final = simulate(source, actions)
    assert cli(["inspect", "--session-json", json.dumps(final)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["turn_count"] == 3
    assert cli([
        "compare", "--left-json", json.dumps(first),
        "--right-json", json.dumps(final),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["relationship"] == "prefix"
    assert report["common_turns"] == 1


def test_inspector_cli_invalid_json_returns_nonzero(capsys) -> None:
    assert cli(["inspect", "--session-json", "{"]) == 2
    report = json.loads(capsys.readouterr().err)
    assert report["ok"] is False


def test_authored_actor_order_does_not_affect_diagnostic_timeline() -> None:
    source, actions = original_demo()
    reverse = copy.deepcopy(source)
    reverse["actors"].reverse()
    assert inspect_session(simulate(source, actions)) == inspect_session(
        simulate(reverse, actions),
    )
