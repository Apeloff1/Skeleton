"""Canonical operator CLI roundtrip against deterministic authoritative walk state."""
from __future__ import annotations

import io
import json
import sys

import pytest

from scripts.studio_ecosystem_cli import main
from skeleton.ai.game_builder import studio_ecosystem_walk_replay as replay


PROJECT = "original-test-world"


def _run(capsys, *flags):
    assert main(["--project", PROJECT, "--play-walk", *flags]) == 0
    return json.loads(capsys.readouterr().out)


def test_walk_cli_exports_authoritative_receipt_and_resume(capsys):
    start = _run(capsys)
    assert start["scene_index"] == 0
    assert start["position"] == [1, 1]
    assert start["events"] == []
    assert start["release_certified"] is False
    assert start["native_genre_runtime_verified"] is False
    first = _run(capsys, "--walk-events", json.dumps([
        ["move", "right"], ["choose", "inspect"]]))
    assert first["scene_index"] == 1
    assert first["choices"] == [["scene-one", "inspect"]]
    assert first["position"] == [1, 1]
    final = _run(capsys, "--walk-receipt", json.dumps(first),
                 "--walk-events", json.dumps([
                     ["move", "right"], ["choose", "finish"]]))
    assert final["scene_index"] == 2
    assert final["choices"] == [["scene-one", "inspect"], ["scene-two", "finish"]]
    assert final["events"] == [["move", "right"], ["choose", "inspect"],
                               ["move", "right"], ["choose", "finish"]]
    # A roundtrip with no additional actions is byte-for-byte canonical.
    assert _run(capsys, "--walk-receipt", json.dumps(final)) == final


@pytest.mark.parametrize("events", [
    '[["move","up"]]',  # boundary collision
    '[["choose","inspect"]]',  # not near marker
    '[["move","teleport"]]',
    '[["move",true]]',
    '[["move","right"], ["choose","not authored"]]',
    '[["move","right"], ["choose","inspect"], ["choose","finish"]]',
    '[{"action":"move"}]',
    '{"kind":"move"}',
    '[["move",NaN]]',
])
def test_walk_cli_rejects_invalid_or_forged_actions(capsys, events):
    with pytest.raises(SystemExit) as ex:
        main(["--project", PROJECT, "--play-walk", "--walk-events", events])
    assert ex.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_walk_cli_stdin_restore_and_bounded_read(capsys, monkeypatch):
    saved = _run(capsys, "--walk-events", '[["move","right"]]')
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
        io.BytesIO(json.dumps(saved).encode("utf-8")), encoding="utf-8"))
    resumed = _run(capsys, "--walk-receipt-stdin", "--walk-events",
                   '[["choose","inspect"]]')
    assert resumed["scene_index"] == 1
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
        io.BytesIO(b"x" * (replay.MAX_WALK_RECEIPT_BYTES + 1)), encoding="utf-8"))
    with pytest.raises(SystemExit) as exc:
        main(["--project", PROJECT, "--play-walk", "--walk-receipt-stdin"])
    assert exc.value.code == 2
    assert "byte budget" in capsys.readouterr().err


def test_walk_cli_rejects_forged_or_stale_receipt(capsys):
    valid = _run(capsys, "--walk-events", '[["move","right"]]')
    for key, forged in (("position", [3, 3]),
                        ("source_digest", "b"*64),
                        ("release_certified", True),
                        ("session_digest", "0"*64)):
        receipt = dict(valid)
        receipt[key] = forged
        with pytest.raises(SystemExit) as ex:
            main(["--project", PROJECT, "--play-walk", "--walk-receipt", json.dumps(receipt)])
        assert ex.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_walk_cli_rejects_duplicate_json_receipt_field(capsys):
    valid = _run(capsys)
    encoded = json.dumps(valid)
    encoded = encoded.replace('"project_id":', '"project_id":"other", "project_id":', 1)
    with pytest.raises(SystemExit) as ex:
        main(["--project", PROJECT, "--play-walk", "--walk-receipt", encoded])
    assert ex.value.code == 2
    assert "duplicate" in capsys.readouterr().err


def test_walk_cli_input_budget_precedes_source_read(monkeypatch, capsys):
    from scripts import studio_ecosystem_cli as cli
    monkeypatch.setattr(cli, "read_blueprint", lambda _: pytest.fail("source accessed before input budget"))
    with pytest.raises(SystemExit) as ex:
        main(["--project", PROJECT, "--play-walk", "--walk-events",
              "x" * (replay.MAX_WALK_RECEIPT_BYTES + 1)])
    assert ex.value.code == 2
    assert "byte budget" in capsys.readouterr().err


def test_walk_cli_rejects_mode_confusion_and_orphan_options(capsys):
    for args in (
        ["--project", PROJECT, "--walk-events", "[]"],
        ["--project", PROJECT, "--play-walk", "--play-quest"],
        ["--project", PROJECT, "--play-quest", "--walk-events", "[]"],
        ["--project", PROJECT, "--walk-receipt-stdin"],
        ["--project", PROJECT, "--play-walk", "--search", "x"],
        ["--project", PROJECT, "--play-walk", "--output", "out"],
    ):
        with pytest.raises(SystemExit) as ex:
            main(args)
        assert ex.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_walk_cli_rejects_total_history_budget(capsys):
    first = _run(capsys)
    # Many valid events can be repeated in a back-and-forth corridor.
    first["events"] = [["move", "right"]] * replay.MAX_WALK_EVENTS
    with pytest.raises(SystemExit) as ex:
        main(["--project", PROJECT, "--play-walk", "--walk-receipt", json.dumps(first),
              "--walk-events", '[["move","right"]]'])
    assert ex.value.code == 2
    assert "error:" in capsys.readouterr().err
