"""Adversarial JSON command boundaries for the actual consumer entrypoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from skeleton.game.gameplay.ridge_rescue.consumer_cli import _strict_action_json
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_nested_action_rejected_without_recursion_escape():
    payload = '{"verb":' + "[" * 1500 + "0" + "]" * 1500 + "}"
    try:
        _strict_action_json(payload)
    except ValueError as exc:
        assert "nesting" in str(exc)
    else:
        raise AssertionError("deep action unexpectedly accepted")


def test_nested_subprocess_command_preserves_save_and_allows_next_turn(tmp_path: Path):
    home = tmp_path / "private"
    env = dict(os.environ, XDG_DATA_HOME=str(home), LOCALAPPDATA=str(home))
    module = "skeleton.game.gameplay.ridge_rescue.consumer_cli"

    def invoke(*args: str):
        return subprocess.run(
            [sys.executable, "-m", module, *args, "--slot", "nested"],
            capture_output=True, text=True, env=env, timeout=25, check=False,
        )

    created = invoke("new")
    assert created.returncode == 0, created.stderr
    state = json.loads(created.stdout)
    payload = '{"verb":' + "[" * 1500 + "0" + "]" * 1500 + "}"
    rejected = invoke("step", "--action", payload, "--expected-head", state["head"])
    assert rejected.returncode == 2
    assert "nesting" in rejected.stderr
    assert "Traceback" not in rejected.stderr

    unchanged = invoke("status")
    assert unchanged.returncode == 0
    assert json.loads(unchanged.stdout)["head"] == state["head"]
    action = state["actions"][0]
    accepted = invoke("step", "--action", json.dumps(action), "--expected-head", state["head"])
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["revision"] == 1
    audited = invoke("audit")
    assert audited.returncode == 0
    assert json.loads(audited.stdout)["verified"] is True


def test_direct_action_decoder_rejects_nontext_and_oversized_unicode():
    """Direct library callers share the CLI's byte budget, not just argv callers."""
    import pytest
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import MAX_ACTION_JSON_BYTES

    with pytest.raises(ValueError, match="must be text"):
        _strict_action_json(None)
    with pytest.raises(ValueError, match="byte budget"):
        _strict_action_json('{"verb":"' + ("é" * (MAX_ACTION_JSON_BYTES // 2)) + '"}')
    assert _strict_action_json('{"verb":"move"}') == {"verb": "move"}
