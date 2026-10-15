"""Passive file/section reconnaissance across console, PC and disc formats.

No native executables, resource scripts, archives, game engines or unpackers
are ever run. A section inventory is not a game decompiler. Unknown formats
remain unknown with exact source hashes, not guessed copyrighted assets.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any

MAX_SECTION_COUNT = 96
MAX_ISO_RECORDS = 128


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ascii(value: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else "_" for b in value).strip(" _")[:64]


def inspect_pe(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"MZ") or len(data) < 0x40:
        raise ValueError("Not a complete PE DOS stub")
    offset = int.from_bytes(data[0x3C:0x40], "little")
    if not 0x40 <= offset <= min(len(data) - 24, 2 * 1024 * 1024):
        raise ValueError("PE signature lies outside bounded source")
    if data[offset:offset + 4] != b"PE\0\0":
        raise ValueError("PE/COFF signature absent")
    machine, sections = struct.unpack_from("<HH", data, offset + 4)
    optional = struct.unpack_from("<H", data, offset + 20)[0]
    if sections > MAX_SECTION_COUNT or offset + 24 + optional + sections * 40 > len(data):
        raise ValueError("PE section table truncated or exceeds capacity")
    entries = []
    start = offset + 24 + optional
    for i in range(sections):
        h = start + 40 * i
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", data, h + 8)
        flags = struct.unpack_from("<I", data, h + 36)[0]
        if raw_size and (raw_offset < 0 or raw_offset + raw_size > len(data)):
            raise ValueError("PE raw section range points beyond file")
        region = data[raw_offset:raw_offset + raw_size] if raw_size else b""
        entries.append({
            "name": _ascii(data[h:h + 8]), "virtual_address": rva,
            "virtual_size": virtual_size, "raw_offset": raw_offset,
            "raw_size": raw_size, "raw_sha256": _sha(region),
            "flags": flags, "marked_executable": bool(flags & 0x20000000),
        })
    return {
        "format": "pe_coff", "machine": machine, "sections": entries,
        "native_code_executed": False, "code_instructions_disassembled": False,
        "decompiler_proof": "section_metadata_only",
    }


def inspect_elf(data: bytes) -> dict[str, Any]:
    if len(data) < 64 or not data.startswith(b"\x7fELF"):
        raise ValueError("Invalid or truncated ELF header")
    elf_class = data[4]
    endian_marker = data[5]
    if elf_class not in (1, 2) or endian_marker not in (1, 2):
        raise ValueError("Unsupported ELF class/byte order")
    endian = "<" if endian_marker == 1 else ">"
    if elf_class == 1:
        section_off = struct.unpack_from(endian + "I", data, 32)[0]
        entry_size, count = struct.unpack_from(endian + "HH", data, 46)
        min_entry, field = 40, endian + "IIIIIIIIII"
    else:
        section_off = struct.unpack_from(endian + "Q", data, 40)[0]
        entry_size, count = struct.unpack_from(endian + "HH", data, 58)
        min_entry, field = 64, endian + "IIQQQQIIQQ"
    if count > MAX_SECTION_COUNT or (count and (
        entry_size < min_entry or section_off + entry_size * count > len(data))):
        raise ValueError("ELF section table is truncated or oversized")
    sections = []
    for i in range(count):
        row = struct.unpack_from(field, data, section_off + i * entry_size)
        section_type, flags, file_offset, size = row[1], row[2], row[4], row[5]
        if section_type == 8:  # SHT_NOBITS virtual allocation, not in source file
            source_sha, file_size = None, 0
        else:
            if file_offset + size > len(data):
                raise ValueError("ELF section points beyond actual file")
            source_sha, file_size = _sha(data[file_offset:file_offset + size]), size
        sections.append({
            "section_index": i, "section_type": section_type,
            "flags": flags, "file_offset": file_offset,
            "source_bytes": file_size, "sha256": source_sha,
            "executable_flag": bool(flags & 4),
        })
    return {
        "format": "elf", "class_bits": 32 if elf_class == 1 else 64,
        "byte_order": "little" if endian == "<" else "big",
        "sections": sections, "native_code_executed": False,
        "code_instructions_disassembled": False,
        "decompiler_proof": "section_metadata_only",
    }


def inspect_iso9660(data: bytes) -> dict[str, Any]:
    """Observe root directory entries from a complete bounded ISO image."""
    pvd = 16 * 2048
    if len(data) < pvd + 2048 or data[pvd + 1:pvd + 6] != b"CD001" or data[pvd] != 1:
        raise ValueError("ISO9660 primary volume descriptor absent")
    block_size = int.from_bytes(data[pvd + 128:pvd + 130], "little")
    if block_size != 2048:
        raise ValueError("Unsupported ISO logical sector size")
    root = data[pvd + 156:pvd + 190]
    if len(root) < 34 or root[0] < 34:
        raise ValueError("ISO root record invalid")
    sector = int.from_bytes(root[2:6], "little")
    size = int.from_bytes(root[10:14], "little")
    if not 0 < size <= 2 * 1024 * 1024 or sector * block_size + size > len(data):
        raise ValueError("ISO root directory exceeds supplied complete image")
    entries, offset = [], 0
    folder = data[sector * block_size:sector * block_size + size]
    while offset < len(folder):
        record_size = folder[offset]
        if not record_size:
            offset = ((offset // block_size) + 1) * block_size
            continue
        if record_size < 34 or offset + record_size > len(folder):
            raise ValueError("ISO directory record crosses the known region")
        record = folder[offset:offset + record_size]
        name_size = record[32]
        if 33 + name_size > record_size:
            raise ValueError("ISO directory filename size invalid")
        name = record[33:33 + name_size]
        if name not in (b"\x00", b"\x01"):
            entry_sector = int.from_bytes(record[2:6], "little")
            entry_size = int.from_bytes(record[10:14], "little")
            if entry_sector * block_size + entry_size > len(data):
                raise ValueError("ISO file entry points outside bounded source")
            entries.append({
                "name": _ascii(name), "file_size": entry_size,
                "extent_lba": entry_sector, "is_directory": bool(record[25] & 2),
                "actual_bytes_not_exported": True,
            })
        if len(entries) > MAX_ISO_RECORDS:
            raise ValueError("ISO directory listing exceeds bounded parser capacity")
        offset += record_size
    return {
        "format": "iso9660", "volume_identifier": _ascii(data[pvd + 40:pvd + 72]),
        "root_entries": entries, "nested_directories_followed": False,
        "disc_executable_code_decompiled": False,
        "source_media_exported": False,
    }


def inspect_binary_structure(data: bytes, filename: str) -> dict[str, Any]:
    if type(data) is not bytes or type(filename) is not str:
        raise ValueError("Bounded binary bytes and original file name are required")
    if data.startswith(b"MZ"):
        return inspect_pe(data)
    if data.startswith(b"\x7fELF"):
        return inspect_elf(data)
    if len(data) > 17 * 2048 and data[16 * 2048 + 1:16 * 2048 + 6] == b"CD001":
        return inspect_iso9660(data)
    if data.startswith(b"PK\x03\x04"):
        return {"format": "zip_container", "archive_extraction_not_performed_here": True}
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"format": "png", "opaque_asset_source_sha256": _sha(data)}
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return {"format": "wav", "opaque_asset_source_sha256": _sha(data)}
    if len(data) >= 16 and data[:4] == b"\x10\x00\x00\x00":
        return {"format": "playstation_tim_candidate", "validated_decoder_not_run": True}
    if data.startswith(b"MComprHD"):
        return {"format": "chd", "compressed_disc_decoding_not_supported": True}
    return {
        "format": "unknown_binary", "source_sha256": _sha(data),
        "no_guessed_disassembly_or_asset_identity": True,
    }
