"""Source-bound tidal hazards, shelter recovery, replay and transactional editing."""
from __future__ import annotations

from copy import deepcopy
import subprocess

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, digest
from skeleton.game.gameplay.harbor_crafting_beacon_tides import (
    build_beacon_tide_report, verify_beacon_tide_report, resume_beacon_tide_report,
    validate_beacon_tides,
)
from skeleton.game.gameplay.harbor_crafting_beacon_tide_authoring import (
    edit_beacon_tides, verify_beacon_tide_revision,
)
from skeleton.testing.test_harbor_crafting_beacons import (
    CLI, FIXTURES, source_board, winning_actions,
)


def inputs():
    source, beacons = source_board()
    tide = decode((FIXTURES / "harbor_lantern_quay_beacon_tides.json").read_bytes())
    return source, beacons, tide


def test_real_tide_hazard_and_earned_rescue_replay():
    source, beacons, tide = inputs()
    report = build_beacon_tide_report(
        source, beacons, tide, winning_actions(), require_rescue=True,
    )
    result = verify_beacon_tide_report(decode(canonical(report)), require_rescue=True)
    assert result["rescued"] and not result["failed"]
    assert result["stamina"] == 1 and result["tick"] == 22
    assert report["beacon_report"]["state"]["rescued"]
    assert report["events"][-1]["previous"] == report["events"][-2]["digest"]


def test_tide_drowning_is_a_real_terminal_state_and_shelter_rest_is_bounded():
    source, beacons, tide = inputs()
    lethal = deepcopy(tide)
    lethal["stamina"] = 1
    report = build_beacon_tide_report(source, beacons, lethal, winning_actions()[:16])
    assert report["state"]["failed"] and report["state"]["stamina"] == 0
    with pytest.raises(HarborError, match="terminal"):
        resume_beacon_tide_report(
            report, winning_actions()[16:], expected_digest=report["tide_digest"],
        )
    with pytest.raises(HarborError, match="not earned"):
        verify_beacon_tide_report(report, require_rescue=True)
    before = winning_actions()[:12]
    resting = build_beacon_tide_report(
        source, beacons, tide, before + [{"op": "rest"}],
    )
    assert resting["state"]["stamina"] == tide["stamina"]
    with pytest.raises(HarborError, match="shelter"):
        build_beacon_tide_report(
            source, beacons, tide,
            before + [{"op": "move", "direction": "east"}, {"op": "rest"}],
        )


def test_tide_source_binding_validation_and_resealed_forgery():
    source, beacons, tide = inputs()
    for field, value in (
        ("source_id", "foreign"), ("period", True), ("high_ticks", [0, 0]),
        ("hazard_tiles", [[2, 2]]), ("rest_at", [3, 3]),
    ):
        forged = deepcopy(tide)
        forged[field] = value
        with pytest.raises(HarborError):
            validate_beacon_tides(forged, source, beacons)
    report = build_beacon_tide_report(source, beacons, tide, winning_actions())
    forged = deepcopy(report)
    forged["state"]["stamina"] = 999
    forged["tide_digest"] = digest({
        key: value for key, value in forged.items() if key != "tide_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_beacon_tide_report(forged)
    with pytest.raises(HarborError, match="stale"):
        resume_beacon_tide_report(
            report, [], expected_digest="0" * 64,
        )


def test_tide_editor_replays_preview_and_preserves_cas():
    source, beacons, tide = inputs()
    report = build_beacon_tide_report(source, beacons, tide, winning_actions())
    edits = [{"kind": "stamina", "value": 4}]
    revision = edit_beacon_tides(
        source, beacons, tide, edits, expected_board_digest=digest(tide),
        preview_report=report,
    )
    assert revision["result"]["state"]["stamina"] == 2
    assert verify_beacon_tide_revision(revision)["preview_rescued"]
    with pytest.raises(HarborError, match="stale"):
        edit_beacon_tides(
            source, beacons, tide, edits, expected_board_digest="0" * 64,
        )


def test_tide_cli_play_verify_resume_and_editor(tmp_path):
    source, beacons, tide = inputs()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    source_file = write("source", source)
    beacon_file = write("beacons", beacons)
    tide_file = write("tide", tide)
    actions = winning_actions()
    report = call("tide-run", "--source", source_file, "--board", beacon_file,
                  "--tide-board", tide_file, "--actions", write("actions", actions),
                  "--require-rescue")
    report_file = write("report", report)
    assert call("tide-verify", "--tide-report", report_file, "--require-rescue")["rescued"]
    partial = build_beacon_tide_report(source, beacons, tide, actions[:12])
    resumed = call(
        "tide-resume", "--tide-report", write("partial", partial),
        "--actions", write("rest", actions[12:]),
        "--expected-digest", partial["tide_digest"], "--require-rescue",
    )
    assert resumed == report
    edits = write("edits", [{"kind": "stamina", "value": 4}])
    revision = call(
        "tide-author", "--source", source_file, "--board", beacon_file,
        "--tide-board", tide_file, "--edits", edits,
        "--expected-digest", digest(tide), "--tide-report", report_file,
    )
    assert call("tide-verify-author", "--tide-revision",
                write("revision", revision))["preview_rescued"]
