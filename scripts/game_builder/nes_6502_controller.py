"""Play one genuine world-derived controller move on the compiled NES CPU.

The previous boot smoke observes palette, nametable and sprite DMA. This
stricter stage now executes the *actual* 6502 game input handler and reads
the new sprite location from CPU RAM via the PPU sprite-DMA bus. No reference
prediction is used as the observed state. This verifies one safe movement,
not a complete playthrough or cycle-perfect game-console emulation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from scripts.game_builder.native_nes_ci import inspect_rom
from scripts.game_builder.nes_6502_boot import (
    ObservableNESBus, NES6502BootError, _MAX_INSTRUCTIONS, _ROM_SIZE,
)
from scripts.game_builder.nes_reproducibility_ci import _source
from skeleton.ai.game_builder.native_release_intake import _read_bounded


_DIRECTIONS = {
    "up":(0,-1),"down":(0,1),"left":(-1,0),"right":(1,0),
}


class NESControllerReplayError(NES6502BootError):
    """Genuine 6502 input path diverged from the authored NES world."""


def verify_original_nes_first_controller_move(
    *,
    compiled_rom: str | Path, source_directory: str | Path,
    expected_rom_sha256: str, expected_source_sha256: str,
    instruction_budget: int = _MAX_INSTRUCTIONS,
) -> dict[str, object]:
    """Compare actual 6502 sprite motion with one world-authored legal step.

    Original game metadata comes from the exact previously reviewed C/ASM,
    linker, makefile and manifest bytes. A supplied filename or title is
    never accepted as executable or copyright evidence.
    """
    if type(instruction_budget) is not int or not 50000 <= instruction_budget <= _MAX_INSTRUCTIONS:
        raise NESControllerReplayError("bounded original input execution budget invalid")
    for digest in (expected_rom_sha256,expected_source_sha256):
        if not isinstance(digest,str) or len(digest)!=64 or any(
            x not in "0123456789abcdef" for x in digest
        ):
            raise NESControllerReplayError("reviewed NES ROM and source SHA-256 required")
    source=_source(Path(source_directory))
    if source["digest"] != expected_source_sha256:
        raise NESControllerReplayError("authored NES source changed after compilation")
    manifest=source["manifest"]
    action=manifest.get("original_first_controller_action")
    initial=manifest.get("original_first_player_spawn")
    target=manifest.get("original_first_controller_target")
    if action not in _DIRECTIONS:
        raise NESControllerReplayError("reviewed original first controller action invalid")
    if (not isinstance(initial,list) or not isinstance(target,list)
        or len(initial)!=2 or len(target)!=2
        or any(type(n) is not int for n in (*initial,*target))):
        raise NESControllerReplayError("missing original game first-move coordinates")
    dx,dy=_DIRECTIONS[action]
    if (target[0]!=initial[0]+dx or target[1]!=initial[1]+dy
        or not (0<=initial[0]<manifest["width"] and 0<=initial[1]<manifest["height"])
        or not (0<=target[0]<manifest["width"] and 0<=target[1]<manifest["height"])):
        raise NESControllerReplayError("first game controller action/target not bound to authored world")
    data=_read_bounded(Path(compiled_rom),max_bytes=_ROM_SIZE)
    if sha256(data).hexdigest()!=expected_rom_sha256:
        raise NESControllerReplayError("compiled NES machine code differs from reviewed artifact")
    checked=inspect_rom(Path(compiled_rom))
    if checked["sha256"]!=expected_rom_sha256:
        raise NESControllerReplayError("NES cartridge replaced during control replay")
    try:
        from py65.devices.mpu6502 import MPU
    except ImportError as exc:
        raise NESControllerReplayError("Py65 NMOS CPU backend required for native gameplay verification") from exc

    bus=ObservableNESBus(data)
    cpu=MPU(memory=bus,pc=None)
    bus.cpu=cpu
    booted_at=None
    sprite_dma_before=0
    read_4016_before=0
    first_sprite=None
    for index in range(instruction_budget):
        if not 0x8000<=cpu.pc<=0xFFFF:
            raise NESControllerReplayError(
                "original NES program counter escaped mapped 6502 cartridge PRG"
            )
        cpu.step()
        if booted_at is None:
            if (bus.palette_writes>=32 and bus.nametable_writes>=960
                and bus.oam_dma_count>=1 and bus.ppu_reads>=2):
                if sha256(bus.nametable[:960]).hexdigest()!=manifest.get("original_stage_zero_bg_sha256"):
                    raise NESControllerReplayError(
                        "actual original-game 6502 PPU name table differs from world tilemap"
                    )
                first_sprite=(bus.oam[3],bus.oam[0])
                expected_sprite=(initial[0]*8, (initial[1]*8-1)&255)
                if first_sprite!=expected_sprite:
                    raise NESControllerReplayError(
                        f"native reset player sprite {first_sprite} != authored spawn {expected_sprite}"
                    )
                booted_at=index+1
                sprite_dma_before=bus.oam_dma_count
                read_4016_before=bus.reads_4016
                bus.set_button(action)
        elif bus.oam_dma_count>sprite_dma_before:
            observed=(bus.oam[3],bus.oam[0])
            expected=(target[0]*8,(target[1]*8-1)&255)
            if bus.reads_4016-read_4016_before<8:
                raise NESControllerReplayError(
                    "real NES input handler did not read full 8-bit controller shift register"
                )
            if observed!=expected:
                raise NESControllerReplayError(
                    f"native NES game controller {action} observed sprite {observed} "
                    f"instead of original safe target {expected}"
                )
            return {
                "schema":"skeleton.game_builder.nes_original_6502_first_input.v1",
                "target":"nintendo_famicom",
                "rom_sha256":expected_rom_sha256,
                "source_sha256":expected_source_sha256,
                "original_world_sha256":manifest["world_digest"],
                "reference_safe_replay_sha256":manifest["safe_replay_digest"],
                "cpu_kind":"py65-nmos6502",
                "original_first_controller_action":action,
                "authored_spawn":initial,
                "authored_first_safe_target":target,
                "original_stage_zero_bg_sha256":manifest["original_stage_zero_bg_sha256"],
                "actual_ppu_stage_zero_bg_sha256":sha256(bus.nametable[:960]).hexdigest(),
                "native_observed_sprite_before":list(first_sprite),
                "native_observed_sprite_after":list(observed),
                "native_input_port_reads":bus.reads_4016-read_4016_before,
                "native_sprite_dma_transfers":bus.oam_dma_count,
                "original_game_boot_instructions":booted_at,
                "original_first_move_cpu_instructions":index+1-booted_at,
                "original_total_cpu_instructions":index+1,
                "original_6502_input_executed":True,
                "original_safe_first_move_matched":True,
                "instruction_limit_enforced":True,
                "cycle_accurate_ppu_apu_verified":False,
                "full_controller_route_replayed":False,
                "physical_hardware_verified":False,
                "legal_distribution_authorized":False,
            }
    raise NESControllerReplayError(
        "original 6502 controller move exceeded fixed CPU budget; "
        f"pc={cpu.pc:#06x} first_dma={sprite_dma_before} "
        f"current_dma={bus.oam_dma_count} reads={bus.reads_4016}"
    )


def main() -> None:
    import argparse
    from scripts.game_builder.sega_reproducibility_ci import emit_receipt
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom",type=Path,required=True)
    p.add_argument("--source-dir",type=Path,required=True)
    p.add_argument("--rom-sha256",required=True)
    p.add_argument("--source-sha256",required=True)
    p.add_argument("--receipt-out",type=Path,required=True)
    opts=p.parse_args()
    result=verify_original_nes_first_controller_move(
        compiled_rom=opts.rom,source_directory=opts.source_dir,
        expected_rom_sha256=opts.rom_sha256,
        expected_source_sha256=opts.source_sha256,
    )
    emit_receipt(opts.receipt_out,result)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
