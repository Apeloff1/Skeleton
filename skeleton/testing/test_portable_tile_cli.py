"""Real offline native tile-command tests, including source custody checks."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.ai.game_builder.portable_tile_cli import SCHEMA, main


TILE=[[((x+y)&3) for x in range(8)] for y in range(8)]


def write_input(path: Path, *, count: int=1) -> None:
    path.write_text(json.dumps({
        "schema":SCHEMA,
        "project_id":"authored-original-game",
        "tiles":[TILE for _ in range(count)],
    }),encoding="utf-8")


@pytest.mark.parametrize("target,syntax,directive",[
    ("nintendo_game_boy","rgbds","db $"),
    ("nintendo_famicom","ca65",".byte $"),
    ("sega_master_system","c99","static const uint8_t"),
])
def test_cli_emits_real_native_tile_declaration_and_unverified_receipt(
    tmp_path,capsys,target,syntax,directive,
):
    source=tmp_path/"original.json"
    output=tmp_path/"tiles.src"
    write_input(source,count=2)
    assert main([
        "--input",str(source),"--output",str(output),
        "--target",target,"--syntax",syntax,"--acknowledge-original",
    ])==0
    emitted=output.read_text(encoding="utf-8")
    assert directive in emitted
    receipt=json.loads(capsys.readouterr().out)
    assert receipt["schema"]=="skeleton.game_builder.portable_tile_compile.v1"
    assert receipt["project_id"]=="authored-original-game"
    assert receipt["target_id"]==target
    assert receipt["tile_count"]==2
    assert receipt["source_sha256"]==sha256(emitted.encode("utf-8")).hexdigest()
    assert receipt["original_source_acknowledged"] is True
    assert receipt["independent_rights_cleared"] is False
    assert receipt["native_binary_verified"] is False
    assert receipt["release_authorized"] is False


def test_cli_refuses_missing_originality_acknowledgement(tmp_path,capsys):
    source=tmp_path/"original.json"
    output=tmp_path/"export.asm"
    write_input(source)
    assert main([
        "--input",str(source),"--output",str(output),
        "--target","nintendo_game_boy","--syntax","rgbds",
    ])==2
    assert not output.exists()
    assert "acknowledgement" in capsys.readouterr().err


@pytest.mark.parametrize("invalid",[
    '{"schema":"a","schema":"b","project_id":"game","tiles":[]}',
    '{"schema":"skeleton.game_builder.original_indexed_tiles.v1","project_id":"game","tiles":[NaN]}',
    '{"not_the_schema":1}',
])
def test_cli_refuses_duplicate_keys_nonfinite_and_wrong_contract(tmp_path,invalid):
    source=tmp_path/"invalid.json"
    output=tmp_path/"out.asm"
    source.write_text(invalid,encoding="utf-8")
    assert main([
        "--input",str(source),"--output",str(output),
        "--target","nintendo_game_boy","--syntax","rgbds","--acknowledge-original",
    ])==2
    assert not output.exists()


def test_cli_does_not_overwrite_prior_source_or_follow_symlink(tmp_path):
    source=tmp_path/"original.json"
    output=tmp_path/"out.asm"
    write_input(source)
    output.write_text("KEEP CURRENT OWNER DATA",encoding="utf-8")
    args=[
        "--input",str(source),"--output",str(output),
        "--target","nintendo_game_boy","--syntax","rgbds","--acknowledge-original",
    ]
    assert main(args)==2
    assert output.read_text(encoding="utf-8")=="KEEP CURRENT OWNER DATA"
    existing=tmp_path/"existing.json"
    write_input(existing)
    link=tmp_path/"symbolic_input.json"
    try:
        link.symlink_to(existing)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable on this filesystem")
    args[1]=str(link)
    output.unlink()
    assert main(args)==2
    assert not output.exists()


def test_cli_detects_source_replacement_between_validation_and_open(tmp_path,monkeypatch):
    from skeleton.ai.game_builder import portable_tile_cli
    source=tmp_path/"original.json"
    replacement=tmp_path/"replacement.json"
    output=tmp_path/"out.asm"
    write_input(source)
    write_input(replacement)
    original_open=portable_tile_cli.os.open
    state={"swapped":False}

    def swap_and_open(path,flags,*args,**kwargs):
        if os.fspath(path)==os.fspath(source) and not state["swapped"]:
            state["swapped"]=True
            os.replace(replacement,source)
        return original_open(path,flags,*args,**kwargs)

    monkeypatch.setattr(portable_tile_cli.os,"open",swap_and_open)
    assert main([
        "--input",str(source),"--output",str(output),
        "--target","nintendo_game_boy","--syntax","rgbds","--acknowledge-original",
    ])==2
    assert state["swapped"]
    assert not output.exists()


def test_cli_enforces_bounded_source_size_before_parsing(tmp_path):
    source=tmp_path/"oversized.json"
    output=tmp_path/"out.asm"
    source.write_bytes(b" " * 256_001)
    assert main([
        "--input",str(source),"--output",str(output),
        "--target","nintendo_game_boy","--syntax","rgbds","--acknowledge-original",
    ])==2
    assert not output.exists()
