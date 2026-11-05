"""Original chained beacon quests are earned from canonical rescue actions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, digest
from skeleton.game.gameplay.harbor_crafting_beacons import build_beacon_rescue
from skeleton.game.gameplay.harbor_crafting_beacon_quests import (
    build_beacon_quest_report, verify_beacon_quest_report, validate_beacon_quests,
)
from skeleton.game.gameplay.harbor_crafting_beacon_quest_authoring import (
    edit_beacon_quests, verify_beacon_quest_revision,
)
from skeleton.testing.test_harbor_crafting_beacons import (
    CLI, FIXTURES, source_board, winning_actions,
)


def inputs():
    source, board = source_board()
    rescue = build_beacon_rescue(source, board, winning_actions(), require_rescue=True)
    quests = decode((FIXTURES / "harbor_lantern_quay_beacon_quests.json").read_bytes())
    return rescue, quests


def test_five_earned_quests_from_real_crafting_signals_and_delivery():
    rescue, quests = inputs()
    report = build_beacon_quest_report(rescue, quests, require_complete=True)
    result = verify_beacon_quest_report(decode(canonical(report)), require_complete=True)
    assert result["complete"] and result["score"] == 45
    assert result["completed"] == [
        "restore_canal", "light_canal", "light_dock", "deliver_relief", "call_rescue",
    ]
    assert [event["source_sequence"] for event in report["events"]] == [12, 13, 19, 20, 21]
    assert report["events"][-1]["previous"] == report["events"][-2]["digest"]


def test_quests_fail_closed_on_source_mismatch_cycles_and_unearned_rewards():
    rescue, quests = inputs()
    for key, value in (
        ("source_id", "foreign"), ("beacon_board_digest", "0" * 64),
        ("quests", []),
    ):
        altered = deepcopy(quests)
        altered[key] = value
        with pytest.raises(HarborError):
            validate_beacon_quests(altered, rescue)
    cyclic = deepcopy(quests)
    cyclic["quests"][0]["requires"] = ["call_rescue"]
    with pytest.raises(HarborError, match="earlier"):
        validate_beacon_quests(cyclic, rescue)
    partial = build_beacon_rescue(
        rescue["source"], rescue["board"], winning_actions()[:14],
    )
    report = build_beacon_quest_report(partial, quests)
    assert report["state"]["completed"] == ["restore_canal", "light_canal"]
    with pytest.raises(HarborError, match="not earned"):
        build_beacon_quest_report(partial, quests, require_complete=True)
    forged = deepcopy(build_beacon_quest_report(rescue, quests))
    forged["state"]["score"] = 999
    forged["quest_digest"] = digest({
        k: v for k, v in forged.items() if k != "quest_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_beacon_quest_report(forged)


def test_quest_editor_cas_preview_and_adversarial_revision():
    rescue, quests = inputs()
    preview = build_beacon_quest_report(rescue, quests, require_complete=True)
    edits = [{"kind": "reward", "target": "call_rescue", "value": 30}]
    revision = edit_beacon_quests(
        rescue, quests, edits, expected_board_digest=digest(quests),
        preview_report=preview,
    )
    assert revision["result"]["state"]["score"] == 55
    assert verify_beacon_quest_revision(revision)["preview_complete"]
    with pytest.raises(HarborError, match="stale"):
        edit_beacon_quests(rescue, quests, edits, expected_board_digest="0" * 64)
    forged = deepcopy(revision)
    forged["result"]["state"]["score"] = 999
    forged["result"]["quest_digest"] = digest({
        k: v for k, v in forged["result"].items() if k != "quest_digest"
    })
    forged["revision_digest"] = digest({
        k: v for k, v in forged.items() if k != "revision_digest"
    })
    with pytest.raises(HarborError):
        verify_beacon_quest_revision(forged)


def test_user_reachable_quest_cli_round_trip(tmp_path):
    rescue, quests = inputs()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    rescue_file = write("rescue", rescue)
    quest_file = write("quests", quests)
    report = call("quest-run", "--report", rescue_file,
                  "--quest-board", quest_file, "--require-rescue")
    assert call("quest-verify", "--quest-report", write("quest-report", report),
                "--require-rescue")["score"] == 45
    edits = write("edits", [{"kind": "reward", "target": "call_rescue", "value": 30}])
    revision = call("quest-author", "--report", rescue_file,
                    "--quest-board", quest_file, "--edits", edits,
                    "--expected-digest", digest(quests),
                    "--quest-report", write("preview", report))
    assert call("quest-verify-author", "--quest-revision",
                write("revision", revision))["preview_complete"]
