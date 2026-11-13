"""Revisioned offline input profile publication and source-bound resume."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from skeleton.game.presentation.input_router import InputProfile, InputSession

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "skeleton/game/presentation/fixtures/original_campaign_controls.json"
COMMAND = [sys.executable, "-m", "scripts.game.route_inputs"]


def event(identifier: str, sequence: int) -> dict[str, object]:
    return {
        "event_id": identifier, "sequence": sequence,
        "device_class": "keyboard", "control_path": "KeyD",
        "modifiers": [], "pressed": True,
    }


def test_atomic_profile_rebind_persists_and_reloads(tmp_path: Path) -> None:
    target = tmp_path / "remapped.json"
    command = COMMAND + [
        "--profile", str(PROFILE), "--rebind", "keyboard-east",
        "--control", "ArrowRight", "--revision", "0",
        "--out-profile", str(target),
    ]
    first = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert first.returncode == 0, first.stderr
    revised = InputProfile.load(json.loads(target.read_text()))
    assert revised.revision == 1
    assert revised.digest == json.loads(first.stdout)["digest"]
    again = subprocess.run(command, capture_output=True, timeout=20)
    assert again.returncode == 2
    assert InputProfile.load(json.loads(target.read_text())).digest == revised.digest


def test_resume_canonical_input_event_replay_without_mutating_prior_save(tmp_path: Path) -> None:
    first_events = tmp_path / "first-events.json"
    second_events = tmp_path / "second-events.json"
    first_save = tmp_path / "first-session.json"
    second_save = tmp_path / "second-session.json"
    first_events.write_text(json.dumps([event("one", 0)]))
    second_events.write_text(json.dumps([event("two", 1)]))
    command = COMMAND + ["--profile", str(PROFILE)]
    first = subprocess.run(
        command + ["--events", str(first_events), "--out-session", str(first_save)],
        capture_output=True, text=True, timeout=20,
    )
    assert first.returncode == 0, first.stderr
    before = first_save.read_bytes()
    second = subprocess.run(
        command + ["--events", str(second_events), "--resume", str(first_save),
                   "--out-session", str(second_save)],
        capture_output=True, text=True, timeout=20,
    )
    assert second.returncode == 0, second.stderr
    profile = InputProfile.load(json.loads(PROFILE.read_text()))
    restored = InputSession.restore(profile, json.loads(second_save.read_text()))
    assert len(restored.events) == 2
    assert first_save.read_bytes() == before
    assert restored.events[-1]["command"] == {"kind": "move", "target": "east"}


def test_duplicate_json_keys_and_nonfinite_input_are_rejected(tmp_path: Path) -> None:
    events = tmp_path / "bad-events.json"
    for text in ('[{"event_id":"x","event_id":"y"}]', '[NaN]', '[Infinity]'):
        events.write_text(text)
        result = subprocess.run(
            COMMAND + ["--profile", str(PROFILE), "--events", str(events)],
            capture_output=True, timeout=20,
        )
        assert result.returncode == 2


def test_session_resume_cannot_be_used_with_rebind(tmp_path: Path) -> None:
    source = tmp_path / "forged.json"
    source.write_text("{}")
    result = subprocess.run(
        COMMAND + ["--profile", str(PROFILE), "--rebind", "keyboard-east",
                   "--control", "ArrowRight", "--revision", "0",
                   "--resume", str(source)],
        capture_output=True, timeout=20,
    )
    assert result.returncode == 2
