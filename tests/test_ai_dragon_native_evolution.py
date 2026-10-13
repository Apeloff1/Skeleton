"""Real multi-edition original game building, auditing and variant evolution."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json

import pytest

from skeleton.ai.webcrawler.dragon_native_production import (
    PortableGameDesign,ProductionRequest,_hash,portable_design_document,
    load_portable_design,verify_published_production,
)
from skeleton.ai.webcrawler.dragon_native_evolution import (
    EvolutionSeriesRequest,build_evolution_series,
    preview_evolution_series,variant_for,verify_evolution_series,
)

def series(*,targets=("game_boy","nes"),editions=3,**changes):
    game=ProductionRequest(
        title="Original Dragon Evolution",
        style="arcade_score_attack",
        targets=targets,seed=101,original_work_attested=True,
        portable_design=PortableGameDesign(
            palette="dmg_green",hero="hatchling",
            quest_theme="crystals",difficulty=2,
            stages=3,candidates=4,
        ),
    )
    return EvolutionSeriesRequest(base=game,editions=editions,**changes)


def test_game_evolution_preview_is_real_distinct_native_work_not_invented_completion(tmp_path):
    item=series(editions=4)
    preview=preview_evolution_series(item)
    assert preview["status"]=="source_ready"
    assert preview["project_count"]==8
    assert len({x["request_id"] for x in preview["editions"]})==4
    assert [x["edition"] for x in preview["editions"]]==[1,2,3,4]
    assert preview["editions"][0]["design"]["hero"]=="hatchling"
    assert preview["editions"][0]["design"]["quest_theme"]=="crystals"
    assert variant_for(item,0).portable_design==item.base.portable_design
    assert [v["seed"] for v in preview["editions"]]==[
        variant_for(item,i).seed for i in range(4)
    ]
    assert not tmp_path.joinpath("episode").exists()
    assert "not trained" in preview["claim"]


@pytest.mark.parametrize("options",[
    {"editions":1},
    {"editions":13},
    {"editions":True},
    {"editions":3,"targets":("game_boy","nes","pc_linux","pc_windows")},
    {"editions":12,"targets":("game_boy","nes","pc_linux","pc_windows")},
    {"rotate_heroes":1},
    {"ramp_difficulty":"yes"},
])
def test_game_evolution_admission_guards_unbounded_jobs(options):
    targets=options.pop("targets",("game_boy",))
    editions=options.pop("editions",3)
    with pytest.raises((ValueError,PermissionError)):
        series(targets=targets,editions=editions,**options).validate()


def test_original_edition_does_not_build_without_publication_approval(tmp_path):
    with pytest.raises(PermissionError):
        build_evolution_series(series(),tmp_path,authorized=False)
    assert not tmp_path.exists()


def test_game_evolution_real_source_archives_chained_adaptation_and_replay(tmp_path):
    item=series(editions=3)
    result=build_evolution_series(item,tmp_path,authorized=True)
    assert result["status"]=="published"
    assert result["editions"]==3
    assert result["source_projects"]==6
    manifest=tmp_path/result["index"]
    assert manifest.is_file()
    audit=verify_evolution_series(tmp_path,result["index"])
    assert audit["status"]=="verified_original_game_evolution"
    assert audit["editions_verified"]==3
    assert audit["source_projects_verified"]==6
    assert audit["index_sha256"]==result["index_sha256"]
    for entry in result["report"]["editions"]:
        assert verify_published_production(
            tmp_path/entry["directory"],entry["index"]
        )["archives_verified"]==2
    assert result["report"]["editions"][0]["source_changes_from_previous"] is None
    assert all(row["source_changes_from_previous"]>0
               for row in result["report"]["editions"][1:])


def test_original_evolution_republication_is_idempotent(tmp_path):
    selected=series(targets=("game_boy",),editions=2)
    first=build_evolution_series(selected,tmp_path,authorized=True)
    second=build_evolution_series(selected,tmp_path,authorized=True)
    assert first["index"]==second["index"]
    assert first["index_sha256"]==second["index_sha256"]
    assert verify_evolution_series(tmp_path,first["index"])["editions_verified"]==2


def test_evolution_index_or_release_tamper_cannot_pass_audit(tmp_path):
    result=build_evolution_series(series(targets=("game_boy",),editions=2),
                                  tmp_path,authorized=True)
    receipt=result["report"]["editions"][1]
    edition_dir=tmp_path/receipt["directory"]
    nested=edition_dir/receipt["index"]
    record=json.loads(nested.read_text())
    record["legal_claim"]="royalty-free commercial clearance"
    nested.write_text(json.dumps(record))
    with pytest.raises(ValueError,match="changed|claim|legal|drift"):
        verify_evolution_series(tmp_path,result["index"])


def test_evolution_directory_cannot_be_rebound_to_symlink(tmp_path):
    root=tmp_path/"editions"
    target=tmp_path/"foreign"
    target.mkdir()
    root.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):
        build_evolution_series(series(targets=("game_boy",)),root,authorized=True)


def test_portable_game_design_file_has_canonical_exact_schema(tmp_path):
    approved=PortableGameDesign(
        palette="modern_neon",hero="pilot",quest_theme="forest",
        difficulty=9,stages=8,candidates=24,
    )
    path=tmp_path/"original-design.json"
    path.write_text(json.dumps(portable_design_document(approved)))
    assert load_portable_design(path)==approved
    path.write_text('{"schema":"skeleton.ai.dragon.portable_game_design.v1",'
                    '"hero":"knight","hero":"robot"}')
    with pytest.raises(ValueError,match="duplicate"):
        load_portable_design(path)
    path.write_text(json.dumps({**portable_design_document(approved),
                                "external_rom":"third_party.bin"}))
    with pytest.raises(ValueError,match="canonical"):
        load_portable_design(path)


def test_original_evolution_preview_does_not_publish_artifacts(tmp_path):
    item=series(targets=("game_boy","ps5"))
    planned=build_evolution_series(item,tmp_path,authorized=True,dry_run=True)
    assert planned["status"]=="blocked"
    assert not tmp_path.exists()


def test_original_game_series_refuses_external_unreviewed_rights_documentation():
    original=series()
    third_party=replace(original.base,rights_basis="documented_license",
                        rights_reference="some-license")
    with pytest.raises(PermissionError):
        replace(original,base=third_party).validate()
