"""Bounded, static, control-flow-aware 6502/SM83 disassembly for authorized games.

A listing is not original source code, a complete decompilation, symbolic
execution, accurate game mechanics, or proof that every byte is code.
Only reachable instructions from hardware entry vectors are decoded. No
emulated instructions or untrusted binaries are ever executed here.
"""
from __future__ import annotations

from collections import deque
from typing import Any

MAX_INSTRUCTIONS = 4096
MAX_BRANCHES = 8192

# Official NMOS 6502 opcodes. Unsupported/undocumented bytes become .db.
# Each tuple is mnemonic, addressing mode. End-user patching/assembler is
# deliberately not supported by the static analysis interface.
_6502_ROWS = (
    "00 BRK imp;01 ORA ix;05 ORA zp;06 ASL zp;08 PHP imp;09 ORA imm;0A ASL acc;0D ORA abs;0E ASL ax",
    "10 BPL rel;11 ORA iy;15 ORA zx;16 ASL zx;18 CLC imp;19 ORA ay;1D ORA ax;1E ASL ax",
    "20 JSR abs;21 AND ix;24 BIT zp;25 AND zp;26 ROL zp;28 PLP imp;29 AND imm;2A ROL acc;2C BIT abs;2D AND ax;2E ROL ax",
    "30 BMI rel;31 AND iy;35 AND zx;36 ROL zx;38 SEC imp;39 AND ay;3D AND ax;3E ROL ax",
    "40 RTI imp;41 EOR ix;45 EOR zp;46 LSR zp;48 PHA imp;49 EOR imm;4A LSR acc;4C JMP abs;4D EOR abs;4E LSR ax",
    "50 BVC rel;51 EOR iy;55 EOR zx;56 LSR zx;58 CLI imp;59 EOR ay;5D EOR ax;5E LSR ax",
    "60 RTS imp;61 ADC ix;65 ADC zp;66 ROR zp;68 PLA imp;69 ADC imm;6A ROR acc;6C JMP ind;6D ADC abs;6E ROR ax",
    "70 BVS rel;71 ADC iy;75 ADC zx;76 ROR zx;78 SEI imp;79 ADC ay;7D ADC ax;7E ROR ax",
    "81 STA ix;84 STY zp;85 STA zp;86 STX zp;88 DEY imp;8A TXA imp;8C STY abs;8D STA abs;8E STX abs",
    "90 BCC rel;91 STA iy;94 STY zx;95 STA zx;96 STX zy;98 TYA imp;99 STA ay;9A TXS imp;9D STA ax",
    "A0 LDY imm;A1 LDA ix;A2 LDX imm;A4 LDY zp;A5 LDA zp;A6 LDX zp;A8 TAY imp;A9 LDA imm;AA TAX imp;AC LDY abs;AD LDA abs;AE LDX abs",
    "B0 BCS rel;B1 LDA iy;B4 LDY zx;B5 LDA zx;B6 LDX zy;B8 CLV imp;B9 LDA ay;BA TSX imp;BC LDY ax;BD LDA ax;BE LDX ay",
    "C0 CPY imm;C1 CMP ix;C4 CPY zp;C5 CMP zp;C6 DEC zp;C8 INY imp;C9 CMP imm;CA DEX imp;CC CPY abs;CD CMP abs;CE DEC abs",
    "D0 BNE rel;D1 CMP iy;D5 CMP zx;D6 DEC zx;D8 CLD imp;D9 CMP ay;DD CMP ax;DE DEC ax",
    "E0 CPX imm;E1 SBC ix;E4 CPX zp;E5 SBC zp;E6 INC zp;E8 INX imp;E9 SBC imm;EA NOP imp;EC CPX abs;ED SBC abs;EE INC abs",
    "F0 BEQ rel;F1 SBC iy;F5 SBC zx;F6 INC zx;F8 SED imp;F9 SBC ay;FD SBC ax;FE INC ax",
)
_6502: dict[int, tuple[str, str]] = {}
for line in _6502_ROWS:
    for pair in line.split(";"):
        code, mnemonic, mode = pair.strip().split()
        _6502[int(code, 16)] = (mnemonic, mode)
_6502_SIZE = {"imp": 1, "acc": 1, "ix": 2, "iy": 2, "zp": 2, "zx": 2,
              "zy": 2, "imm": 2, "rel": 2, "abs": 3, "ax": 3, "ay": 3, "ind": 3}
_6502_STOP = {"BRK", "RTI", "RTS"}
_6502_BRANCH = {"BPL", "BMI", "BVC", "BVS", "BCC", "BCS", "BNE", "BEQ"}


def _hex(value: int, digits: int = 4) -> str:
    return "$" + format(value, "0" + str(digits) + "X")


def _signed(value: int) -> int:
    return value - 256 if value >= 128 else value


