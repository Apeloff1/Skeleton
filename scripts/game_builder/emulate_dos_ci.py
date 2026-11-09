"""Run a compiled ORIGINAL 8086 DOS .COM in Unicorn's real 16-bit x86 CPU.

No DOS image or proprietary BIOS is required: *only* the three documented
BIOS/DOS interrupts used by this generated game are emulated at the boundary.
Unlike an assembler/header check, this drives every original maze action and
checks actual guest RAM, the rendered text-mode VRAM and the final victory.
No guest memory is patched to force a particular result.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from struct import unpack_from
from typing import Any

_STATE_NAMES = ("level", "x", "y", "health", "score", "gems_remaining", "won", "lost")
_SCAN_CODES = {"up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D}
_STATE_MARKER = b"SKELDOSSTATE"
_BASE_SEG = 0x2000
_GUEST_BASE = _BASE_SEG << 4
_VIDEO = 0xB8000
_SCHEMA = "skeleton.game_builder.dos_8086_reference_replay.v1"
_MAX_STEPS = 20_000


class DOSExecutionError(ValueError):
    """Native DOS 8086 replay, BIOS contract or CPU state diverged."""


def parse_guest_offsets(blob: bytes) -> dict[str, int]:
    if not 256 < len(blob) <= 0xFF00 or not blob.startswith(b"\x0e\x1f\xfc\xb8\x03\x00\xcd\x10"):
        raise DOSExecutionError("not an 8086 real-mode DOS COM image")
    if blob.count(_STATE_MARKER) != 1:
        raise DOSExecutionError("DOS RAM address marker missing or ambiguous")
    pos = blob.index(_STATE_MARKER) + len(_STATE_MARKER)
    if pos + 16 > len(blob):
        raise DOSExecutionError("truncated DOS guest state address table")
    offsets = unpack_from("<8H", blob, pos)
    if (len(set(offsets)) != 8
            or any(not 0x100 <= offset < 0x100 + len(blob) for offset in offsets)):
        raise DOSExecutionError("DOS guest-state offsets are out-of-bounds or overlapping")
    return dict(zip(_STATE_NAMES, offsets))


def validate_reference(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") != _SCHEMA:
        raise DOSExecutionError("unsupported DOS CPU replay schema")
    if any(data.get(k) is not False for k in (
        "binary_compiled", "cpu_emulator_executed",
        "physical_hardware_verified", "redistribution_licensed",
    )):
        raise DOSExecutionError("reference asserts unverifiable execution/rights claims")
    if not isinstance(data.get("world_digest"), str) or not re.fullmatch("[0-9a-f]{64}", data["world_digest"]):
        raise DOSExecutionError("missing original authored world digest")
    if type(data.get("levels")) is not int or not 1 <= data["levels"] <= 8:
        raise DOSExecutionError("invalid DOS 8086 stage count")
    steps = data.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= _MAX_STEPS:
        raise DOSExecutionError("invalid DOS replay size")
    for i, row in enumerate((data.get("initial"), *steps)):
        if not isinstance(row, dict):
            raise DOSExecutionError("missing original reference state")
        if i and row.get("key") not in _SCAN_CODES:
            raise DOSExecutionError("illegal DOS keyboard action")
        if not i and row.get("key") is not None:
            raise DOSExecutionError("initial state has input")
        for key in _STATE_NAMES:
            value = row.get(key)
            max_val = 65535 if key == "score" else 255
            if type(value) is not int or not 0 <= value <= max_val:
                raise DOSExecutionError(f"invalid guest register/memory state: {key}")
        if row["level"] >= data["levels"] or row["won"] not in (0,1) or row["lost"] not in (0,1):
            raise DOSExecutionError("invalid stage or termination flag")
    if steps[-1]["won"] != 1 or steps[-1]["lost"] != 0:
        raise DOSExecutionError("original replay does not terminate in victory")
    expected = data.get("trace_sha256")
    unsigned = {k:v for k,v in data.items() if k != "trace_sha256"}
    actual = sha256(json.dumps(unsigned,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if expected != actual:
        raise DOSExecutionError("DOS native reference trace integrity mismatch")
    return data


def _guest_state(cpu: Any, offsets: dict[str,int]) -> dict[str,int]:
    result = {}
    for key,offset in offsets.items():
        size = 2 if key == "score" else 1
        result[key] = int.from_bytes(cpu.mem_read(_GUEST_BASE+offset,size), "little")
    return result


def _assert_screen(cpu: Any, state: dict[str,int], index: int) -> None:
    # An interactive *visible game* must render its actual position and HUD.
    cell = (state["y"] + 2)*80 + (state["x"]+1)
    if cpu.mem_read(_VIDEO+2*cell,1) != b"@":
        raise DOSExecutionError(f"native DOS video player sprite missing at action {index}")
    for pos,key in ((26,"level"),(34,"gems_remaining"),(40,"health")):
        expected = 1 + state[key] if key=="level" else state[key]
        displayed = cpu.mem_read(_VIDEO+2*pos,1)
        if displayed != bytes((48+expected,)):
            raise DOSExecutionError(f"native DOS HUD {key} diverged at action {index}")
    score = b"".join(cpu.mem_read(_VIDEO+2*i,1) for i in range(49,53))
    if score != f'{state["score"]:04d}'.encode("ascii"):
        raise DOSExecutionError(f"native DOS HUD score diverged at action {index}")


def run_cpu(blob: bytes, reference: dict[str,Any]) -> dict[str,Any]:
    reference=validate_reference(reference)
    symbols=parse_guest_offsets(blob)
    try:
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UcError
        from unicorn.x86_const import (
            UC_X86_REG_AX, UC_X86_REG_CS, UC_X86_REG_DS,
            UC_X86_REG_ES, UC_X86_REG_SS, UC_X86_REG_SP, UC_X86_REG_IP,
        )
    except ImportError as exc:
        raise DOSExecutionError("actual 16-bit Unicorn CPU emulator is required") from exc

    uc=Uc(UC_ARCH_X86,UC_MODE_16)
    uc.mem_map(0,0x100000)
    uc.mem_write(_GUEST_BASE+0x100,blob)
    for register in (UC_X86_REG_CS,UC_X86_REG_DS,UC_X86_REG_SS):
        uc.reg_write(register,_BASE_SEG)
    uc.reg_write(UC_X86_REG_ES,_BASE_SEG)
    uc.reg_write(UC_X86_REG_SP,0xFFFE)
    uc.reg_write(UC_X86_REG_IP,0x100)
    status={"keyboard_inputs":0,"completed":False,"bios_screen_initialized":False}

    def interrupt(cpu:Any,number:int,_userdata:Any)->None:
        ax=cpu.reg_read(UC_X86_REG_AX)
        ah=(ax>>8)&255
        if number==0x10 and ah==0:
            if ax!=3 or status["bios_screen_initialized"]:
                raise DOSExecutionError("unexpected native BIOS screen initialization")
            status["bios_screen_initialized"]=True
            return
        if number==0x16 and ah==0:
            i=status["keyboard_inputs"]
            expected=reference["initial"] if i==0 else reference["steps"][i-1]
            seen=_guest_state(cpu,symbols)
            should={key:expected[key] for key in _STATE_NAMES}
            if seen!=should:
                raise DOSExecutionError(
                    f"CPU RAM differed at native DOS action {i}: expected {should}, saw {seen}"
                )
            _assert_screen(cpu,seen,i)
            if i==len(reference["steps"]):
                status["completed"]=True
                cpu.emu_stop()
                return
            cpu.reg_write(UC_X86_REG_AX,_SCAN_CODES[reference["steps"][i]["key"]]<<8)
            status["keyboard_inputs"]=i+1
            return
        if number==0x21 and ah==0x4c:
            raise DOSExecutionError("game exited before reference replay completed")
        raise DOSExecutionError(f"unexpected real-mode interrupt {number:02X} AH={ah:02X}")

    uc.hook_add(UC_HOOK_INTR,interrupt)
    try:
        uc.emu_start(_GUEST_BASE+0x100,0xFFFFF,timeout=15_000_000,count=10_000_000)
    except UcError as exc:
        raise DOSExecutionError(f"actual x86 real-mode CPU execution failed: {exc}") from exc
    if not status["completed"] or not status["bios_screen_initialized"]:
        raise DOSExecutionError("native DOS CPU gameplay stopped without real victory")
    return {
        "schema":"skeleton.game_builder.native_dos_cpu_attestation.v1",
        "world_digest":reference["world_digest"],
        "trace_sha256":reference["trace_sha256"],
        "binary_sha256":sha256(blob).hexdigest(),
        "native_bios_video_executed":True,
        "native_keyboard_actions":len(reference["steps"]),
        "actual_guest_ram_final":_guest_state(uc,symbols),
        "hardware_cpu_gameplay_passed":True,
        "physical_hardware_verified":False,
        "commercial_game_material_included":False,
        "distribution_licensed":False,
    }


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--com",required=True,type=Path)
    parser.add_argument("--trace",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError(str(args.out))
    blob=args.com.read_bytes()
    route=json.loads(args.trace.read_text(encoding="utf-8"))
    evidence=run_cpu(blob,route)
    with args.out.open("x",encoding="utf-8",newline="\n") as output:
        json.dump(evidence,output,sort_keys=True,indent=2)
        output.write("\n")
    print("ORIGINAL_8086_DOS_NATIVE_CPU_GAMEPLAY_VERIFIED",evidence["native_keyboard_actions"])


if __name__=="__main__":
    main()
