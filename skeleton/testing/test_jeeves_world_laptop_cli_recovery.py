"""CLI recovery actions must be typed, bounded and non-mutating on failure."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.laptop_cli import MAX_INPUT, run


@pytest.mark.parametrize(("content", "expected", "next_action"), [
    (b" " * (MAX_INPUT + 1), "input_too_large", "reduce_json_input_below_524288_bytes"),
    (b"{}", "input_invalid_path", "provide_a_normalized_existing_json_file_path"),
])
def test_laptop_cli_input_recovery_does_not_publish(tmp_path, capsys, content, expected, next_action):
    source = tmp_path / "brief.json"
    source.write_bytes(content)
    path = str(source) if expected == "input_too_large" else str(tmp_path / ".." / "brief.json")
    assert run(["--store", str(tmp_path), "propose", "--brief-file", path]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure == {"ok": False, "phase": "propose", "error": expected,
                       "next_action": next_action}
    assert not any(p.name.endswith(".laptop.review.json") for p in tmp_path.iterdir())


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unsupported")
def test_laptop_cli_pipe_rejection_is_nonblocking_and_actionable(tmp_path, capsys):
    pipe = tmp_path / "untrusted.json"
    os.mkfifo(pipe)
    assert run(["--store", str(tmp_path), "propose", "--brief-file", str(pipe)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "input_not_regular"
    assert failure["next_action"] == "provide_a_regular_json_file_not_a_device_or_pipe"