def disassemble_nes_nrom(rom: bytes, *, limit: int = MAX_INSTRUCTIONS) -> dict[str, Any]:
    """Decode CPU-reachable code only for mapper-0 NROM, never guess other banks."""
    if (type(rom) is not bytes or len(rom) < 16 or rom[:4] != b"NES\x1a"
        or type(limit) is not int or not 1 <= limit <= MAX_INSTRUCTIONS):
        raise ValueError("Valid bounded iNES binary and instruction limit required")
    nes2 = (rom[7] & 12) == 8
    mapper = (rom[6] >> 4) | (rom[7] & 240) | (((rom[8] & 15) << 8) if nes2 else 0)
    trainer = 512 if rom[6] & 4 else 0
    prg = rom[4] * 16384
    if nes2 or mapper != 0 or prg not in (16384, 32768):
        raise ValueError("Only unambiguous mapper-0 iNES PRG 16/32 KiB code mapping supported")
    offset = 16 + trainer
    if offset + prg > len(rom):
        raise ValueError("Declared NROM code bytes are truncated")
    payload = rom[offset:offset + prg]

    def file_index(address: int) -> int | None:
        if not 0x8000 <= address <= 0xFFFF:
            return None
        return (address - 0x8000) % prg

    def word(address: int) -> int:
        idx = file_index(address)
        if idx is None or idx + 1 >= len(payload):
            raise ValueError("NROM vector outside mapped PRG")
        return payload[idx] | (payload[idx + 1] << 8)

    vectors = {"nmi": word(0xFFFA), "reset": word(0xFFFC), "irq": word(0xFFFE)}
    entries = sorted(set(addr for addr in vectors.values() if file_index(addr) is not None))
    queue = deque(entries)
    visited: set[int] = set()
    rows: dict[int, dict[str, Any]] = {}
    branches: set[tuple[int, int, str]] = set()
    while queue and len(rows) < limit:
        pc = queue.popleft()
        while pc not in visited and len(rows) < limit:
            idx = file_index(pc)
            if idx is None:
                break
            visited.add(pc)
            opcode = payload[idx]
            mnemonic, mode = _6502.get(opcode, (".db", "imp"))
            size = _6502_SIZE[mode]
            if idx + size > len(payload) or pc + size > 0x10000:
                mnemonic, mode, size = ".db", "imp", 1
            raw = payload[idx:idx + size]
            value = raw[1] if size == 2 else (
                (raw[1] | (raw[2] << 8)) if size == 3 else None)
            target = None
            if mode == "rel":
                target = (pc + size + _signed(raw[1])) & 0xFFFF
            elif mode == "abs" and mnemonic in {"JSR", "JMP"}:
                target = value
            if target is not None and file_index(target) is not None and len(branches) < MAX_BRANCHES:
                branches.add((pc, target, "call" if mnemonic == "JSR" else "branch"))
                if target not in visited:
                    queue.append(target)
            if mode == "imp":
                operands = "" if mnemonic != ".db" else _hex(opcode, 2)
            elif mode == "acc":
                operands = "A"
            elif mode == "rel":
                operands = _hex(target if target is not None else 0)
            elif mode == "imm":
                operands = "#" + _hex(value, 2)
            elif mode == "zp":
                operands = _hex(value, 2)
            elif mode == "zx":
                operands = _hex(value, 2) + ",X"
            elif mode == "zy":
                operands = _hex(value, 2) + ",Y"
            elif mode in ("ix", "iy"):
                operands = "(" + _hex(value, 2) + (",X)" if mode == "ix" else "),Y")
            elif mode == "ind":
                operands = "(" + _hex(value) + ")"
            else:
                operands = _hex(value) + (",X" if mode == "ax" else ",Y" if mode == "ay" else "")
            rows[pc] = {
                "cpu_address": pc, "file_offset": offset + idx,
                "instruction_bytes": raw.hex(), "mnemonic": mnemonic,
                "operands": operands, "size": size, "branch_target": target,
                "certainty": "valid_opcode_not_proven_to_be_code",
            }
            if mnemonic in _6502_STOP or (mnemonic == "JMP"):
                break
            pc += size
    return {
        "architecture": "mos6502_nrom", "mapping": "mapper_0_only",
        "vectors": vectors, "reachable_entry_addresses": entries,
        "instructions": [rows[key] for key in sorted(rows)],
        "control_flow_edges": [
            {"from": a, "to": b, "kind": kind} for a, b, kind in sorted(branches)
        ],
        "instructions_emitted": len(rows), "instruction_limit": limit,
        "truncated": bool(queue) or len(rows) >= limit,
        "unmapped_prg_bytes_not_decompiled": True,
        "complete_original_source_recovered": False,
        "unknown_data_not_interpreted_as_licensed_assets": True,
    }


