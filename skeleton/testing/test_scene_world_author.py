"""Canonical playable scene editor integration, atomicity and replay tests."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, new_session, original_demo, resume_session,
)
from skeleton.game.gameplay.scene_world_author import (
    SCHEMA, author_world, verify_authoring_report,
)


def _expansion():
    return [
        {"kind": "add_scene", "scene": {
            "id": "lighthouse", "ending": None, "pickups": [],
            "exits": [{"id": "back", "to": "quay", "requires_item": None}],
        }},
        {"kind": "add_exit", "scene_id": "quay", "exit": {
            "id": "east", "to": "lighthouse", "requires_item": None,
        }},
    ]


def test_edit_produces_playable_verified_world() -> None:
    original, _ = original_demo()
    source_copy = copy.deepcopy(original)
    report = author_world(original, _expansion())
    assert original == source_copy
    assert report["schema_version"] == SCHEMA
    assert report["before_digest"] != report["after_digest"]
    assert report["preview"]["status"] == "found"
    assert verify_authoring_report(json.loads(json.dumps(report))) == report
    actions = report["preview"]["actions"]
    session = resume_session(new_session(report["after_source"]), actions)
    assert session["state"]["phase"] == "won"
    assert session["state_digest"] == report["preview"]["final_state_digest"]


def test_atomic_multistep_retarget_and_remove() -> None:
    original, _ = original_demo()
    edits = [
        {"kind": "remove_exit", "scene_id": "quay", "exit_id": "down"},
        {"kind": "remove_scene", "scene_id": "sinkhole"},
    ]
    report = author_world(original, edits)
    assert "sinkhole" not in {s["id"] for s in report["after_source"]["scenes"]}
    assert report["preview"]["status"] == "found"
    assert verify_authoring_report(report) == report


def test_atomic_reject_dangling_exit_and_preserve_input() -> None:
    original, _ = original_demo()
    before = copy.deepcopy(original)
    with pytest.raises(SceneTravelError, match="destination"):
        author_world(original, [
            {"kind": "remove_scene", "scene_id": "sinkhole"},
        ])
    assert original == before


def test_reject_dangling_item_requirement() -> None:
    original, _ = original_demo()
    with pytest.raises(SceneTravelError, match="item"):
        author_world(original, [
            {"kind": "remove_pickup", "scene_id": "quay",
             "pickup_id": "find_key"},
        ])


def test_reject_duplicate_scene_and_exit() -> None:
    original, _ = original_demo()
    with pytest.raises(SceneTravelError, match="duplicate"):
        author_world(original, _expansion() + _expansion())


def test_set_limit_changes_canonical_source() -> None:
    original, _ = original_demo()
    report = author_world(original, [
        {"kind": "set_step_limit", "step_limit": 6},
    ])
    assert report["after_source"]["step_limit"] == 6
    assert verify_authoring_report(report) == report


@pytest.mark.parametrize("edits", [
    [],
    [{"kind": "unknown"}],
    [{"kind": "set_step_limit", "step_limit": True}],
    [{"kind": "set_step_limit", "step_limit": 999}],
    [{"kind": "set_start", "scene_id": "absent"}],
    [{"kind": "remove_scene", "scene_id": "quay"}],
    [{"kind": "remove_exit", "scene_id": "quay", "exit_id": "missing"}],
    [{"kind": "add_exit", "scene_id": "quay",
      "exit": {"id": "north", "to": "gate", "requires_item": "brass_key"}}],
])
def test_invalid_edits_fail_closed(edits) -> None:
    original, _ = original_demo()
    with pytest.raises(SceneTravelError):
        author_world(original, edits)


@pytest.mark.parametrize("key,value", [
    ("checksum", "0" * 64),
    ("edit_count", 999),
    ("after_digest", "0" * 64),
    ("preview", {"status": "found"}),
    ("edits", []),
])
def test_tampered_receipts_denied(key, value) -> None:
    original, _ = original_demo()
    report = author_world(original, _expansion())
    report[key] = value
    with pytest.raises(SceneTravelError):
        verify_authoring_report(report)


def test_cli_demo_and_verify_end_to_end() -> None:
    run = subprocess.run(
        [sys.executable, "-m", "skeleton", "scene-author", "demo"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    verify = subprocess.run(
        [sys.executable, "-m", "skeleton", "scene-author", "verify",
         "--report-json", json.dumps(report)],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout) == report


def test_cli_denies_invalid_source_without_traceback() -> None:
    run = subprocess.run(
        [sys.executable, "-m", "skeleton", "scene-author", "edit",
         "--world-json", '{"invalid":true}',
         "--edits-json", '[{"kind":"set_step_limit","step_limit":4}]'],
        capture_output=True, text=True, check=False, timeout=15,
    )
    assert run.returncode == 2
    assert json.loads(run.stderr)["ok"] is False
    assert "Traceback" not in run.stderr
