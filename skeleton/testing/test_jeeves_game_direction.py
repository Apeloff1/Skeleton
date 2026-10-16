"""Source-canon anchored book/film direction and production gap regressions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer.jeeves_game_direction import DIMENSIONS, PANEL_SCHEMA, SCHEMA
from skeleton.ai.game_builder.story_canon_fabric import BIBLE, sign, story_bible_template


def workspace(tmp_path: Path) -> Path:
    result=run_game_cli(["init","literary-game","--dir",str(tmp_path),
                         "--vision","Completely original high-consequence branching story"])
    assert result["ok"],result
    return tmp_path/"literary-game"


def original_bible(root: Path) -> Path:
    doc=story_bible_template("literary_game")
    doc["title"]="The Last Observatory"
    doc["story"]={
        "premise":"A night-shift astronomer must discover why the winter stars disappear.",
        "conflict":"The astronomer must choose between their sibling and the last surviving city.",
        "themes":["memory","sacrifice","return"],"planned_chapters":100,"planned_acts":1000,
    }
    doc["world"]={
        "era":"original low-technology science fiction",
        "geography":"One mountain observatory above a fogbound city.",
        "laws":["Every fulfilled oath binds two people to a single memory."],
    }
    doc=sign(doc,BIBLE)
    path=root/"design"/"bible.json"
    path.write_text(json.dumps(doc),encoding="utf-8")
    return path


def manifest(root: Path, **overrides) -> Path:
    doc={
        "schema":SCHEMA,"bible":"design/bible.json","contract":None,
        "scenes":[],"shotboards":[],"panel":None,
    }
    doc.update(overrides)
    path=root/"design"/"direction_manifest.json"
    path.write_text(json.dumps(doc),encoding="utf-8")
    return path


def creative_panel(root: Path, scores:int=94) -> Path:
    doc={"schema":PANEL_SCHEMA,"original_project":True,"reviews":[]}
    for i in range(3):
        doc["reviews"].append({
            "reviewer":f"Editor reviewer {i+1}",
            "role":"Literary or cinematic independent panel",
            "method":"Independent cold-read of approved original source and performance",
            "scores":{field:scores for field in DIMENSIONS},
            "critique":"Original authorial voice needs continuity verification before release.",
            "evidence_ids":["story_scene_0001"],
        })
    path=root/"design"/"editorial_panel.json"
    path.write_text(json.dumps(doc),encoding="utf-8")
    return path


def test_direction_audit_uses_real_canonical_story_bible_and_no_fake_scene_qa(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    manifest(root)
    review=run_game_cli(["jeeves","direction-audit","--project",str(root)])
    assert review["ok"],review
    assert review["canonical_source_replay_passed"]
    assert review["accepted_canonical_scenes"]==0
    assert review["dialogue_lines"]==0
    assert "approved_design_bible" in review["missing_qualification_gates"]
    assert "at_least_one_canonical_scene" in review["missing_qualification_gates"]
    assert review["narrative_world_class_certified"] is False
    assert review["hollywood_rendered_direction_certified"] is False
    assert review["game_story_ready_for_release"] is False
    order=run_game_cli(["jeeves","direction-workorder","--project",str(root)])
    assert order["ok"] and order["count"]>=6
    assert order["quality_downgrade_allowed"] is False


def test_strict_14_dimension_panel_cannot_certify_hollywood_quality(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    creative_panel(root, scores=95)
    manifest(root,panel="design/editorial_panel.json")
    direction=run_game_cli(["jeeves","direction-audit","--project",str(root)])
    assert direction["ok"],direction
    panel=direction["creative_panel"]
    assert len(DIMENSIONS)==14
    assert panel["reviewers"]==3
    assert panel["panel_claims_top_tier"] is True
    assert panel["minimum_scores"]["emotional_resonance"]==95
    assert panel["ratings_authenticated_externally"] is False
    assert direction["hollywood_rendered_direction_certified"] is False


def test_low_creative_quality_adds_explicit_repair_without_relaxation(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    creative_panel(root,scores=88)
    manifest(root,panel="design/editorial_panel.json")
    outcome=run_game_cli(["jeeves","direction-workorder","--project",str(root)])
    assert outcome["ok"],outcome
    assert any(x["gate"]=="artistic_character_psychology" for x in outcome["work_items"])
    assert any("require >= 90" in x["acceptance"] for x in outcome["work_items"])
    assert outcome["top_quality_bar"]=="all 14 artistic dimensions >=90 for every independent reviewer"


@pytest.mark.parametrize("corruption", [
    lambda doc:doc["story"].update({"conflict":"Something entirely different"}),
    lambda doc:doc.update({"phase":"design"}),
    lambda doc:doc.update({"rights_reviewed":True}),
])
def test_corrupted_canon_cannot_be_assessed_as_approved(tmp_path,corruption):
    root=workspace(tmp_path)
    path=original_bible(root)
    manifest(root)
    doc=json.loads(path.read_text())
    corruption(doc)
    path.write_text(json.dumps(doc))
    result=run_game_cli(["jeeves","direction-audit","--project",str(root)])
    assert not result["ok"]


def test_orphaned_shots_or_unsigned_dialogue_cannot_pass(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    manifest(root,shotboards=[{"sequence":1,"path":"design/shot_1.json"}])
    result=run_game_cli(["jeeves","direction-audit","--project",str(root)])
    assert not result["ok"]
    assert "contract" in result["error"]


def test_stale_reference_and_duplicate_source_rejected(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    manifest(root,scenes=["design/story_1.json","design/story_1.json"])
    result=run_game_cli(["jeeves","direction-audit","--project",str(root)])
    assert not result["ok"]
    assert "duplicate" in result["error"]


def test_artistic_panel_requires_distinct_reviewers_and_complete_dimensions(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    path=creative_panel(root)
    manifest(root,panel="design/editorial_panel.json")
    data=json.loads(path.read_text())
    data["reviews"][1]["reviewer"]=data["reviews"][0]["reviewer"]
    path.write_text(json.dumps(data))
    result=run_game_cli(["jeeves","direction-audit","--project",str(root)])
    assert not result["ok"]
    data["reviews"][1]["reviewer"]="Different independent reviewer"
    data["reviews"][1]["scores"].pop("emotional_resonance")
    path.write_text(json.dumps(data))
    assert not run_game_cli(["jeeves","direction-audit","--project",str(root)])["ok"]


def test_gap_matrix_reports_every_currently_unverified_release_discipline(tmp_path):
    root=workspace(tmp_path)
    result=run_game_cli(["jeeves","production-gap-matrix","--project",str(root)])
    assert result["ok"],result
    assert result["gap_count"]>=60
    assert sum(result["areas"].values())==result["gap_count"]
    assert len({g["gap_id"] for g in result["gaps"]})==result["gap_count"]
    assert any(g["gap_id"]=="literary_prose_voice" for g in result["gaps"])
    assert any(g["gap_id"]=="modern_gpu_quality" for g in result["gaps"])
    assert result["live_project_evidence"]["production_complete"] is False
    assert result["standalone_studio_qualified"] is False
    assert result["catalog_guaranteed_complete_for_every_possible_game_genre"] is False


def test_unrelated_cli_options_are_not_silently_ignored(tmp_path):
    root=workspace(tmp_path)
    original_bible(root)
    manifest(root)
    denied=run_game_cli(["jeeves","direction-audit","--project",str(root),
                         "--target","ps5"])
    assert not denied["ok"]
    denied2=run_game_cli(["jeeves","production-gap-matrix","--project",str(root),
                          "--source","design/foo.json"])
    assert not denied2["ok"]
