"""Legal beacon guidance is executable, bounded, replayed and tamper-evident."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, digest
from skeleton.game.gameplay.harbor_crafting_beacons import (
    build_beacon_rescue, resume_beacon_rescue,
)
from skeleton.game.gameplay.harbor_crafting_beacon_guidance import (
    legal_beacon_actions, verify_beacon_guidance,
)
from skeleton.testing.test_harbor_crafting_beacons import source_board, winning_actions


def test_every_hint_is_a_real_executable_transition():
    source, board = source_board()
    initial = build_beacon_rescue(source, board, [])
    guidance = legal_beacon_actions(initial)
    assert verify_beacon_guidance(initial, decode(canonical(guidance)))["verified"]
    assert {"op": "move", "direction": "east"} in [
        item["action"] for item in guidance["candidates"]
    ]
    assert {"op": "repair", "beacon": "canal_light"} not in [
        item["action"] for item in guidance["candidates"]
    ]
    for item in guidance["candidates"]:
        next_report = resume_beacon_rescue(
            initial, [item["action"]], expected_digest=initial["report_digest"],
        )
        assert next_report["report_digest"] == item["report_digest"]


def test_repair_signal_rescue_only_admitted_when_earned():
    source, board = source_board()
    actions = winning_actions()
    repaired = build_beacon_rescue(source, board, actions[:13])
    hints = legal_beacon_actions(repaired)
    assert {"op": "signal", "beacon": "canal_light"} in [
        item["action"] for item in hints["candidates"]
    ]
    assert {"op": "rescue"} not in [item["action"] for item in hints["candidates"]]
    near_rescue = build_beacon_rescue(source, board, actions[:-1])
    ending = legal_beacon_actions(near_rescue)
    assert {"op": "rescue"} in [item["action"] for item in ending["candidates"]]
    finished = build_beacon_rescue(source, board, actions, require_rescue=True)
    assert legal_beacon_actions(finished)["candidates"] == []


def test_guidance_rejects_resealed_forged_actions_and_stale_custody():
    source, board = source_board()
    report = build_beacon_rescue(source, board, [])
    guidance = legal_beacon_actions(report)
    forged = deepcopy(guidance)
    forged["candidates"].append({
        "action": {"op": "rescue"}, "report_digest": "0" * 64,
        "rescued": True, "signals": [], "delivered": True,
    })
    forged["guidance_digest"] = digest({
        key: value for key, value in forged.items() if key != "guidance_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_beacon_guidance(report, forged)
    progressed = resume_beacon_rescue(
        report, [{"op": "move", "direction": "east"}],
        expected_digest=report["report_digest"],
    )
    with pytest.raises(HarborError, match="replay"):
        verify_beacon_guidance(progressed, guidance)
