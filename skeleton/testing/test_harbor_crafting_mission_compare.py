"""Source-to-gameplay mission-edit consequence preview and replay custody."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_mission_authoring import author_mission_revision
from skeleton.game.gameplay.harbor_crafting_mission_compare import (
    compare_mission_revision, verify_mission_comparison,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def source():
    return load_source(ROOT / "harbor_lantern_quay.json")


def board():
    return decode((ROOT / "harbor_lantern_quay_missions.json").read_bytes())


def revision(operations):
    authored = board()
    return author_mission_revision(
        authored, source(), operations, expected_board_digest=digest(authored),
    )


def won_bundle():
    return export_bundle(source(), demo_actions(), require_win=True)


def test_edited_quest_points_have_deterministic_earned_score_delta():
    edited = revision([{"op": "set_points", "id": "salvage", "value": 15}])
    result = compare_mission_revision(edited, won_bundle())
    assert result["before"]["points"] == 60
    assert result["after"]["points"] == 65
    assert result["delta_points"] == 5
    assert result["gained"] == []
    assert result["lost"] == []
    assert verify_mission_comparison(decode(canonical(result))) == {
        "delta_points": 5, "gained": [], "lost": [],
        "before_points": 60, "after_points": 65,
    }
    assert canonical(result) == canonical(compare_mission_revision(edited, won_bundle()))


def test_choice_consequence_preview_loses_unearned_dispatch_mission():
    edited = revision([{
        "op": "replace_objective", "id": "dispatch", "index": 1,
        "objective": {"kind": "choose", "choice": "shelter"},
    }])
    result = compare_mission_revision(edited, won_bundle())
    assert result["before"]["points"] == 60
    assert result["after"]["points"] == 30
    assert result["delta_points"] == -30
    assert result["lost"] == ["dispatch"]
    assert result["gained"] == []
    assert verify_mission_comparison(result)["lost"] == ["dispatch"]


@pytest.mark.parametrize("mutation", [
    lambda c: c.update({"delta_points": 100}),
    lambda c: c["gained"].append("forged"),
    lambda c: c["after"].update({"points": 999}),
    lambda c: c["before"]["journal"][0].update({"points": 1000}),
    lambda c: c["revision"]["board"]["missions"][0].update({"points": 99}),
    lambda c: c.update({"bundle_digest": "0" * 64}),
])
def test_resealed_comparison_forgeries_rejected(mutation):
    result = compare_mission_revision(
        revision([{"op": "set_points", "id": "salvage", "value": 15}]),
        won_bundle(),
    )
    mutation(result)
    result["comparison_digest"] = digest({
        key: value for key, value in result.items() if key != "comparison_digest"
    })
    with pytest.raises(HarborError):
        verify_mission_comparison(result)


def test_comparison_rejects_different_world_source():
    edited = revision([{"op": "set_points", "id": "salvage", "value": 15}])
    bundle = won_bundle()
    bundle["source_digest"] = "f" * 64
    with pytest.raises(HarborError):
        compare_mission_revision(edited, bundle)


def test_cli_author_compare_and_verify_revision(tmp_path):
    world_path = ROOT / "harbor_lantern_quay.json"
    board_path = ROOT / "harbor_lantern_quay_missions.json"
    edits_path = tmp_path / "edits.json"
    edits_path.write_bytes(canonical([{"op": "set_points", "id": "salvage", "value": 15}]))
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_bytes(canonical(won_bundle()))
    base = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    authored = subprocess.run(
        base + ["author-missions", "--source", str(world_path), "--missions", str(board_path),
                "--mission-edits", str(edits_path), "--expected-board-digest", digest(board()),
                "--preview-bundle", str(bundle_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert authored.returncode == 0, authored.stderr
    revision_path = tmp_path / "revision.json"
    revision_path.write_text(authored.stdout, encoding="utf-8")
    verified = subprocess.run(
        base + ["verify-mission-author", "--mission-revision", str(revision_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["verified"]
    compared = subprocess.run(
        base + ["compare-mission-revision", "--mission-revision", str(revision_path),
                "--bundle", str(bundle_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert compared.returncode == 0, compared.stderr
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(compared.stdout, encoding="utf-8")
    accepted = subprocess.run(
        base + ["verify-mission-comparison", "--comparison", str(comparison_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["delta_points"] == 5
