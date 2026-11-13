"""Transactional season editing, immutable earned rounds and CLI replay."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_season import build_season, verify_season_record
from skeleton.game.gameplay.harbor_crafting_season_authoring import (
    author_season_revision, verify_season_revision,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def setup():
    world = load_source(ROOT / "harbor_lantern_quay.json")
    course = decode((ROOT / "harbor_lantern_quay_time_trial.json").read_bytes())
    season = {
        "schema": "skeleton.game.harbor.season.v1", "source_id": world["id"],
        "rounds": [{"id": "opening", "course": course}],
        "points": {"gold": 10, "silver": 7, "bronze": 4, "finish": 2},
    }
    first = export_bundle(world, demo_actions(), require_win=True)
    return world, season, first


def next_course(course):
    updated = deepcopy(course)
    updated["deadline"] = 33
    updated["medals"] = {"gold": 19, "silver": 25, "bronze": 33}
    return updated


def edit(world, season, edits, *, preview=None):
    return author_season_revision(
        world, season, edits, expected_source_digest=digest(world),
        expected_season_digest=digest(season), preview_record=preview,
    )


def test_append_round_preserves_earned_save_and_replays_preview():
    world, season, first = setup()
    earned = build_season(world, season, [first])
    revision = edit(world, season, [
        {"op": "append_round", "id": "night_shift",
         "course": next_course(season["rounds"][0]["course"])},
    ], preview=earned)
    assert revision["preview_result"]["next_round"] == 1
    assert not revision["preview_result"]["complete"]
    assert revision["preview_result"]["total_points"] == 10
    assert verify_season_record(revision["preview_result"])["next_round"] == 1
    assert verify_season_revision(decode(canonical(revision)))["season_digest"] == digest(revision["season"])


def test_unplayed_round_can_be_replaced_or_removed():
    world, season, first = setup()
    two = deepcopy(season)
    two["rounds"].append({"id": "night_shift", "course": next_course(season["rounds"][0]["course"])})
    earned = build_season(world, two, [first])
    changed = next_course(two["rounds"][1]["course"])
    changed["deadline"] = 34
    changed["medals"]["bronze"] = 34
    revision = edit(world, two, [
        {"op": "replace_round", "id": "night_shift", "course": changed},
    ], preview=earned)
    assert revision["preview_result"]["next_round"] == 1
    removed = edit(world, two, [{"op": "remove_last", "id": "night_shift"}], preview=earned)
    assert removed["preview_result"]["complete"]


@pytest.mark.parametrize("edits,reason", [
    ([{"op": "set_points", "points": {"gold": 20, "silver": 7, "bronze": 4, "finish": 2}}], "rescore"),
    ([{"op": "replace_round", "id": "opening", "course": None}], "invalid"),
    ([{"op": "remove_last", "id": "opening"}], "invalid"),
])
def test_earned_round_cannot_be_mutated_or_removed(edits, reason):
    world, season, first = setup()
    earned = build_season(world, season, [first])
    with pytest.raises(HarborError):
        edit(world, season, edits, preview=earned)


def test_stale_leases_and_duplicate_edits_fail_closed():
    world, season, _ = setup()
    edits = [{"op": "set_points", "points": {"gold": 20, "silver": 10, "bronze": 5, "finish": 1}}]
    with pytest.raises(HarborError, match="stale season authoring source"):
        author_season_revision(world, season, edits, expected_source_digest="0" * 64,
                               expected_season_digest=digest(season))
    with pytest.raises(HarborError, match="stale season authoring base"):
        author_season_revision(world, season, edits, expected_source_digest=digest(world),
                               expected_season_digest="0" * 64)
    with pytest.raises(HarborError, match="unsupported season edit"):
        edit(world, season, [{"op": "set_points", "points": season["points"], "extra": 1}])


def test_resealed_revision_forgery_is_rejected():
    world, season, first = setup()
    earned = build_season(world, season, [first])
    revision = edit(world, season, [
        {"op": "append_round", "id": "night_shift",
         "course": next_course(season["rounds"][0]["course"])},
    ], preview=earned)
    forged = deepcopy(revision)
    forged["preview_result"]["total_points"] = 999
    forged["revision_digest"] = digest({k: v for k, v in forged.items() if k != "revision_digest"})
    with pytest.raises(HarborError):
        verify_season_revision(forged)


def test_cli_season_author_and_verify(tmp_path):
    world, season, first = setup()
    earned = build_season(world, season, [first])
    edits = [{"op": "append_round", "id": "night_shift",
              "course": next_course(season["rounds"][0]["course"])}]
    season_path = tmp_path / "season.json"
    edits_path = tmp_path / "edits.json"
    earned_path = tmp_path / "earned.json"
    season_path.write_bytes(canonical(season))
    edits_path.write_bytes(canonical(edits))
    earned_path.write_bytes(canonical(earned))
    proc = subprocess.run(CLI + [
        "season-author", "--season", str(season_path),
        "--season-edits", str(edits_path),
        "--expected-source-digest", digest(world),
        "--expected-season-digest", digest(season),
        "--preview-season-record", str(earned_path),
    ], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode()
    revision = decode(proc.stdout)
    assert revision["preview_result"]["next_round"] == 1
    revision_path = tmp_path / "revision.json"
    revision_path.write_bytes(proc.stdout)
    checked = subprocess.run(CLI + [
        "season-verify-author", "--season-revision", str(revision_path),
    ], capture_output=True, check=False)
    assert checked.returncode == 0, checked.stderr.decode()
    assert decode(checked.stdout)["verified"] is True
