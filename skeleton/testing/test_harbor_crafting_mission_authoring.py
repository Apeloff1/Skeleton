"""Mission-board editing, CAS, portable preview and hostile revision contracts."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_mission_authoring import (
    author_mission_revision, verify_mission_revision,
)
from skeleton.game.gameplay.harbor_crafting_missions import verify_mission_report

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def world():
    return load_source(ROOT / "harbor_lantern_quay.json")


def board():
    return decode((ROOT / "harbor_lantern_quay_missions.json").read_bytes())


def test_transactional_board_revision_replays_against_real_winning_session():
    original = board()
    source = world()
    operations = [
        {"op": "set_points", "id": "salvage", "value": 15},
        {"op": "set_deadline", "id": "dispatch", "value": 96},
    ]
    preview = export_bundle(source, demo_actions(), require_win=True)
    revision = author_mission_revision(
        original, source, operations, expected_board_digest=digest(original),
        preview_bundle=preview,
    )
    assert revision["board"]["missions"][0]["points"] == 15
    assert revision["preview"]["points"] == 65
    assert verify_mission_report(revision["preview"], require_all=True)["points"] == 65
    assert verify_mission_revision(decode(canonical(revision))) == revision["board"]
    assert original == board()
    assert canonical(revision) == canonical(author_mission_revision(
        original, source, operations, expected_board_digest=digest(original),
        preview_bundle=preview,
    ))


def test_stale_digest_and_duplicate_edit_target_fail_closed():
    source, original = world(), board()
    with pytest.raises(HarborError, match="stale"):
        author_mission_revision(original, source, [
            {"op": "set_points", "id": "salvage", "value": 30}
        ], expected_board_digest="0" * 64)
    with pytest.raises(HarborError, match="duplicate"):
        author_mission_revision(original, source, [
            {"op": "set_points", "id": "salvage", "value": 30},
            {"op": "set_points", "id": "salvage", "value": 40},
        ], expected_board_digest=digest(original))


@pytest.mark.parametrize("operation", [
    {"op": "remove_mission", "id": "salvage"},
    {"op": "set_requires", "id": "salvage", "requires": ["dispatch"]},
    {"op": "set_deadline", "id": "salvage", "value": 0},
    {"op": "set_points", "id": "salvage", "value": True},
    {"op": "remove_objective", "id": "dispatch", "index": 90},
    {"op": "append_objective", "id": "dispatch", "objective": {"kind": "choose", "choice": "admin"}},
    {"op": "replace_mission", "id": "salvage", "mission": {"id": "different"}},
    {"op": "delete_everything"},
])
def test_invalid_edits_never_publish_revision(operation):
    original = board()
    with pytest.raises(HarborError):
        author_mission_revision(original, world(), [operation], expected_board_digest=digest(original))


def test_resealed_forged_preview_and_board_are_rejected_by_replay():
    original = board()
    revision = author_mission_revision(
        original, world(),
        [{"op": "set_points", "id": "salvage", "value": 15}],
        expected_board_digest=digest(original),
        preview_bundle=export_bundle(world(), demo_actions()),
    )
    altered = deepcopy(revision)
    altered["preview"]["points"] = 900
    altered["revision_digest"] = digest({k: v for k, v in altered.items() if k != "revision_digest"})
    with pytest.raises(HarborError):
        verify_mission_revision(altered)
    altered = deepcopy(revision)
    altered["board"]["missions"][0]["points"] = 99
    altered["board_digest"] = digest(altered["board"])
    altered["revision_digest"] = digest({k: v for k, v in altered.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay mismatch"):
        verify_mission_revision(altered)


def test_revision_without_preview_is_valid_but_not_claimed_playable():
    original = board()
    revision = author_mission_revision(
        original, world(),
        [{"op": "set_points", "id": "dispatch", "value": 40}],
        expected_board_digest=digest(original),
    )
    assert revision["preview"] is None
    assert verify_mission_revision(revision)["missions"][-1]["points"] == 40
