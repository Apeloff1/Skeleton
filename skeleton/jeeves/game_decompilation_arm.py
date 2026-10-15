"""Static, bounded ARM7TDMI ARM-state control-flow map for lawful GBA ROMs.

The GBA CPU is dual ARM/Thumb. This maps only 32-bit ARM-state reachable
branches from a structurally recognized cartridge entrypoint. Register-built
targets, Thumb mode, BIOS, EWRAM, IRQ and decompression remain out of scope.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from .game_learning_ingestion import _rom_gba

MAX_ARM_WORDS = 4096
BASE = 0x08000000
ALU = ("AND","EOR","SUB","RSB","ADD","ADC","SBC","RSC",
       "TST","TEQ","CMP","CMN","ORR","MOV","BIC","MVN")
COND = ("EQ","NE","CS","CC","MI","PL","VS","VC",
        "HI","LS","GE","LT","GT","LE","","NV")


def disassemble_gba_arm_entry(data: bytes, *, limit: int = 2048) -> dict[str, Any]:
    if type(data) is not bytes or type(limit) is not int or not 1<=limit<=MAX_ARM_WORDS:
        raise ValueError("GBA ARM disassembler expects exact ROM bytes and bounded word budget")
    header=_rom_gba(data)
    if not header["header_checksum_valid"]:
        raise ValueError("GBA fixed boot header checksum differs; refuse untrusted execution map")
    queue=deque([BASE])
    visited=set()
    rows={}
    edges=set()
    while queue and len(rows)<limit:
        addr=queue.popleft()
        while addr not in visited and len(rows)<limit:
            off=addr-BASE
            if off<0 or off+4>len(data) or off%4:
                break
            word=int.from_bytes(data[off:off+4],"little")
            visited.add(addr)
            condition=(word>>28)&15
            suff=COND[condition]
            target=None
            flow=None
            stop=False
            if ((word>>25)&7)==5: # ARM B / BL
                raw=word&0xFFFFFF
                signed=raw-(1<<24) if raw&(1<<23) else raw
                target=(addr+8+signed*4)&0xFFFFFFFF
                link=bool(word&(1<<24))
                mnemonic=("BL" if link else "B")+suff
                flow="call" if link else "branch"
                if not link and condition==14:
                    stop=True
            elif word&0x0FFFFFF0==0x012FFF10:
                mnemonic="BX"+suff
                # Register target could switch into Thumb mode, which is
                # not statically proven or followed here.
                stop=True
            elif (word>>26)&3==1:
                mnemonic=("LDR" if word&(1<<20) else "STR")+suff
            elif (word>>26)&3==0:
                mnemonic=ALU[(word>>21)&15]+suff
            elif (word>>24)&15==15:
                mnemonic="SWI"+suff
            else:
                mnemonic="ARM_WORD_NOT_FULLY_DECODED"
            if target is not None and BASE<=target<BASE+len(data) and target%4==0:
                edges.add((addr,target,flow))
                if target not in visited:
                    queue.append(target)
            rows[addr]={
                "cpu_address":addr,"file_offset":off,
                "instruction_word_hex":format(word,"08x"),
                "mnemonic_family":mnemonic,
                "branch_target":target,
                "raw_encoding_recoverable":True,
                "precise_operands_or_register_values_recovered":False,
            }
            if stop:
                break
            addr+=4
    return {
        "architecture":"arm7tdmi_arm_state_only",
        "cpu_base":BASE,
        "header_checksum_verified":True,
        "entry_cpu_address":BASE,
        "instructions":[rows[key] for key in sorted(rows)],
        "control_flow_edges":[
            {"from":a,"to":b,"kind":k} for a,b,k in sorted(edges)
        ],
        "instructions_emitted":len(rows),
        "instruction_limit":limit,
        "truncated":bool(queue) or len(rows)>=limit,
        "thumb_state_disassembled":False,
        "interrupt_and_bios_code_disassembled":False,
        "mode_changes_followed":False,
        "full_game_source_recovered":False,
    }
