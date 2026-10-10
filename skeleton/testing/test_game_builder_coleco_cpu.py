"""Adversarial real Z80 Coleco one-KiB bus, OS7 stubs, VDP and original replay."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.ai.game_builder.coleco_rom import make_col
from skeleton.testing.test_game_builder_coleco_native import _structural_fixture
from scripts.game_builder.emulate_coleco_ci import (
    ColecoCPUError,ColecoMachine,MOVES,_reference,
)


def _host():
    return ColecoMachine(make_col(_structural_fixture()))


def test_original_guest_z80_only_has_one_kib_ram_and_protected_cartridge_bios():
    h=_host()
    assert h.entry==0x8050
    assert h.nmi==0x8060
    assert h.rom_firmware_bundled is False
    for address in (0x6000,0x6400,0x7000,0x7C00):
        h.write(address,4)
    assert h.read(0x6000)==4
    assert h.read(0x7000)==4
    h.write(0x7300,6)
    assert h.read(0x6300)==6
    assert h.ram_state()["level"]==6
    with pytest.raises(ColecoCPUError,match="BIOS ROM"):
        h.write(0x1F85,0)
    with pytest.raises(ColecoCPUError,match="cartridge"):
        h.write(0x8000,0)
    with pytest.raises(ColecoCPUError,match="unpopulated"):
        h.write(0x5000,0)
    with pytest.raises(ColecoCPUError,match="unspecified"):
        h.read(0x1000)


def test_true_vblank_bios_trampoline_and_minimal_legal_os7_stubs():
    h=_host()
    assert h.read(0x66)==0xC3
    assert h.read(0x67)==0x60
    assert h.read(0x68)==0x80
    assert h.read(0x1F85)==0xC9
    assert h.read(0x1F7F)==0xC9
    assert h.bios_calls=={"MODE_1":1,"LOAD_ASCII":1}
    assert not h.rom_firmware_bundled
    h.write_port(0xC0,0)
    assert h.pad_selected
    h.pad=0xFD
    assert h.read_port(0xFC)==0xFD
    assert h.controller_reads==1
    assert MOVES=={"up":0,"right":1,"down":2,"left":3}
    h.write_port(0xFF,0x93)
    assert h.psg_writes==1
    with pytest.raises(ColecoCPUError,match="unknown"):
        h.read_port(0x34)


def test_real_tms9918_control_latch_vdp_name_table_and_video_nmi():
    h=_host()
    with pytest.raises(ColecoCPUError,match="before joystick strobe"):
        h.read_port(0xFC)
    with pytest.raises(ColecoCPUError,match="frame|VBlank|TMS9918"):
        h.assert_screen()
    h.write_port(0xBF,0xE0)
    h.write_port(0xBF,0x81)
    assert h.vdp_registers[1]==0xE0
    address=h.hero_address()
    h.write_port(0xBF,address & 255)
    with pytest.raises(ColecoCPUError,match="half"):
        h.write_port(0xBE,ord("@"))
    h.write_port(0xBF,0x40|(address>>8))
    h.write_port(0xBE,ord("@"))
    assert h.vram[address]==ord("@")
    assert h.video_writes==1
    assert h.read_port(0xBF)==0x80
    assert h.vblank_acks==1
    h.write_port(0xC0,0)
    with pytest.raises(ColecoCPUError,match="rendered"):
        h.assert_screen()
    h.video_writes=768
    h.assert_screen()
    with pytest.raises(ColecoCPUError,match="unknown"):
        h.write_port(0x19,1)


def _route():
    r={
        "schema":"skeleton.game_builder.game_boy_memory_replay.v1",
        "world_digest":"e"*64,"levels":1,
        "binary_compiled":False,"emulator_executed":False,
        "hardware_verified":False,"release_approved":False,
        "steps":[{"button":"up","level":0,"x":1,"y":1,
                 "health":4,"score":1,"gems_remaining":0,"won":1,"lost":0}],
    }
    r["route_sha256"]=sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return r


def _manifest():
    return {"platform":"colecovision","world_digest":"e"*64,
            "author_evidence_sha256":"b"*64,"native_binary_compiled":False}


def test_guest_original_replay_refuses_forged_hardware_authority_and_tampering():
    route,manifest=_route(),_manifest()
    assert _reference(route,manifest)==route
    bad=dict(route)
    bad["world_digest"]="a"*64
    with pytest.raises(ColecoCPUError,match="mismatch"):
        _reference(bad,manifest)
    bad={**route,"binary_compiled":True}
    with pytest.raises(ColecoCPUError,match="falsely"):
        _reference(bad,manifest)
    bad={**route,"steps":[]}
    bad["route_sha256"]=sha256(json.dumps(
        {k:v for k,v in bad.items() if k!="route_sha256"},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()
    with pytest.raises(ColecoCPUError,match="bounded"):
        _reference(bad,manifest)
    bad={**route,"steps":[123]}
    bad["route_sha256"]=sha256(json.dumps(
        {k:v for k,v in bad.items() if k!="route_sha256"},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()
    with pytest.raises(ColecoCPUError):
        _reference(bad,manifest)
    bad=_route()
    bad["steps"][0]["x"]=99
    with pytest.raises(ColecoCPUError,match="modified"):
        _reference(bad,manifest)
    with pytest.raises(ColecoCPUError,match="rights"):
        _reference(route,{**manifest,"author_evidence_sha256":""})
    with pytest.raises(ColecoCPUError,match="mismatch"):
        _reference(route,{**manifest,"platform":"sega_master_system"})
    with pytest.raises(ColecoCPUError,match="falsely"):
        _reference(route,{**manifest,"native_binary_compiled":True})
