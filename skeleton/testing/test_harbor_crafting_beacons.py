"""End-to-end original beacon rescue: canonical gameplay -> replay -> export."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_beacons import (
    build_beacon_rescue, verify_beacon_rescue, resume_beacon_rescue,
    validate_beacon_board,
)
from skeleton.game.gameplay.harbor_crafting_beacon_authoring import (
    edit_beacons, verify_beacon_revision,
)
from skeleton.game.gameplay.harbor_crafting_beacon_package import (
    build_beacon_package, play_beacon_package, verify_beacon_package,
    verify_beacon_package_play, resume_beacon_package,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_beacon_cli"]


def source_board():
    return (
        load_source(FIXTURES / "harbor_lantern_quay.json"),
        decode((FIXTURES / "harbor_lantern_quay_beacons.json").read_bytes()),
    )


def winning_actions():
    demo = demo_actions()
    return (
        demo[:12]
        + [{"op": "repair", "beacon": "canal_light"},
           {"op": "signal", "beacon": "canal_light"}]
        + demo[12:16]
        + [{"op": "repair", "beacon": "dock_light"},
           {"op": "signal", "beacon": "dock_light"}]
        + demo[16:17]
        + [{"op": "rescue"}]
    )


def test_real_crafting_signals_delivery_and_earned_rescue():
    source, board = source_board()
    report = build_beacon_rescue(source, board, winning_actions(), require_rescue=True)
    status = verify_beacon_rescue(decode(canonical(report)), require_rescue=True)
    assert status["rescued"]
    assert status["signaled"] == ["canal_light", "dock_light"]
    assert status["tick"] == 22
    assert status["delivered"]
    assert report["bundle"]["state"]["ending"] == "beacon"
    assert report["bundle"]["state"]["inventory"].get("lantern", 0) == 0
    assert report["events"][-1]["previous"] == report["events"][-2]["digest"]


def test_canonical_tool_and_prerequisite_cannot_be_bypassed():
    source, board = source_board()
    with pytest.raises(HarborError, match="(?:not earned|out of reach)"):
        build_beacon_rescue(source, board, [{"op": "repair", "beacon": "canal_light"}])
    with pytest.raises(HarborError, match="prerequisite"):
        build_beacon_rescue(
            source, board,
            demo_actions()[:12] + demo_actions()[12:16]
            + [{"op": "repair", "beacon": "dock_light"},
               {"op": "signal", "beacon": "dock_light"}],
        )
    with pytest.raises(HarborError, match="bypasses"):
        build_beacon_rescue(source, board, demo_actions())
    with pytest.raises(HarborError, match="not earned"):
        build_beacon_rescue(source, board, demo_actions()[:-1] + [{"op": "rescue"}])


def test_board_rejects_cycles_collisions_oversize_and_malformed_values():
    source, board = source_board()
    for change in (
        {"repair_tool": "impossible"},
        {"max_turns": True},
        {"max_turns": 99999},
        {"beacons": []},
        {"beacons": [board["beacons"][0]] * 2},
    ):
        candidate = deepcopy(board)
        candidate.update(change)
        with pytest.raises(HarborError):
            validate_beacon_board(candidate, source)
    for pos in ([2, 2], [4, 2], source["dock"]):
        candidate = deepcopy(board)
        candidate["beacons"][0]["at"] = pos
        with pytest.raises(HarborError):
            validate_beacon_board(candidate, source)
    candidate = deepcopy(board)
    candidate["beacons"][0]["requires"] = ["dock_light"]
    with pytest.raises(HarborError, match="earlier"):
        validate_beacon_board(candidate, source)
    candidate = deepcopy(board)
    candidate["beacons"][0]["power"] = False
    with pytest.raises(HarborError):
        validate_beacon_board(candidate, source)


def test_replay_forgery_and_stale_resume_fail_closed():
    source, board = source_board()
    actions = winning_actions()
    partial = build_beacon_rescue(source, board, actions[:15])
    full = resume_beacon_rescue(
        partial, actions[15:], expected_digest=partial["report_digest"],
        require_rescue=True,
    )
    assert full == build_beacon_rescue(source, board, actions, require_rescue=True)
    with pytest.raises(HarborError, match="stale"):
        resume_beacon_rescue(partial, actions[15:], expected_digest="0" * 64)
    with pytest.raises(HarborError, match="terminal"):
        resume_beacon_rescue(full, [{"op": "wait"}], expected_digest=full["report_digest"])
    for field, value in (("rescued", False), ("tick", 999), ("signaled", [])):
        forged = deepcopy(full)
        forged["state"][field] = value
        forged["report_digest"] = digest({
            key: item for key, item in forged.items() if key != "report_digest"
        })
        with pytest.raises(HarborError, match="replay"):
            verify_beacon_rescue(forged)


def test_editor_cas_preview_and_replay_verification():
    source, board = source_board()
    report = build_beacon_rescue(source, board, winning_actions(), require_rescue=True)
    revision = edit_beacons(
        source, board, [{"kind": "max-turns", "target": "board", "value": 79}],
        expected_board_digest=digest(board), preview_report=report,
    )
    assert verify_beacon_revision(decode(canonical(revision)))["preview_rescued"]
    with pytest.raises(HarborError, match="stale"):
        edit_beacons(
            source, board, [{"kind": "power", "target": "dock_light", "value": 2}],
            expected_board_digest="0" * 64,
        )
    with pytest.raises(HarborError):
        edit_beacons(
            source, board, [{"kind": "power", "target": "dock_light", "value": 2}],
            expected_board_digest=digest(board), preview_report=report,
        )
    forged = deepcopy(revision)
    forged["after"]["max_turns"] = 80
    forged["revision_digest"] = digest({
        key: item for key, item in forged.items() if key != "revision_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_beacon_revision(forged)


def test_portable_package_and_cas_continuation():
    source, board = source_board()
    package = build_beacon_package("lantern-beacon-rescue", source, board)
    assert verify_beacon_package(package)["verified"]
    actions = winning_actions()
    partial = play_beacon_package(package, actions[:15])
    complete = resume_beacon_package(
        partial, actions[15:], expected_digest=partial["play_digest"],
        require_rescue=True,
    )
    assert complete == play_beacon_package(package, actions, require_rescue=True)
    assert verify_beacon_package_play(decode(canonical(complete)), require_rescue=True)["rescued"]
    with pytest.raises(HarborError, match="stale"):
        resume_beacon_package(partial, actions[15:], expected_digest="0" * 64)
    forged = deepcopy(complete)
    forged["report"]["state"]["rescued"] = False
    forged["report"]["report_digest"] = digest({
        key: item for key, item in forged["report"].items() if key != "report_digest"
    })
    forged["play_digest"] = digest({
        key: item for key, item in forged.items() if key != "play_digest"
    })
    with pytest.raises(HarborError):
        verify_beacon_package_play(forged)


def test_user_reachable_cli_run_verify_package_and_author(tmp_path):
    source, board = source_board()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)

    world_file = str(FIXTURES / "harbor_lantern_quay.json")
    board_file = str(FIXTURES / "harbor_lantern_quay_beacons.json")
    actions = write("actions", winning_actions())
    report = call("run", "--source", world_file, "--board", board_file,
                  "--actions", actions, "--require-rescue")
    report_file = write("report", report)
    assert call("verify", "--report", report_file, "--require-rescue")["rescued"]
    package = call("package", "--source", world_file, "--board", board_file)
    package_file = write("package", package)
    assert call("verify-package", "--package", package_file)["verified"]
    play = call("play", "--package", package_file, "--actions", actions,
                "--require-rescue")
    assert call("verify-play", "--play", write("play", play), "--require-rescue")["rescued"]
    edits = write("edits", [{"kind": "max-turns", "target": "board", "value": 79}])
    revision = call(
        "author", "--source", world_file, "--board", board_file,
        "--edits", edits, "--expected-digest", digest(board),
        "--report", report_file,
    )
    assert call("verify-author", "--revision", write("revision", revision))["verified"]
    bad = subprocess.run(
        CLI + ["resume", "--report", report_file, "--actions", actions,
               "--expected-digest", "0" * 64], capture_output=True, check=False,
    )
    assert bad.returncode == 2 and b"stale" in bad.stderr


def test_interactive_beacon_terminal_rejects_bad_input_and_saves_victory():
    from io import StringIO
    from skeleton.game.gameplay.harbor_crafting_beacon_ui import play_beacon_live
    source, board = source_board()
    lines = ["invalid", "repair fake"]
    for action in winning_actions():
        op = action["op"]
        lines.append(
            op + " " + action.get(
                "direction", action.get("recipe", action.get("item", action.get("beacon", "")))
            ) if op in {"move", "craft", "trade", "repair", "signal"} else op
        )
    output = StringIO()
    report = play_beacon_live(
        source, board, instream=StringIO("\n".join(lines) + "\n"),
        outstream=output,
    )
    assert verify_beacon_rescue(report, require_rescue=True)["rescued"]
    assert "Rejected:" in output.getvalue()
    assert "beacon>" in output.getvalue()


def test_public_beacon_status_replays_before_exposing_result():
    from skeleton.game.gameplay.harbor_crafting_beacons import beacon_status
    source, board = source_board()
    report = build_beacon_rescue(source, board, winning_actions(), require_rescue=True)
    assert beacon_status(report)["rescued"]
    forged = deepcopy(report)
    forged["state"]["rescued"] = False
    with pytest.raises(HarborError):
        beacon_status(forged)
