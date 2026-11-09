"""Product doc verbs must invoke existing organism owners, not placeholders."""
from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from skeleton.__main__ import main

@pytest.mark.parametrize("command,owner,function", [
    ("ready", "skeleton.organism.ready", "ready_card"),
    ("product", "skeleton.organism.product", "product_card"),
    ("health", "skeleton.organism.health", "health_card"),
    ("next", "skeleton.organism.next", "hint"),
])
def test_operator_command_dispatch_to_real_owner(command, owner, function, capsys):
    source = {"kind": command, "ok": 1, "record": "real-owner"}
    with patch("skeleton.organism.organismer.live_organismer", return_value=object()) as live:
        with patch(f"{owner}.{function}", return_value=source) as call:
            assert main([command, "--json"]) == 0
    assert live.call_count == 1
    assert call.call_count == 1
    assert json.loads(capsys.readouterr().out) == source

def test_ready_forwards_bounded_fix_and_walk_control(capsys):
    with patch("skeleton.organism.organismer.live_organismer", return_value=object()):
        with patch("skeleton.organism.ready.ready_card", return_value={"kind": "ready", "ok": 1}) as ready:
            assert main(["ready", "--fix", "--walk", "-n", "3"]) == 0
    assert ready.call_args.kwargs == {"walk": True, "n": 3, "fix": True}
    assert main(["ready", "-n", "100000"]) == 2
    capsys.readouterr()

def test_health_failure_exits_failure_without_fabrication(capsys):
    with patch("skeleton.organism.organismer.live_organismer", return_value=object()):
        with patch("skeleton.organism.health.health_card",
                   return_value={"kind": "health", "ok": 0, "errors": 4}):
            assert main(["health"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] == 0
