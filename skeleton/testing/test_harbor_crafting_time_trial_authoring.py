"""Transactional authoring and CLI acceptance for replayable time trials."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_time_trial_authoring import (
    author_time_trial_revision, verify_time_trial_revision,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    source = load_source(ROOT / "harbor_lantern_quay.json")
    course = decode((ROOT / "harbor_lantern_quay_time_trial.json").read_bytes())
    return source, course


def edit(source, course, edits, *, preview=None):
    return author_time_trial_revision(
        course, source, edits,
        expected_course_digest=digest(course),
        expected_source_digest=digest(source),
        preview_bundle=preview,
    )


def test_atomic_medal_revision_and_gameplay_preview():
    source, course = inputs()
    original = deepcopy(course)
    won = export_bundle(source, demo_actions(), require_win=True)
    revision = edit(source, course, [
        {"op": "set_medals", "gold": 17, "silver": 24, "bronze": 32},
    ], preview=won)
    assert course == original
    assert revision["course"]["medals"]["gold"] == 17
    assert revision["preview_report"]["medal"] == "silver"
    checked = verify_time_trial_revision(decode(canonical(revision)))
    assert checked["course_digest"] == revision["course_digest"]
    assert checked["preview"]["finish_tick"] == 18


def test_multi_edit_transaction_changes_checkpoint_and_choice():
    source, course = inputs()
    revision = edit(source, course, [
        {"op": "set_checkpoint", "id": "pantry", "at": [2, 3], "latest_tick": 12},
        {"op": "set_choice", "choice": "shelter"},
    ])
    assert revision["course"]["checkpoints"][2]["at"] == [2, 3]
    assert revision["course"]["choice"] == "shelter"
    assert verify_time_trial_revision(revision)["preview"] is None


def test_append_remove_checkpoint_and_validate_final_course():
    source, course = inputs()
    revision = edit(source, course, [
        {"op": "append_checkpoint", "id": "approach", "at": [6, 2], "latest_tick": 21},
        {"op": "remove_checkpoint", "id": "dock_approach"},
    ])
    assert [entry["id"] for entry in revision["course"]["checkpoints"]] == [
        "timber", "ore", "pantry", "approach",
    ]


@pytest.mark.parametrize("edits", [
    [{"op": "remove_checkpoint", "id": "absent"}],
    [{"op": "append_checkpoint", "id": "timber", "at": [5, 3], "latest_tick": 20}],
    [{"op": "set_checkpoint", "id": "timber", "at": [0, 0], "latest_tick": 3}],
    [{"op": "set_medals", "gold": 20, "silver": 19, "bronze": 32}],
    [{"op": "set_choice", "choice": "unearned"}],
    [{"op": "set_deadline", "deadline": True}],
    [{"op": "unknown", "data": "bad"}],
    [{"op": "remove_checkpoint", "id": "timber", "extra": True}],
])
def test_invalid_edits_rejected_atomically(edits):
    source, course = inputs()
    original = deepcopy(course)
    with pytest.raises(HarborError):
        edit(source, course, edits)
    assert course == original


def test_source_and_course_leases_reject_stale_edits():
    source, course = inputs()
    with pytest.raises(HarborError, match="stale time trial source"):
        author_time_trial_revision(
            course, source, [{"op": "set_choice", "choice": "shelter"}],
            expected_course_digest=digest(course),
            expected_source_digest="0" * 64,
        )
    with pytest.raises(HarborError, match="stale time trial course"):
        author_time_trial_revision(
            course, source, [{"op": "set_choice", "choice": "shelter"}],
            expected_course_digest="0" * 64,
            expected_source_digest=digest(source),
        )


def test_foreign_gameplay_preview_rejected():
    source, course = inputs()
    changed = deepcopy(source)
    changed["initial_coins"] = 5
    foreign = export_bundle(changed, demo_actions(), require_win=True)
    with pytest.raises(HarborError, match="preview source mismatch"):
        edit(source, course, [{"op": "set_choice", "choice": "shelter"}], preview=foreign)


def test_resealed_forged_course_or_preview_is_rejected():
    source, course = inputs()
    original = edit(source, course, [
        {"op": "set_medals", "gold": 17, "silver": 24, "bronze": 32},
    ], preview=export_bundle(source, demo_actions(), require_win=True))
    for mutation in (
        lambda r: r["course"]["medals"].update({"gold": 18}),
        lambda r: r["edits"][0].update({"gold": 18}),
        lambda r: r["preview_report"].update({"medal": "gold"}),
    ):
        changed = deepcopy(original)
        mutation(changed)
        changed["revision_digest"] = digest({
            key: value for key, value in changed.items() if key != "revision_digest"
        })
        with pytest.raises(HarborError):
            verify_time_trial_revision(changed)


def test_cli_author_and_verify_with_original_playable_preview(tmp_path):
    source, course = inputs()
    trial = ROOT / "harbor_lantern_quay_time_trial.json"
    edits = tmp_path / "edits.json"
    edits.write_bytes(canonical([
        {"op": "set_medals", "gold": 17, "silver": 24, "bronze": 32},
    ]))
    save = tmp_path / "save.json"
    save.write_bytes(canonical(export_bundle(source, demo_actions(), require_win=True)))
    produced = subprocess.run(CLI + [
        "trial-author", "--trial", str(trial), "--trial-edits", str(edits),
        "--expected-course-digest", digest(course),
        "--expected-source-digest", digest(source),
        "--preview-bundle", str(save),
    ], capture_output=True, check=False)
    assert produced.returncode == 0, produced.stderr.decode()
    revision = decode(produced.stdout)
    assert revision["preview_report"]["medal"] == "silver"
    revision_path = tmp_path / "revision.json"
    revision_path.write_bytes(produced.stdout)
    verified = subprocess.run(CLI + [
        "trial-verify-author", "--trial-revision", str(revision_path),
    ], capture_output=True, check=False)
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["preview"]["medal"] == "silver"
