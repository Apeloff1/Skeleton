"""Signed scene-to-scene payoff tracing, explicit open plots and Hollywood claims."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.story_canon_fabric import BIBLE, SCENE, sign
from skeleton.ai.game_builder.story_dramaturgy_graph import (
    DramaturgyError, audit_threads,
)
from skeleton.ai.game_builder.story_direction_quality import evaluate_direction, revision_plan
from skeleton.developer.game_cli import run_game_cli
from tests.test_game_builder_story_canon_fabric import canonical_bible, scene_source


def sources(project="original-story", count=3):
    bible = canonical_bible()
    bible["project"] = project.replace("-", "_")
    bible = sign(bible, BIBLE)
    history = []
    for index in range(1, count + 1):
        history.append(scene_source(bible, index, history[-1] if history else None))
    return bible, history


def fulfilled(*, state="resolved", payoff="arrival_2"):
    return {
        "id": "recovered_lantern_route", "character": "alina",
        "setup": {"scene": 1, "anchor": "arrival_1"},
        "payoff": {"scene": 2, "anchor": payoff},
        "state": state,
        "stakes": "If the lost paths remain hidden, citizens cannot reach each other safely",
        "promise": "Alina promises the lantern routes will be found and documented",
        "consequence": (
            "The restored route changes the settlement and proves the promise"
            if state != "open" else None
        ),
    }


def test_signed_causal_path_proves_source_links_not_emotional_genius():
    bible, history = sources()
    proof = audit_threads(bible, history, [fulfilled()])
    assert proof["ok"]
    assert proof["declared_thread_count"] == 1
    assert proof["declared_resolved_count"] == 1
    assert proof["open_thread_ids"] == []
    assert proof["structural_resolution_complete"]
    assert proof["cross_scene_causal_links"] > 0
    row = proof["thread_evidence"][0]
    assert row["causal_path"] == ["arrival_1", "visit_1", "arrival_2"]
    assert row["scene_span"] == 1
    assert not row["original_audience_payoff_quality_proven"]
    assert not proof["professional_novel_emotional_payoff_verified"]
    assert not proof["complete_game_playthrough_verified"]


def test_open_arc_remains_explicit_and_creates_source_linked_revision():
    bible, history = sources()
    open_ = fulfilled(state="open")
    open_["payoff"] = None
    reviewed = evaluate_direction(
        bible, history, dramatic_threads=[open_], passes=5,
    )
    assert reviewed["ok"]
    assert reviewed["dramaturgy"]["open_thread_ids"] == [open_["id"]]
    assert reviewed["dramaturgy"]["structural_resolution_complete"] is False
    assert "unresolved_dramatic_thread" in {
        item["kind"] for item in reviewed["revision_work"]
    }
    revision = revision_plan(reviewed)
    uncovered = [
        r for r in revision["work_items"]
        if r["evidence_kind"] == "unresolved_dramatic_thread"
    ]
    assert len(uncovered) == 1
    assert uncovered[0]["thread_id"] == open_["id"]
    assert uncovered[0]["must_reverify_canonical_story_history"]
    assert not revision["source_files_modified"]


@pytest.mark.parametrize("edit,message", [
    (lambda t: t.update(payoff={"scene": 2, "anchor": "line_2"}), "causal path"),
    (lambda t: t.update(payoff={"scene": 3, "anchor": "arrival_2"}), "scene-local"),
    (lambda t: t.update(payoff={"scene": 1, "anchor": "arrival_1"}), "later scene"),
    (lambda t: t.update(character="unknown_person"), "outside signed bible"),
    (lambda t: t.update(stakes="small"), "substantive"),
    (lambda t: t.update(state="open"), "open story thread"),
    (lambda t: t.update(payoff=None), "needs a canonical"),
])
def test_unearned_or_fabricated_payoff_denied(edit, message):
    bible, history = sources()
    false_arc = fulfilled()
    edit(false_arc)
    with pytest.raises(DramaturgyError, match=message):
        audit_threads(bible, history, [false_arc])


def test_duplicate_source_threads_and_identity_tampering_fail():
    bible, history = sources()
    with pytest.raises(DramaturgyError, match="duplicate original"):
        audit_threads(bible, history, [fulfilled(), fulfilled()])
    corrupted = deepcopy(history)
    corrupted[1]["dialogue"][0]["text"] = "A very different unsanctioned line"
    with pytest.raises(ValueError):
        audit_threads(bible, corrupted, [fulfilled()])


def test_red_herring_requires_actual_later_signed_reveal():
    bible, history = sources()
    revelation = fulfilled(state="red_herring")
    revelation["consequence"] = "The supposed restoration is a deception revealed by signed sources"
    accepted = audit_threads(bible, history, [revelation])
    assert accepted["declared_red_herring_reveals"] == 1
    assert accepted["structural_resolution_complete"]
    assert not accepted["professional_novel_emotional_payoff_verified"]


def test_empty_tracker_does_not_claim_complete_game():
    bible, history = sources()
    report = audit_threads(bible, history, [])
    assert not report["structural_resolution_complete"]
    assert report["declared_thread_count"] == 0
    assert report["signed_scenes_scrutinized"] == len(history)


def test_project_dossier_tracks_unresolved_setup_and_read_only_editor(tmp_path):
    root = tmp_path / "original-story"
    result = run_game_cli(["init", "original-story", "--dir", str(tmp_path)])
    assert result["ok"], result
    bible, history = sources("original-story")
    path = root / "design" / "story_direction_packet.json"
    payload = {
        "schema": "skeleton.jeeves.direction_dossier.v1",
        "bible": bible,
        "scenes": history,
        "expert_reviews": [],
        "dramatic_threads": [fulfilled()],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    actual = run_game_cli([
        "jeeves", "direction-audit", "--project", str(root),
        "--source", "design/story_direction_packet.json", "--passes", "3",
    ])
    assert actual["ok"], actual
    assert actual["dramaturgy"]["declared_resolved_count"] == 1
    assert not actual["hollywood_level_film_quality_proven"]
    assert path.read_text(encoding="utf-8") == json.dumps(payload)
    changed = deepcopy(payload)
    changed["dramatic_threads"][0]["payoff"]["anchor"] = "line_2"
    path.write_text(json.dumps(changed), encoding="utf-8")
    denied = run_game_cli([
        "jeeves", "direction-audit", "--project", str(root),
        "--source", "design/story_direction_packet.json",
    ])
    assert not denied["ok"]


def test_no_character_payoff_when_cast_excluded(tmp_path):
    bible, history = sources()
    example = fulfilled()
    example["character"] = "boren"
    # Boren is present in original source, so evidence is still accepted.
    assert audit_threads(bible, history, [example])["ok"]
    example["character"] = "alina"
    removed = deepcopy(history)
    removed[1]["cast"] = ["boren"]
    removed[1] = sign(removed[1], SCENE)
    with pytest.raises(ValueError):
        audit_threads(bible, removed, [example])
