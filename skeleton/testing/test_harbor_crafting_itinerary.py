"""End-to-end waypoint navigation, legal interaction, replay and CLI."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_itinerary import (
    MAX_STOPS, build_itinerary, verify_itinerary,
)

WORLD = (
    Path(__file__).resolve().parents[1] / "game" / "gameplay"
    / "fixtures" / "harbor_lantern_quay.json"
)


def _root():
    return export_bundle(load_source(WORLD), [])


def _stops():
    return [
        {"goal": [2, 1], "action": {"op": "gather"}},
        {"goal": [2, 1], "action": {"op": "gather"}},
        {"goal": [1, 1], "action": None},
    ]


def _build(root=None, stops=None):
    root = _root() if root is None else root
    stops = _stops() if stops is None else stops
    return build_itinerary(
        root, stops, expected_terminal_digest=root["terminal_digest"]
    )


def test_multi_stop_playable_resource_collection_and_return():
    root = _root()
    report = _build(root)
    assert report["result"]["state"]["pos"] == [1, 1]
    assert report["result"]["state"]["inventory"]["wood"] == 2
    assert [entry["action"]["op"] for entry in report["segments"][:2]] == [
        "gather", "gather",
    ]
    assert len(report["actions"]) == 4
    assert report["result"]["events"][:len(root["events"])] == root["events"]
    assert verify_itinerary(decode(canonical(report)))["actions"] == 4
    assert canonical(_build(root)) == canonical(report)


def test_itinerary_can_resume_existing_checkpoint_without_rewriting_history():
    root = _root()
    partial = export_bundle(
        root["source"], [{"op": "move", "direction": "east"}]
    )
    report = _build(
        partial, [{"goal": [2, 1], "action": {"op": "gather"}}]
    )
    assert report["result"]["events"][:1] == partial["events"]
    assert verify_itinerary(report)["stops"] == 1


def test_invalid_interaction_fails_without_partial_publication():
    root = _root()
    before = deepcopy(root)
    with pytest.raises(HarborError, match="materials missing"):
        _build(root, [{"goal": [1, 1], "action": {
            "op": "craft", "recipe": "lantern",
        }}])
    assert root == before


def test_stale_cas_rejected():
    with pytest.raises(HarborError, match="stale itinerary checkpoint"):
        build_itinerary(
            _root(), _stops(), expected_terminal_digest="stale"
        )


@pytest.mark.parametrize("stops", [
    [], [{}], [{"goal": [2, 1]}],
    [{"goal": [2, 1], "action": None, "extra": 1}],
    [{"goal": [0, 0], "action": None}],
    [{"goal": [1, 1], "action": {"op": "teleport"}}],
    [{"goal": [1, 1], "action": None}] * (MAX_STOPS + 1),
])
def test_malformed_or_unreachable_itinerary_fails_closed(stops):
    with pytest.raises(HarborError):
        _build(stops=stops)


def test_resealed_forged_route_or_reward_is_rejected():
    original = _build()
    for field in ("actions", "segments", "result", "stops"):
        forged = deepcopy(original)
        if field == "actions":
            forged["actions"][0] = {"op": "wait"}
        elif field == "segments":
            forged["segments"][0]["terminal_digest"] = "0" * 64
        elif field == "result":
            forged["result"]["state"]["coins"] += 1
        else:
            forged["stops"][0]["goal"] = [1, 1]
        forged["itinerary_digest"] = digest({
            key: value for key, value in forged.items()
            if key != "itinerary_digest"
        })
        with pytest.raises(HarborError):
            verify_itinerary(forged)


def test_cli_build_and_verify_itinerary(tmp_path):
    root = _root()
    save_path = tmp_path / "save.json"
    stops_path = tmp_path / "stops.json"
    report_path = tmp_path / "itinerary.json"
    save_path.write_bytes(canonical(root))
    stops_path.write_bytes(canonical(_stops()))
    base = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    created = subprocess.run(
        base + [
            "itinerary-build", "--bundle", str(save_path),
            "--stops", str(stops_path),
            "--expected-terminal-digest", root["terminal_digest"],
        ], capture_output=True, text=True, timeout=30,
    )
    assert created.returncode == 0, created.stderr
    report_path.write_text(created.stdout, encoding="utf-8")
    verified = subprocess.run(
        base + ["itinerary-verify", "--itinerary", str(report_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["stops"] == 3
