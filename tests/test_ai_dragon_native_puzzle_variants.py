"""Original procedural puzzle stages: solver-proven novelty, bounded change, replay."""
from __future__ import annotations
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile
import json,pytest
from skeleton.ai.webcrawler.dragon_native_puzzle import (
    BASE_LEVELS,MAX_SEARCH,solve_grid,transformed_level,emit_native_puzzle,
)
from skeleton.ai.webcrawler.dragon_native_puzzle_variants import (
    vary_original_level,variant_report,MAX_TRIALS,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    PortableGameDesign,ProductionRequest,_render,make_source_release,
    verify_source_release,build_source_bundle,verify_source_bundle,
)

def design(seed=3,stages=4,difficulty=8):
    return ProductionRequest(
        title="Original Labyrinth Crate Quest",
        style="fixed_screen_puzzle",targets=("pc_linux",),
        seed=seed,original_work_attested=True,
        portable_design=PortableGameDesign(
            stages=stages,difficulty=difficulty,
            procedural_levels=True,
        ),
    )

@pytest.mark.parametrize("seed,stage,difficulty", [
    (0,0,5),(17,1,8),(1024,2,10),(2026,3,4),
    (1337,4,7),(0xffffffff,7,9),
])
def test_authored_procedural_game_layouts_are_deterministic_and_solvable(seed,stage,difficulty):
    first=transformed_level(stage,seed,difficulty,procedural=True)
    second=transformed_level(stage,seed,difficulty,procedural=True)
    assert first==second
    assert len(first)==10
    assert all(len(row)==12 for row in first)
    assert sum(row.count("$") for row in first)==sum(row.count("o") for row in first)
    moves,visited=solve_grid(first)
    assert 0<len(moves)<=350 and 0<visited<MAX_SEARCH

def test_variants_produce_genuinely_distinct_original_soluble_layouts():
    changed=0
    for seed in (1,2,3,5,8,13):
        stage=seed%4
        original=transformed_level(stage,seed,difficulty=8,procedural=False)
        varied,evidence=vary_original_level(
            original,seed=seed,stage=stage,difficulty=8,solve=solve_grid,
        )
        assert evidence.base_digest
        assert evidence.chosen_digest
        assert evidence.search_trials<=MAX_TRIALS
        assert evidence.added_walls<=5
        assert solve_grid(varied)[0]
        assert variant_report(evidence)["status"] in ("solvable_variant","solvable_baseline")
        changed+=varied!=original
    assert changed>=1,"algorithm never produced a new solvable layout"

def test_legacy_campaigns_remain_the_same_until_author_opts_in():
    assert transformed_level(2,42)==transformed_level(2,42,procedural=False)
    baseline=emit_native_puzzle(seed=42,stages=3)
    assert json.loads(baseline["dragon-puzzle-proof.json"])["procedural"] is False

def test_real_native_source_embeds_solver_verified_procedural_campaign():
    spec=design()
    game=_render(spec,"pc_linux")
    receipt=json.loads(game.files["dragon-puzzle-proof.json"])
    assert receipt["procedural"] is True
    assert receipt["stages"]==4
    for level,report in enumerate(receipt["level_proofs"]):
        grid=transformed_level(level,spec.seed,8,procedural=True)
        moves,_=solve_grid(grid)
        assert report["solution"]==moves
        assert report["optimal_within_abstract_grid"]
    payload,_=make_source_release(game,spec)
    assert verify_source_release(payload)["source_fingerprint"]==game.digest
    with ZipFile(BytesIO(payload)) as archive:
        assert b"DRAGON_NATIVE_PUZZLE_HINTS PASS" in archive.read("source/src/main.c")

def test_native_source_browser_delivery_can_include_real_procedural_puzzles():
    spec=replace(design(stages=2),max_portfolio_bytes=3_000_000)
    output,index=build_source_bundle(spec,authorized=True)
    assert index["target_count"]==1
    assert verify_source_bundle(output)["status"]=="verified_source_bundle"
    with ZipFile(BytesIO(output)) as archive:
        nested=next(x for x in archive.namelist() if x.startswith("releases/"))
        with ZipFile(BytesIO(archive.read(nested))) as release:
            proof=json.loads(release.read("source/dragon-puzzle-proof.json"))
            assert proof["procedural"] is True

@pytest.mark.parametrize("bad",[
    {"procedural_levels":1},{"procedural_levels":"yes"},
])
def test_source_procedural_authority_requires_strict_boolean(bad):
    with pytest.raises(ValueError):
        PortableGameDesign(**bad).validate()

def test_procedural_level_generation_rejects_unimplemented_console_targets():
    illegal=replace(design(),targets=("nes",))
    with pytest.raises(ValueError,match="desktop puzzles"):
        illegal.validate()

def test_procedural_map_generation_refuses_invalid_range_and_flag():
    with pytest.raises(ValueError):
        transformed_level(0,1,procedural="enabled")
    with pytest.raises(ValueError):
        vary_original_level(BASE_LEVELS[0],seed=1,stage=9,difficulty=5,solve=solve_grid)
