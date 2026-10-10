"""Real original 2bpp native source art regression, no ROM extraction."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZipFile
import json

import pytest

from skeleton.ai.webcrawler.dragon_native_artforge import (
    FILENAME, HEROES_8, THEMES_8, apply_original_art,
    make_art, original_tiles, raw_tile_data, source_asm, verify_original_art,
)
from skeleton.ai.webcrawler.dragon_retro_assets import BITMAPS,NAMES,decode_tile
from skeleton.ai.webcrawler.dragon_native_production import (
    PortableGameDesign, ProductionRequest, _adapt_portable_design,
    _render, build_source_bundle, make_source_release, publish_production,
    validate_native_source, verify_source_bundle, verify_source_release,
    verify_published_production,
)

def make_request(target="game_boy",style="arcade_score_attack",**changes):
    game=ProductionRequest(
        title="Original Art Star Quest",
        targets=(target,), style=style, original_work_attested=True,
        seed=19, portable_design=PortableGameDesign(
            hero="robot", quest_theme="clockwork", palette="dmg_green",
            stages=5, candidates=7,
        ),
    )
    return replace(game,**changes)


@pytest.mark.parametrize("hero",sorted(HEROES_8))
@pytest.mark.parametrize("world",sorted(THEMES_8))
def test_all_original_characters_and_worlds_create_complete_native_sprite_sets(hero,world):
    tiles=original_tiles(hero=hero,theme=world,palette="dmg_green",seed=7)
    assert tuple(tiles)==NAMES
    assert len(tiles)==8
    assert all(len(bitmap)==8 and all(len(row)==8 for row in bitmap)
               for bitmap in tiles.values())
    assert all(set("".join(bitmap))<=set("0123") for bitmap in tiles.values())
    assert tiles["dragon"]!=tiles["star"]
    for order in ("gb","nes"):
        data=raw_tile_data(tiles,order)
        assert len(data)==8*16
        for i,name in enumerate(NAMES):
            assert decode_tile(data[i*16:(i+1)*16],target=order)==tiles[name]


@pytest.mark.parametrize("target,style", [
    ("game_boy","arcade_score_attack"),
    ("game_boy","side_scrolling_platformer"),
    ("game_boy_color","arcade_score_attack"),
    ("nes","arcade_score_attack"),
])
def test_original_art_changes_actual_native_console_runtime_source(target,style):
    custom=make_request(target,style)
    native=_render(custom,target)
    hashes=validate_native_source(native)
    assert FILENAME in hashes
    claimed=json.loads(native.files[FILENAME])
    _,port=_adapt_portable_design(custom,target)
    verified=verify_original_art(native.files,port,style)
    assert verified["sprites_verified"]==8
    assert claimed["hero"]=="robot"
    assert claimed["quest_theme"]=="clockwork"
    assert claimed["runtime_applied"] is True
    if "dragon-pixel-art.json" in native.files:
        older_catalog=json.loads(native.files["dragon-pixel-art.json"])
        assert older_catalog["runtime_tiles_replaced_by_original_design"]
        assert [x["fingerprint"] for x in older_catalog["sprites"]]==claimed["pixel_digests"]

    baseline=make_request(target,style,
        portable_design=PortableGameDesign(
            hero="hatchling",quest_theme="forest",palette="dmg_green",
            stages=5,candidates=7,
        ))
    older=_render(baseline,target)
    main="src/main.s" if target=="nes" else "src/main.asm"
    assert native.files[main]!=older.files[main]
    assert json.loads(native.files[FILENAME])!=json.loads(older.files[FILENAME])
    _,receipt=make_source_release(native,custom)
    assert receipt.original_art_sha256 is not None


@pytest.mark.parametrize("target,style", [
    ("game_boy","arcade_score_attack"),
    ("game_boy","side_scrolling_platformer"),
    ("nes","arcade_score_attack"),
])
def test_original_native_art_release_verifier_reconstructs_assembly(target,style):
    custom=make_request(target,style)
    project=_render(custom,target)
    binary,_=make_source_release(project,custom)
    receipt=verify_source_release(binary)
    assert receipt["original_art_sha256"] is not None
    assert receipt["target"]==target


@pytest.mark.parametrize("target,style", [
    ("game_boy","arcade_score_attack"),
    ("game_boy","side_scrolling_platformer"),
    ("nes","arcade_score_attack"),
])
def test_forged_visual_source_does_not_pass_portable_art_replay(target,style):
    game=make_request(target,style)
    project=_render(game,target)
    files=dict(project.files)
    assembly="src/main.s" if target=="nes" else "src/main.asm"
    filename,pattern,original=source_asm(
        original_tiles(hero="robot",theme="clockwork",palette="dmg_green",seed=19),
        style,target,
    )
    assert assembly==filename
    # Replace one original 2bpp byte: a valid assembler directive and valid
    # hardware budget cannot launder an incorrect actor into approved art.
    assert "$" in original
    pos=files[assembly].find(original)
    assert pos>=0
    corrupted=original.replace("$00","$01",1)
    files[assembly]=files[assembly].replace(original,corrupted)
    _,plan=_adapt_portable_design(game,target)
    with pytest.raises(ValueError,match="original artwork|runtime tile|art source"):
        verify_original_art(files,plan,style)


@pytest.mark.parametrize("profile",[
    {"hero":"licensed_character"},
    {"theme":"commercial_game"},
    {"palette":"shader_from_rom"},
    {"seed":True},
    {"seed":-1},
])
def test_original_sprite_compiler_does_not_accept_unlicensed_or_unbounded_values(profile):
    params=dict(hero="robot",theme="space",palette="dmg_green",seed=1)
    params.update(profile)
    with pytest.raises(ValueError):
        original_tiles(**params)


def test_source_bundle_offline_audit_replays_console_art_and_pc_fidelity():
    game=make_request("game_boy", targets=("game_boy","nes","pc_linux"),
                      max_portfolio_bytes=3_000_000)
    payload,index=build_source_bundle(game,authorized=True)
    result=verify_source_bundle(payload)
    assert result["target_count"]==3
    assert len(index["entries"])==3
    assert all(item["original_art_sha256"] for item in index["entries"]
               if item["target"] in ("game_boy","nes"))
    assert next(item for item in index["entries"]
                if item["target"]=="pc_linux")["original_art_sha256"] is None
    with ZipFile(BytesIO(payload)) as archive:
        for filename in archive.namelist():
            if filename.startswith("releases/"):
                assert verify_source_release(archive.read(filename))


def test_original_sprite_palette_honors_bounded_hardware_color_indices():
    base=original_tiles(hero="explorer",theme="space",palette="dmg_green",seed=11)
    alt=original_tiles(hero="explorer",theme="space",palette="modern_neon",seed=11)
    assert base!=alt
    assert len(raw_tile_data(base,"gb"))==len(raw_tile_data(alt,"nes"))==128
    assert base["dragon"]==HEROES_8["explorer"]
    assert set("".join(alt["dragon"]))<=set("0123")



@pytest.mark.parametrize("target,expected", [
    ("game_boy", ".playerMoving"),
    ("game_boy_color", ".playerMoving"),
    ("nes", "DragonMoving:"),
])
def test_original_hero_animation_runs_on_real_controller_movement(target,expected):
    approved=make_request(target)
    project=_render(approved,target)
    source=project.files["src/main.s" if target=="nes" else "src/main.asm"]
    assert expected in source
    if target=="nes":
        assert "DragonAnimationTick: .res 1" in source
        assert "sta $0201" in source
        assert "lda #2\nDragonPaint:" in source
        assert "sta DragonPreviousX" in source
    else:
        assert "PreviousPlayerX: ds 1" in source
        assert "PreviousPlayerY: ds 1" in source
        assert "ld [OAM+2], a" in source
        assert "ld a, 2\n.drawHeroFrame:" in source
    assert verify_source_release(make_source_release(project,approved)[0])["evidence"]=="source_generated"


@pytest.mark.parametrize("target,animation_label", [
    ("game_boy", ".playerMoving"),
    ("nes", "DragonMoving:"),
])
def test_cartridge_art_auditor_does_not_accept_inert_hero_animation(target,animation_label):
    from skeleton.ai.webcrawler.dragon_native_artforge import verify_original_art
    game=make_request(target)
    source=_render(game,target)
    files=dict(source.files)
    name="src/main.s" if target=="nes" else "src/main.asm"
    files[name]=files[name].replace(animation_label,animation_label[:-1]+"Fake:",1)
    _,port=_adapt_portable_design(game,target)
    with pytest.raises(ValueError,match="animation source"):
        verify_original_art(files,port,"arcade_score_attack")
