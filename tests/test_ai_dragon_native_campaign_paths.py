"""Real branching native game chapters, distinct reachable endings and choice proofs."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile
from dataclasses import replace
import json,shutil,subprocess,pytest

from skeleton.ai.webcrawler.dragon_native_campaign_paths import (
    SCHEMA,design_campaign,graph_report,graph_header,
    verify_graph_report,validate_campaign,Chapter,Campaign,
)
from skeleton.ai.webcrawler.dragon_native_puzzle import emit_native_puzzle
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,_render,make_source_release,
)
from skeleton.ai.webcrawler.dragon_native_desktop import _puzzle_proof


@pytest.mark.parametrize("stages",list(range(1,9)))
def test_real_game_campaign_has_reachable_noncyclic_stages_and_alternate_endings(stages):
    campaign=design_campaign(stages,seed=1977,mode="branching")
    assert validate_campaign(campaign)==campaign
    assert len(campaign.chapters)==stages
    assert all(route[0]==0 for route in campaign.complete_routes)
    assert set(x for route in campaign.complete_routes for x in route)==set(range(stages))
    assert all(len(route)==len(set(route)) for route in campaign.complete_routes)
    assert campaign.ending_count==(2 if stages>=3 else 1)
    assert (campaign.choice_nodes>0)==(stages>=3)
    assert len(campaign.complete_routes)>1 if stages>=3 else len(campaign.complete_routes)==1
    assert verify_graph_report(json.loads(json.dumps(graph_report(campaign))))==campaign
    assert 'dragon_branch_next[LEVEL_COUNT][2]' in graph_header(campaign)


def test_stage_metrics_really_order_player_choices_without_deleting_options():
    easy=design_campaign(4,seed=23,stage_difficulty=(1,90,5,35),
                         intensity="gentle")
    spicy=design_campaign(4,seed=23,stage_difficulty=(1,90,5,35),
                          intensity="spicy")
    assert easy.chapters[0].exits==(2,1)
    assert spicy.chapters[0].exits==(1,2)
    assert easy.chapters[0].option_labels[0].startswith("lower tension")
    assert spicy.chapters[0].option_labels[0].startswith("higher tension")
    assert set(easy.chapters[0].exits)==set(spicy.chapters[0].exits)
    assert set(tuple(sorted(path)) for path in easy.complete_routes)==set(
        tuple(sorted(path)) for path in spicy.complete_routes)


@pytest.mark.parametrize("invalid", [
    {"stages":0},{"stages":9},{"stages":True},
    {"stages":4,"mode":"open-world-infinite"},
    {"stages":4,"intensity":"malicious"},
    {"stages":4,"stage_difficulty":(1,2)},
    {"stages":4,"stage_difficulty":(1,2,3,105)},
])
def test_campaign_generation_rejects_unbounded_or_fabricated_paths(invalid):
    with pytest.raises(ValueError):
        design_campaign(**invalid)


def test_original_runtime_source_has_genuine_branch_controls_and_alternate_ending_screen():
    native=emit_native_puzzle(seed=5,stages=5,difficulty=6)
    source=native["src/main.c"]
    header=native["include/dragon_puzzle.h"]
    proof=json.loads(native["dragon-puzzle-proof.json"])
    assert "--branch-selftest" in source
    assert "if(dragon_branch_count[chapter]==0)" in source
    assert "dragon_branch_next[chapter][option]" in source
    assert "if(key=='n'||key=='N'||key=='1'||key=='2')" in source
    assert 'dragon_branch_ending[LEVEL_COUNT]' in header
    assert 'dragon_branch_next[LEVEL_COUNT][2]' in header
    assert proof["campaign_mode"]=="branching"
    assert proof["campaign_graph"]["ending_count"]==2
    assert len(proof["campaign_graph"]["complete_routes"])>=2
    assert "SDLK_2" in native["src/graphics.c"]
    assert "SDL_CONTROLLER_BUTTON_Y" in native["src/graphics.c"]


def test_chapter_forks_are_identity_bound_and_replayable_as_actual_source():
    request=ProductionRequest(
        title="Original Multiple Ending Adventure",
        style="fixed_screen_puzzle",targets=("pc_linux",),
        original_work_attested=True,
        portable_design=PortableGameDesign(
            stages=4,campaign_pathing="branching",
            challenge_profile="spicy",
        ),
    )
    native=_render(request,"pc_linux")
    release,_=make_source_release(native,request)
    receipt,files=_puzzle_proof(release)
    proof=json.loads(files["dragon-puzzle-proof.json"])
    graph=verify_graph_report(proof["campaign_graph"])
    assert graph.mode=="branching" and graph.ending_count==2
    assert any(len(chapter.exits)==2 for chapter in graph.chapters)
    assert receipt["source_fingerprint"]==native.digest


@pytest.mark.skipif(not shutil.which("cc"),reason="requires trusted native C99 compiler")
@pytest.mark.parametrize("stages",[3,5,8])
def test_actual_compiled_original_c99_game_replays_every_fork_and_terminal_ending(
    tmp_path,stages,
):
    files=emit_native_puzzle(seed=2026,stages=stages,difficulty=6)
    for name in ("src/main.c","include/dragon_puzzle.h"):
        destination=tmp_path/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(files[name],encoding="utf-8")
    executable=tmp_path/"dragon_game"
    compiled=subprocess.run(
        ["cc","-O2","-std=c99","-Wall","-Wextra","-Werror","-pedantic",
         "-Iinclude","src/main.c","-o",str(executable)],
        cwd=tmp_path,capture_output=True,text=True,timeout=45,
    )
    assert compiled.returncode==0,compiled.stderr
    report=subprocess.run(
        [str(executable),"--branch-selftest"],cwd=tmp_path,
        capture_output=True,text=True,timeout=50,
    )
    assert report.returncode==0,(report.stdout,report.stderr)
    graph=verify_graph_report(json.loads(files["dragon-puzzle-proof.json"])["campaign_graph"])
    branches=sum(len(x.exits) for x in graph.chapters)
    assert report.stdout.count("DRAGON_BRANCH_PASS")==branches
    assert report.stdout.count("DRAGON_ENDING_PASS")==graph.ending_count
    assert report.stdout.strip().endswith(
        f"DRAGON_BRANCH_CAMPAIGN_PASS stages={stages} "
        f"transitions={branches} endings={graph.ending_count}"
    )
