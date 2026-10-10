"""Independently check Sega SMS Z80 guest memory, VDP and replay tamper gates."""
from __future__ import annotations

import json
from hashlib import sha256

import pytest

from scripts.game_builder.emulate_sms_z80_ci import (
    SMSCPUAcceptanceError,SMSHardware,_accepted_route,
    _BUTTONS,MAX_MOVES,
)


def _mock_device():
    # Host-only tests: not a playable Z80 emulator or accepted ROM proof.
    from skeleton.testing.test_game_builder_sms_native import _fake_sms_binary
    from skeleton.ai.game_builder.sms_rom import make_sms
    return SMSHardware(make_sms(_fake_sms_binary()))


def test_sms_cpu_video_address_registers_palette_and_joypad_real_hardware_contract():
    hardware=_mock_device()
    assert hardware.read(0)==0xC3
    assert hardware.read_port(0xDC)==0xFF
    hardware.pad=0xFB
    assert hardware.read_port(0xDC)==0xFB
    assert _BUTTONS=={"up":0,"down":1,"left":2,"right":3}
    hardware.write(0xC001,3)
    assert hardware.read(0xC001)==3
    assert hardware.read(0xE001)==3
    hardware.write(0xE001,4)
    assert hardware.read(0xC001)==4
    with pytest.raises(SMSCPUAcceptanceError,match="ROM"):
        hardware.write(0x0020,123)
    with pytest.raises(SMSCPUAcceptanceError,match="nonexistent"):
        hardware.write(0xA000,5)
    with pytest.raises(SMSCPUAcceptanceError,match="unsupported"):
        hardware.write_port(0x42,1)

    # Real SMS VDP register command: first value, then 0x80 | register index.
    for reg,val in ((0,4),(1,0x60),(2,0x0E)):
        hardware.write_port(0xBF,val)
        hardware.write_port(0xBF,0x80|reg)
    # Real CRAM write command at palette index zero.
    hardware.write_port(0xBF,0)
    hardware.write_port(0xBF,0xC0)
    for index in range(32):
        hardware.write_port(0xBE,0x3F if index==1 else 0)
    assert hardware.cram[1]==0x3F
    assert hardware.cram_writes==32
    # Tilemap write address is $3800+(row+1)*64+(x+1)*2.
    hardware.ram[1]=3
    hardware.ram[2]=4
    position=hardware.player_vram_address()
    hardware.write_port(0xBF,position&255)
    hardware.write_port(0xBF,0x40|(position>>8))
    hardware.write_port(0xBE,5)
    hardware.write_port(0xBE,0)
    hardware.assert_video()
    assert hardware.video_writes==2
    assert hardware.psg_writes==0
    hardware.write_port(0x7F,0x93)
    assert hardware.psg_writes==1
    assert hardware.read_port(0xBF)==0x80
    assert hardware.vblank_acks==1


def test_sms_cpu_host_fails_closed_on_bad_vram_palette_mode_and_impossible_video():
    h=_mock_device()
    with pytest.raises(SMSCPUAcceptanceError,match="Mode4 VDP"):
        h.assert_video()
    with pytest.raises(SMSCPUAcceptanceError,match="RGB222"):
        h.write_port(0xBF,0)
        h.write_port(0xBF,0xC0)
        h.write_port(0xBE,0xFF)
    with pytest.raises(SMSCPUAcceptanceError,match="half-pending"):
        h.write_port(0xBF,0x55)
        h.write_port(0xBE,5)
    h.pending_control=None
    h.write_port(0xBF,0)
    h.write_port(0xBF,0)
    with pytest.raises(SMSCPUAcceptanceError,match="valid write mode"):
        h.write_port(0xBE,5)


def _route():
    o={
        "schema":"skeleton.game_builder.game_boy_memory_replay.v1",
        "world_digest":"a"*64,"levels":1,
        "binary_compiled":False,"emulator_executed":False,
        "hardware_verified":False,"release_approved":False,
        "steps":[{"button":"right","level":0,"x":3,"y":3,
                 "health":3,"gems_remaining":0,"won":1,"lost":0,"score":1}],
    }
    o["route_sha256"]=sha256(json.dumps(o,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return o


def test_sms_cpu_replay_canonical_hash_bounds_and_foreign_action_denied():
    original=_route()
    assert _accepted_route(original)==original
    forged=_route()
    forged["steps"][0]["score"]=300
    with pytest.raises(SMSCPUAcceptanceError,match="tampered"):
        _accepted_route(forged)
    invalid=_route()
    invalid["steps"][0]["button"]="decrypting"
    with pytest.raises(SMSCPUAcceptanceError,match="tampered|action"):
        _accepted_route(invalid)
    with pytest.raises(SMSCPUAcceptanceError,match="unbounded"):
        _accepted_route({**_route(),"steps":[]})
    with pytest.raises(SMSCPUAcceptanceError,match="claims"):
        _accepted_route({**_route(),"binary_compiled":True})
    for weird in (False,3.1,-1,65536):
        r=_route()
        r["steps"][0]["level"]=weird
        r["route_sha256"]=sha256(json.dumps({k:v for k,v in r.items() if k!="route_sha256"},
             sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with pytest.raises(SMSCPUAcceptanceError,match="expectation"):
            _accepted_route(r)
    assert MAX_MOVES<=20000
