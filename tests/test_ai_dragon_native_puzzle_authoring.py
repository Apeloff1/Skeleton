"""Original game-editor levels: native compilation, exact solving, tamper bounds."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import json
import pytest

from skeleton.ai.webcrawler.dragon_native_puzzle import (
    BASE_LEVELS,emit_native_puzzle,
)
from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import (
    SCHEMA,authored_document,load_authored_level_pack,
    parse_authored_document,preview_authored_levels,starter_authored_levels,
    validate_authored_levels,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,_render,make_source_release,
    verify_source_release,build_source_bundle,verify_source_bundle,
)
from skeleton.ai.webcrawler.dragon_native_desktop import _puzzle_proof

def authored_request(levels):
    return ProductionRequest(
        title="Original Authored Moon Puzzles",
        style="fixed_screen_puzzle",
        targets=("pc_linux",),seed=2019,original_work_attested=True,
        portable_design=PortableGameDesign(stages=len(levels),difficulty=5),
        authored_puzzles=levels,
    )

@pytest.mark.parametrize("count",[1,2,4,8])
def test_starter_boards_are_distinct_genuine_solvable_12_by_10_games(count):
    document=starter_authored_levels(count)
    pack=parse_authored_document(document)
    assert document["level_count"]==count
    assert len(pack.levels)==count
    assert len({x.layout_sha256 for x in pack.levels})==count
    assert all(0<x.shortest_moves<400 for x in pack.levels)
    assert pack.digest==document["digest"]

def test_original_user_map_editor_generates_actual_native_source_and_solver_proof():
    levels=(BASE_LEVELS[0],BASE_LEVELS[1],BASE_LEVELS[2])
    approved=authored_request(levels)
    project=_render(approved,"pc_linux")
    proof=json.loads(project.files["dragon-puzzle-proof.json"])
    assert proof["authoring_mode"]=="authored"
    assert proof["authoring_digest"]==validate_authored_levels(levels).digest
    assert proof["authored_level_rows"]==[list(x) for x in levels]
    assert len(proof["level_proofs"])==3
    assert all(level["solution"] for level in proof["level_proofs"])
    binary,_=make_source_release(project,approved)
    receipt, recovered=_puzzle_proof(binary)
    assert receipt["target"]=="pc_linux"
    assert verify_source_release(binary)["source_fingerprint"]==project.digest
    assert "dragon_levels" in recovered["include/dragon_puzzle.h"]

def test_authored_browsable_source_zip_contains_verifiable_real_level_geometry():
    approved=replace(authored_request((BASE_LEVELS[0],BASE_LEVELS[2])),
                     max_portfolio_bytes=3_000_000)
    body,index=build_source_bundle(approved,authorized=True)
    assert verify_source_bundle(body)["target_count"]==1
    with ZipFile(BytesIO(body)) as archive:
        name=next(x for x in archive.namelist() if x.startswith("releases/"))
        inner=archive.read(name)
    receipt,inventory=_puzzle_proof(inner)
    proof=json.loads(inventory["dragon-puzzle-proof.json"])
    assert tuple(proof["authored_level_rows"][0])==BASE_LEVELS[0]
    assert proof["authoring_mode"]=="authored"

@pytest.mark.parametrize("broken",[
    (),
    ((("............",)*10),),
    ((("############",)*10),),
    ((("@"*12,)*10),),
    (BASE_LEVELS[0],BASE_LEVELS[0]),
    tuple(BASE_LEVELS[0] for _ in range(9)),
])
def test_original_native_game_editor_rejects_incomplete_invalid_or_repeated_board(broken):
    with pytest.raises(ValueError):
        validate_authored_levels(broken)

def test_author_puzzle_level_pack_does_not_trust_attested_digest_or_claim(tmp_path):
    levels=(BASE_LEVELS[0],)
    document=authored_document(levels)
    path=tmp_path/"level-pack.json"
    path.write_text(json.dumps(document))
    pack=load_authored_level_pack(path)
    assert pack.levels[0].shortest_solution
    malicious={**document,"claim":"Nintendo-licensed exclusive original games"}
    path.write_text(json.dumps(malicious))
    with pytest.raises(ValueError):
        load_authored_level_pack(path)
    tampered={**document,"digest":"f"*64}
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError):
        load_authored_level_pack(path)
    path.write_text(json.dumps({**document,"script":"os.system"}))
    with pytest.raises(ValueError):
        load_authored_level_pack(path)

def test_author_request_rejects_mismatched_campaign_size_unsupported_targets():
    base=authored_request((BASE_LEVELS[0],BASE_LEVELS[1]))
    with pytest.raises(ValueError):
        replace(base,targets=("game_boy",)).validate()
    with pytest.raises(ValueError):
        replace(base,style="arcade_score_attack").validate()
    with pytest.raises(ValueError):
        replace(base,portable_design=PortableGameDesign(stages=4)).validate()
    with pytest.raises(ValueError):
        replace(base,portable_design=PortableGameDesign(stages=2,
                                                        procedural_levels=True)).validate()

def test_read_only_authoring_preview_performs_actual_exact_solver_pass():
    levels=(BASE_LEVELS[0],BASE_LEVELS[3])
    preview=preview_authored_levels(levels)
    assert preview["ok"]
    assert preview["total_stages"]==2
    assert [x["crates"] for x in preview["stages"]]==[1,2]
    assert all(x["solver_states"]>0 for x in preview["stages"])
    assert "not compiled" in preview["scope"]



def test_author_replay_rejects_modified_generated_c_game_even_with_matching_zip_hash():
    from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import validate_authored_levels
    from skeleton.ai.webcrawler.dragon_native_desktop import _puzzle_proof
    from skeleton.ai.webcrawler.dragon_native_production import (
        make_source_release,ProductionRequest,PortableGameDesign,_render,
    )
    from skeleton.ai.webcrawler.dragon_native_projects import NativeProject,digest
    from dataclasses import replace

    levels=(BASE_LEVELS[0],)
    approved=authored_request(levels)
    native=_render(approved,"pc_linux")
    original=dict(native.files)
    assert "if(!perform(trace[i]))return 4;" in original["src/main.c"]
    original["src/main.c"]=original["src/main.c"].replace(
        "if(!perform(trace[i]))return 4;",
        "if(!perform(trace[i]))return 0;",
        1,
    )
    # Recreate the same source-only cryptographic envelope with altered
    # generated game behavior; independent emitter replay must still reject.
    tampered=replace(native,files=original,digest=digest(original))
    payload,_=make_source_release(tampered,approved)
    with pytest.raises(ValueError,match="native runnable source"):
        _puzzle_proof(payload)


def test_author_replay_rejects_puzzle_layout_inconsistent_with_generated_header():
    from dataclasses import replace
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    from skeleton.ai.webcrawler.dragon_native_desktop import _puzzle_proof
    game=authored_request((BASE_LEVELS[0],))
    native=_render(game,"pc_linux")
    files=dict(native.files)
    files["include/dragon_puzzle.h"]=files["include/dragon_puzzle.h"].replace(
        "#define LEVEL_COUNT 1","#define LEVEL_COUNT 2",1,
    )
    modified=replace(native,files=files,digest=digest(files))
    release,_=make_source_release(modified,game)
    with pytest.raises(ValueError,match="native runnable source"):
        _puzzle_proof(release)