# SM83 Game Boy instruction size table: 0xCB prefix is two bytes;
# STOP is encoded with a trailing padding byte.
_GB_3 = {
    0x01, 0x08, 0x11, 0x21, 0x31, 0xC2, 0xC3, 0xC4, 0xCA,
    0xCC, 0xCD, 0xD2, 0xD4, 0xDA, 0xDC, 0xEA, 0xFA,
}
_GB_2 = {
    0x06, 0x0E, 0x10, 0x16, 0x18, 0x1E, 0x20, 0x26, 0x28,
    0x2E, 0x30, 0x36, 0x38, 0x3E, 0xC6, 0xCB, 0xCE, 0xD6,
    0xDE, 0xE0, 0xE6, 0xE8, 0xEE, 0xF0, 0xF6, 0xF8, 0xFE,
}
_GB_ILLEGAL = {0xD3, 0xDB, 0xDD, 0xE3, 0xE4, 0xEB, 0xEC, 0xED, 0xF4, 0xFC, 0xFD}
_GB_RET = {0xC9, 0xD9}
_GB_COND_RET = {0xC0, 0xC8, 0xD0, 0xD8}
_GB_ABS_JP = {0xC2, 0xC3, 0xCA, 0xD2, 0xDA}
_GB_ABS_CALL = {0xC4, 0xCC, 0xCD, 0xD4, 0xDC}
_GB_REL = {0x18, 0x20, 0x28, 0x30, 0x38}
_GB_RST = {0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF}


def disassemble_gb_sm83(rom: bytes, *, limit: int = MAX_INSTRUCTIONS) -> dict[str, Any]:
    """Decode reachable ROM-bank-0 SM83 instructions, not mapper-switching code."""
    if (type(rom) is not bytes or len(rom) < 0x150
        or type(limit) is not int or not 1 <= limit <= MAX_INSTRUCTIONS):
        raise ValueError("Game Boy ROM and bounded instructions required")
    from .game_learning_ingestion import _rom_gb
    metadata = _rom_gb(rom)
    # Never conflate bank switched 0x4000-7FFF with a fixed CPU code address.
    queue = deque([0x100])
    visited: set[int] = set()
    rows: dict[int, dict[str, Any]] = {}
    edges: set[tuple[int, int, str]] = set()
    while queue and len(rows) < limit:
        pc = queue.popleft()
        while pc not in visited and len(rows) < limit:
            if not 0 <= pc < min(0x4000, len(rom)):
                break
            op = rom[pc]
            size = 3 if op in _GB_3 else 2 if op in _GB_2 else 1
            if pc + size > min(0x4000, len(rom)):
                break
            visited.add(pc)
            raw = rom[pc:pc + size]
            target = None
            kind = None
            if op in _GB_ABS_JP | _GB_ABS_CALL:
                target = raw[1] | (raw[2] << 8)
                kind = "call" if op in _GB_ABS_CALL else "jump"
            elif op in _GB_REL:
                target = (pc + size + _signed(raw[1])) & 0xFFFF
                kind = "relative_branch"
            elif op in _GB_RST:
                target = op & 0x38
                kind = "restart"
            if target is not None and 0 <= target < min(0x4000, len(rom)):
                edges.add((pc, target, kind))
                if target not in visited:
                    queue.append(target)
            mnemonic = (
                ".db_undocumented" if op in _GB_ILLEGAL else
                "STOP" if op == 0x10 else
                "HALT" if op == 0x76 else
                "RET" if op in _GB_RET else
                "RET_cc" if op in _GB_COND_RET else
                "JP" if op in _GB_ABS_JP else
                "CALL" if op in _GB_ABS_CALL else
                "JR" if op in _GB_REL else
                "RST" if op in _GB_RST else
                "PREFIX_CB" if op == 0xCB else
                "SM83_opcode_" + format(op, "02X")
            )
            rows[pc] = {
                "cpu_address": pc, "file_offset": pc,
                "instruction_bytes": raw.hex(), "opcode": op,
                "mnemonic": mnemonic, "size": size,
                "branch_target": target,
                "certainty": "opcode_length_only_for_unexpanded_mnemonic",
            }
            if op in _GB_RET or op in {0x10, 0x76, 0xC3, 0x18, 0xE9} or op in _GB_ILLEGAL:
                break
            pc += size
    return {
        "architecture": "sharp_sm83_fixed_bank", "cartridge_type": metadata["cartridge_type"],
        "entry_address": 0x100,
        "instructions": [rows[key] for key in sorted(rows)],
        "control_flow_edges": [
            {"from": a, "to": b, "kind": k} for a, b, k in sorted(edges)
        ],
        "instructions_emitted": len(rows), "instruction_limit": limit,
        "truncated": bool(queue) or len(rows) >= limit,
        "bank_switched_code_decompiled": False,
        "complete_original_source_recovered": False,
        "opcode_semantics_not_claimed_for_generic_names": True,
    }
