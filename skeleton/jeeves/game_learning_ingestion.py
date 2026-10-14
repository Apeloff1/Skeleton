"""Bounded, provider-neutral game source digestion for the existing Jeeves owner.

Cartridge headers describe layout, not game behavior or emulator compatibility.
Text/record classifications remain source claims or lexical cues. No uploaded code
is executed, no archive is extracted, and no network/provider call occurs here.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sqlite3
import stat
import struct
import unicodedata
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

SCHEMA_VERSION = "skeleton.game.source_bundle.v1"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 96
MAX_TEXT_FILE_BYTES = 128000
MAX_TEXT_TREE_BYTES = 1000000
MAX_DOCUMENTS = 64
MAX_DOCUMENT_CHARS = 32000
MAX_DOCUMENT_TOTAL_CHARS = 512000
MAX_TRACE_BYTES = 8 * 1024 * 1024
MAX_TRACE_TRANSITIONS = 10000
_GB_LOGO = bytes.fromhex(
    "ceed6666cc0d000b03730083000c000d0008111f8889000edccc6ee6ddddd999" "bbbb67636e0eecccdddc999fbbb9333e"
)
_ROM_EXTENSIONS = {
    ".nes",
    ".gb",
    ".gbc",
    ".sfc",
    ".smc",
    ".md",
    ".gen",
    ".smd",
    ".gba",
    ".z64",
    ".v64",
    ".n64",
}
_ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}
_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".godot",
    ".gd",
    ".tscn",
    ".tres",
    ".cs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".lua",
    ".py",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".xml",
    ".glsl",
    ".shader",
    ".csv",
}
_PLATFORM_ALIASES = {
    "famicom": "nes",
    "nintendo_entertainment_system": "nes",
    "super_nintendo": "snes",
    "super_famicom": "snes",
    "gameboy": "gb",
    "game_boy": "gb",
    "gameboy_color": "gbc",
    "game_boy_color": "gbc",
    "mega_drive": "genesis",
    "megadrive": "genesis",
    "sega_genesis": "genesis",
    "gameboy_advance": "gba",
    "game_boy_advance": "gba",
    "nintendo_64": "n64",
}
_HARDWARE = {
    "nes": (1983, "8-bit cartridge console"),
    "gb": (1989, "8-bit handheld"),
    "gbc": (1998, "8-bit color handheld"),
    "snes": (1990, "16-bit cartridge console"),
    "genesis": (1988, "16-bit cartridge console"),
    "gba": (2001, "32-bit handheld"),
    "n64": (1996, "64-bit cartridge console"),
}
_GENRE_TERMS = {
    "platformer": ("platformer", "platform game"),
    "role_playing": ("role-playing", "role playing", "rpg", "jrpg"),
    "puzzle": ("puzzle",),
    "racing": ("racing",),
    "fighting": ("fighting game", "fighter"),
    "strategy": ("strategy", "rts", "turn-based"),
    "shooter": ("shooter", "fps", "shoot-em-up"),
    "adventure": ("adventure",),
    "simulation": ("simulation", "simulator"),
    "sports": ("sports", "football", "basketball"),
}
_MECHANIC_TERMS = {
    "jumping": ("jump", "jumping", "platformer"),
    "gravity": ("gravity",),
    "collision": ("collision", "collider"),
    "inventory": ("inventory",),
    "crafting": ("crafting", "craft"),
    "turn_based_combat": ("turn-based combat", "turn based combat"),
    "ranged_combat": ("projectile", "shooting", "ranged combat"),
    "stealth": ("stealth",),
    "resource_management": ("resource management",),
    "procedural_generation": ("procedural generation", "procgen"),
    "checkpoint": ("checkpoint",),
    "dialogue": ("dialogue", "dialog"),
    "quest": ("quest",),
}


class GameIngestionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise GameIngestionError(code, message)


def _text(value: Any, name: str, *, limit: int = 2048, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not empty and not value.strip())
        or "\x00" in value
    ):
        _fail("invalid_field", f"{name} is invalid")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    _bounded_json(value)
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GameIngestionError("invalid_json", "Source contains unsupported JSON values") from exc


def _bounded_json(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 24 or nodes > 100000:
            _fail("json_limit", "Source JSON exceeds its bounded structure")
        if isinstance(item, dict):
            if len(item) > 10000 or any(not isinstance(key, str) or len(key) > 2048 for key in item):
                _fail("invalid_json", "Source JSON object keys are invalid")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, (list, tuple)):
            if len(item) > 10000:
                _fail("json_limit", "Source JSON array exceeds its limit")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is int and abs(item) > 2**64 - 1:
            _fail("invalid_json", "Source integer exceeds its bounded numeric domain")
        elif isinstance(item, float):
            if not math.isfinite(item):
                _fail("invalid_json", "Source contains non-finite numbers")
        elif item is not None and type(item) not in (str, int, bool):
            _fail("invalid_json", "Source contains unsupported values")


def _json(data: bytes) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                _fail("duplicate_json_key", "Source JSON contains duplicate keys")
            result[key] = value
        return result

    try:
        value = json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: _fail("invalid_json", "Source JSON contains non-finite numbers"),
        )
    except GameIngestionError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise GameIngestionError("invalid_json", "Source is not bounded valid UTF-8 JSON") from exc
    _bounded_json(value)
    return value


def _filename(value: str) -> str:
    value = unicodedata.normalize("NFC", _text(value, "filename", limit=200))
    if (
        "/" in value
        or "\\" in value
        or value in {".", ".."}
        or ":" in value
        or any(ord(char) < 32 for char in value)
    ):
        _fail("invalid_filename", "Uploaded source filename must be a basename")
    return value


def _platform(value: str | None) -> str | None:
    if value is None:
        return None
    value = _text(value, "console_id", limit=64).casefold().replace("-", "_").replace(" ", "_")
    return _PLATFORM_ALIASES.get(value, value)


@dataclass(frozen=True, slots=True)
class GameSourceProvenance:
    source_ref: str
    tenant_id: str
    owner_id: str
    rights_refs: tuple[str, ...]
    license_ref: str = "user-attested"
    rights_acknowledged: bool = False
    origin: str = "user_upload"
    record_digest: str | None = None

    def __post_init__(self) -> None:
        _text(self.source_ref, "source_ref")
        _text(self.tenant_id, "tenant_id", limit=512)
        _text(self.owner_id, "owner_id", limit=512)
        _text(self.license_ref, "license_ref")
        if type(self.rights_acknowledged) is not bool or not self.rights_acknowledged:
            _fail(
                "rights_required", "Explicit source analysis and learning rights acknowledgement is required"
            )
        if type(self.rights_refs) is not tuple or not 1 <= len(self.rights_refs) <= 64:
            _fail("rights_required", "Distinct scoped source rights references are required")
        for ref in self.rights_refs:
            _text(ref, "rights_ref")
        if len(set(self.rights_refs)) != len(self.rights_refs):
            _fail("rights_required", "Distinct scoped source rights references are required")
        if self.origin not in {"user_upload", "dragon_record", "local_record"}:
            _fail("invalid_origin", "Source origin is unsupported")
        if self.record_digest is not None and (
            not isinstance(self.record_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", self.record_digest)
        ):
            _fail("invalid_digest", "Record digest is invalid")
        if self.origin != "user_upload" and self.record_digest is None:
            _fail("record_binding_required", "Collected knowledge requires its exact record digest")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["rights_refs"] = list(self.rights_refs)
        result["rights_status"] = "attested_requires_current_backend_authority"
        return result


@dataclass(frozen=True, slots=True)
class GameSourceBundle:
    payload_json: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.payload_json, str)
            or len(self.payload_json.encode("utf-8")) > MAX_SOURCE_BYTES
        ):
            _fail("bundle_limit", "Normalized source bundle exceeds its limit")
        raw = _json(self.payload_json.encode("utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            _fail("invalid_bundle", "Normalized source bundle schema is invalid")
        actual = raw.get("bundle_digest")
        unsigned = {key: value for key, value in raw.items() if key != "bundle_digest"}
        if actual != _sha(_canonical(unsigned)) or self.payload_json.encode("utf-8") != _canonical(raw):
            _fail("invalid_bundle", "Normalized source bundle digest or canonical encoding is invalid")

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def source_digest(self) -> str:
        return self.to_dict()["source_digest"]

    @property
    def content_digest(self) -> str:
        return self.source_digest

    @property
    def bundle_digest(self) -> str:
        return self.to_dict()["bundle_digest"]

    @property
    def digest(self) -> str:
        return self.bundle_digest

    @property
    def metadata(self) -> dict[str, Any]:
        return self.to_dict()["metadata"]

    @property
    def features(self) -> dict[str, Any]:
        return self.to_dict()["features"]

    @property
    def trace(self) -> dict[str, Any] | None:
        return self.to_dict()["trace"]


class _Accumulator:
    def __init__(self, source_ref: str) -> None:
        self.source_ref = source_ref
        self.documents: list[dict[str, Any]] = []
        self.assets: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.platforms: set[str] = set()
        self.roms: list[dict[str, Any]] = []
        self.projects: list[dict[str, Any]] = []
        self.trace: dict[str, Any] | None = None
        self.characters = 0
        self.text_bytes = 0
        self.features: dict[str, Any] = {"genres": [], "mechanics": [], "era": {}, "project": {}}

    def warning(self, value: str) -> None:
        if value not in self.warnings and len(self.warnings) < 128:
            self.warnings.append(value)

    def document(self, text: str, *, ref: str, kind: str, byte_digest: str) -> None:
        if not text.strip():
            return
        if len(self.documents) >= MAX_DOCUMENTS:
            _fail("document_limit", "Source has too many indexable documents")
        if len(text) > MAX_DOCUMENT_CHARS:
            self.warning(
                "A source document was shortened for bounded analysis; its full byte digest is retained."
            )
            text = text[:MAX_DOCUMENT_CHARS]
        self.characters += len(text)
        if self.characters > MAX_DOCUMENT_TOTAL_CHARS:
            _fail("document_limit", "Source documents exceed the total analysis limit")
        doc = {
            "document_id": _sha((ref + "\x00" + byte_digest).encode()),
            "text": text,
            "source_ref": ref,
            "content_digest": byte_digest,
            "kind": kind,
            "document_digest": _sha(text.encode()),
        }
        self.documents.append(doc)
        self._lexical_features(text, ref)

    def _lexical_features(self, text: str, ref: str) -> None:
        folded = text.casefold()
        for target, terms in (("genres", _GENRE_TERMS), ("mechanics", _MECHANIC_TERMS)):
            for label, aliases in terms.items():
                if any(
                    item["value"] == label and item["evidence_ref"] == ref for item in self.features[target]
                ):
                    continue
                for alias in aliases:
                    match = re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", folded)
                    if match:
                        self.features[target].append(
                            {
                                "value": label,
                                "classification": "lexical_cue",
                                "evidence_ref": ref,
                                "matched_text": alias,
                                "character_span": [match.start(), match.end()],
                                "span_basis": "Unicode casefolded document",
                            }
                        )
                        break
        for target in ("genres", "mechanics"):
            self.features[target] = self.features[target][:128]

    def declared_features(self, record: Mapping[str, Any], ref: str) -> None:
        for field, target in (("genre", "genres"), ("genres", "genres"), ("mechanics", "mechanics")):
            values = record.get(field, ())
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, (list, tuple)) or len(values) > 64:
                _fail("invalid_features", f"Declared {field} metadata is invalid")
            for value in values:
                value = _text(value, field, limit=80)
                self.features[target].append(
                    {"value": value, "classification": "declared", "evidence_ref": ref, "source_field": field}
                )
        year = record.get("release_year")
        if year is not None:
            if type(year) is not int or not 1950 <= year <= 2100:
                _fail("invalid_features", "Declared game release year is invalid")
            self.features["era"]["release_year"] = {
                "value": year,
                "classification": "declared",
                "evidence_ref": ref,
            }
        for field in (
            "engine",
            "template",
            "perspective",
            "dimension",
            "map_dimensions",
            "style",
            "movement",
            "physics",
        ):
            if field in record:
                encoded = _canonical(record[field])
                if len(encoded) > 16384:
                    _fail("invalid_features", "Declared project feature exceeds its limit")
                self.features["project"][field] = {
                    "value": json.loads(encoded),
                    "classification": "declared",
                    "evidence_ref": ref,
                }

    def bounded_features(self) -> dict[str, Any]:
        for field in ("genres", "mechanics"):
            unique = {}
            for item in sorted(self.features[field], key=lambda row: row["classification"] != "declared"):
                unique.setdefault(
                    (item["value"].casefold(), item["evidence_ref"], item["classification"]), item
                )
            self.features[field] = list(unique.values())[:64]
        while len(_canonical(self.features)) > 16384:
            if self.features["mechanics"]:
                self.features["mechanics"].pop()
            elif self.features["genres"]:
                self.features["genres"].pop()
            elif self.features["project"]:
                self.features["project"].pop(next(reversed(self.features["project"])))
            elif self.features["era"]:
                self.features["era"].pop(next(reversed(self.features["era"])))
            else:
                _fail("feature_limit", "Source feature projection exceeds its limit")
            self.warning(
                "Feature cues were shortened for the bounded generation projection; complete source digests and documents remain separate evidence."
            )
        return self.features

    def rom(self, data: bytes, filename: str, ref: str) -> None:
        metadata = _parse_rom(data, filename)
        platform = metadata["console_id"]
        self.platforms.add(platform)
        metadata["source_ref"] = ref
        metadata["content_digest"] = _sha(data)
        self.roms.append(metadata)
        for warning in metadata.pop("warnings", []):
            self.warning(warning)
        for asset in metadata.get("layout", []):
            self.assets.append({**asset, "source_ref": ref, "classification": "observed_cartridge_layout"})
        year, generation = _HARDWARE[platform]
        self.features["era"].setdefault("hardware", [])
        self.features["era"]["hardware"].append(
            {
                "platform": platform,
                "introduction_year": year,
                "generation": generation,
                "classification": "platform_reference",
                "evidence_ref": ref,
            }
        )
        self.document(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False),
            ref=ref,
            kind="rom_header_observations",
            byte_digest=_sha(data),
        )
        self.warning(
            "Cartridge layout does not establish game genre, mechanics, asset semantics, bootability or emulator support."
        )


def _ascii(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def _layout(data: bytes, offset: int, size: int, kind: str, **extra: Any) -> dict[str, Any]:
    if size < 0 or offset < 0 or offset + size > len(data):
        _fail("truncated_rom", "Declared cartridge region exceeds the provided bytes")
    return {
        "kind": kind,
        "offset": offset,
        "byte_length": size,
        "content_digest": _sha(data[offset : offset + size]),
        **extra,
    }


def _nes_size(low: int, high: int, unit: int) -> int:
    if high != 15:
        return ((high << 8) | low) * unit
    exponent = low >> 2
    if exponent > 24:
        _fail("source_limit", "NES 2.0 declared cartridge size exceeds the bounded source limit")
    return (1 << exponent) * (2 * (low & 3) + 1)


def _rom_nes(data: bytes) -> dict[str, Any]:
    if len(data) < 16 or data[:4] != b"NES\x1a":
        _fail("invalid_rom", "iNES signature or header is missing")
    second = data[7] & 12 == 8
    if data[7] & 12 not in {0, 8}:
        _fail("unsupported_rom", "Unsupported NES header variant")
    prg = _nes_size(data[4], data[9] & 15, 16384) if second else data[4] * 16384
    chr_size = _nes_size(data[5], data[9] >> 4, 8192) if second else data[5] * 8192
    trainer = 512 if data[6] & 4 else 0
    mapper = (data[6] >> 4) | (data[7] & 240) | ((data[8] & 15) << 8 if second else 0)
    if not prg or prg + chr_size + trainer + 16 > len(data):
        _fail("truncated_rom", "NES declared PRG/CHR regions are missing or truncated")
    layout = [_layout(data, 16 + trainer, prg, "program_rom", bank_bytes=16384)]
    if trainer:
        layout.append(_layout(data, 16, trainer, "trainer"))
    if chr_size:
        layout.append(
            _layout(
                data,
                16 + trainer + prg,
                chr_size,
                "character_rom",
                tile_bytes=16,
                tile_count=chr_size // 16,
                encoding="NES planar 2bpp",
            )
        )
    ram = lambda shift: 0 if shift == 0 else 64 << shift
    result = {
        "console_id": "nes",
        "format": "nes2" if second else "ines",
        "header_offset": 0,
        "mapper_id": mapper,
        "submapper_id": data[8] >> 4 if second else None,
        "prg_rom_bytes": prg,
        "chr_rom_bytes": chr_size,
        "trainer_bytes": trainer,
        "mirroring": "four_screen" if data[6] & 8 else "vertical" if data[6] & 1 else "horizontal",
        "battery_flag": bool(data[6] & 2),
        "console_type": data[7] & 3,
        "layout": layout,
        "header_digest": _sha(data[:16]),
        "trailing_bytes": len(data) - 16 - trainer - prg - chr_size,
        "warnings": [],
    }
    if second:
        result.update(
            prg_ram_bytes=ram(data[10] & 15),
            prg_nvram_bytes=ram(data[10] >> 4),
            chr_ram_bytes=ram(data[11] & 15),
            chr_nvram_bytes=ram(data[11] >> 4),
            timing_mode=data[12] & 3,
        )
    else:
        result.update(prg_ram_declared_bytes=data[8] * 8192, tv_system="pal" if data[9] & 1 else "ntsc")
        if any(data[12:16]):
            result["warnings"].append(
                "Legacy iNES reserved bytes are nonzero; mapper metadata may reflect an old ambiguous dump header."
            )
    if result["trailing_bytes"]:
        result["warnings"].append(
            "Trailing cartridge bytes are retained by source digest but not assigned an asset meaning."
        )
    return result


def _rom_gb(data: bytes) -> dict[str, Any]:
    if len(data) < 0x150 or data[0x104:0x134] != _GB_LOGO:
        _fail("invalid_rom", "Game Boy cartridge logo or complete header is missing")
    code = data[0x148]
    declared = (
        (32768 << code) if code <= 8 else {0x52: 72 * 16384, 0x53: 80 * 16384, 0x54: 96 * 16384}.get(code)
    )
    if declared is None:
        _fail("unsupported_rom", "Game Boy ROM size code is unsupported")
    if len(data) < declared:
        _fail("truncated_rom", "Game Boy declared ROM banks are truncated")
    cgb = data[0x143] in {0x80, 0xC0}
    cartridge = data[0x147]
    mapper = (
        "ROM_ONLY"
        if cartridge in {0, 8, 9}
        else (
            "MBC1"
            if cartridge in {1, 2, 3}
            else (
                "MBC2"
                if cartridge in {5, 6}
                else (
                    "MBC3"
                    if cartridge in {15, 16, 17, 18, 19}
                    else (
                        "MBC5"
                        if 25 <= cartridge <= 30
                        else "MBC6" if cartridge == 32 else "MBC7" if cartridge == 34 else "unknown"
                    )
                )
            )
        )
    )
    checksum = 0
    for byte in data[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    global_actual = (sum(data) - data[0x14E] - data[0x14F]) & 65535
    result = {
        "console_id": "gbc" if cgb else "gb",
        "format": "game_boy_cartridge",
        "header_offset": 0x100,
        "title": _ascii(data[0x134:0x143] if cgb else data[0x134:0x144]),
        "manufacturer_code_candidate": _ascii(data[0x13F:0x143]) if cgb else None,
        "cartridge_type": cartridge,
        "mapper": mapper,
        "cgb_flag": data[0x143],
        "sgb_supported": data[0x146] == 3,
        "rom_size_code": code,
        "rom_declared_bytes": declared,
        "ram_size_code": data[0x149],
        "ram_declared_bytes": {0: 0, 1: 2048, 2: 8192, 3: 32768, 4: 131072, 5: 65536}.get(data[0x149]),
        "region_code": data[0x14A],
        "rom_version": data[0x14C],
        "header_checksum_stored": data[0x14D],
        "header_checksum_computed": checksum,
        "header_checksum_valid": checksum == data[0x14D],
        "global_checksum_stored": int.from_bytes(data[0x14E:0x150], "big"),
        "global_checksum_computed": global_actual,
        "global_checksum_valid": global_actual == int.from_bytes(data[0x14E:0x150], "big"),
        "header_digest": _sha(data[0x100:0x150]),
        "layout": [_layout(data, 0, declared, "cartridge_rom", bank_bytes=16384)],
        "warnings": [],
    }
    if not result["header_checksum_valid"] or not result["global_checksum_valid"]:
        result["warnings"].append(
            "Game Boy checksum mismatch is observed; the source may be modified or incomplete and bootability is not established."
        )
    if mapper == "unknown":
        result["warnings"].append(
            "Cartridge type is preserved, but its mapper is not implemented by this ingestion parser."
        )
    return result


def _rom_snes(data: bytes) -> dict[str, Any]:
    prefix = 512 if len(data) % 1024 == 512 else 0
    image = data[prefix:]
    candidates = []
    for base, mapping in ((0x7FC0, "lorom"), (0xFFC0, "hirom"), (0x40FFC0, "exhirom")):
        if base + 64 > len(image):
            continue
        header = image[base : base + 64]
        title = header[:21]
        checksum = int.from_bytes(header[30:32], "little")
        complement = int.from_bytes(header[28:30], "little")
        mode = header[21]
        printable = sum(32 <= byte < 127 for byte in title)
        reset = int.from_bytes(header[60:62], "little")
        expected = mode & 15 in ({0, 2, 3} if mapping == "lorom" else {1} if mapping == "hirom" else {5})
        if (
            printable < 16
            or reset < 0x8000
            or mode not in {0x20, 0x21, 0x22, 0x23, 0x25, 0x30, 0x31, 0x32, 0x35}
        ):
            continue
        score = (
            2
            + (4 if checksum ^ complement == 65535 and checksum not in {0, 65535} else 0)
            + (3 if expected else 0)
        )
        candidates.append((score, base, mapping, header))
    if not candidates:
        _fail("invalid_rom", "No sufficiently structured SNES cartridge header was found")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    score, base, mapping, header = candidates[0]
    if score < 6 or (len(candidates) > 1 and candidates[1][0] == score):
        _fail("ambiguous_rom", "SNES cartridge header mapping is ambiguous or insufficiently supported")
    size_code = header[23]
    capacity = 1024 << size_code if size_code <= 15 else None
    result = {
        "console_id": "snes",
        "format": "snes_cartridge",
        "header_offset": prefix + base,
        "copier_header_bytes": prefix,
        "mapping_candidate": mapping,
        "mapping_mode": header[21],
        "title": _ascii(header[:21]),
        "cartridge_type": header[22],
        "rom_size_code": size_code,
        "rom_declared_capacity_bytes": capacity,
        "ram_declared_capacity_bytes": (
            0 if header[24] == 0 else 1024 << header[24] if header[24] <= 15 else None
        ),
        "region_code": header[25],
        "developer_code": header[26],
        "rom_version": header[27],
        "checksum_stored": int.from_bytes(header[30:32], "little"),
        "checksum_complement_stored": int.from_bytes(header[28:30], "little"),
        "checksum_pair_valid": int.from_bytes(header[30:32], "little")
        ^ int.from_bytes(header[28:30], "little")
        == 65535,
        "reset_vector": int.from_bytes(header[60:62], "little"),
        "header_digest": _sha(header),
        "layout": [_layout(data, prefix, len(image), "cartridge_rom")],
        "warnings": [
            "SNES header selection uses structural cues; mapped CPU execution and the complete cartridge checksum algorithm are not implemented."
        ],
    }
    if capacity != len(image):
        result["warnings"].append(
            "SNES declared power-of-two cartridge capacity differs from supplied image length; this is not proof of truncation."
        )
    return result


def _rom_genesis(data: bytes, filename: str) -> dict[str, Any]:
    image = data
    interleaved = PurePosixPath(filename).suffix.casefold() == ".smd"
    if interleaved:
        if len(data) <= 512 or (len(data) - 512) % 16384:
            _fail("invalid_rom", "SMD dump must contain a 512-byte header and complete interleaved banks")
        output = bytearray(len(data) - 512)
        for offset in range(512, len(data), 16384):
            block = data[offset : offset + 16384]
            start = offset - 512
            output[start : start + 16384 : 2] = block[8192:]
            output[start + 1 : start + 16384 : 2] = block[:8192]
        image = bytes(output)
    if len(image) < 512 or not image[0x100:0x110].startswith(b"SEGA"):
        _fail("invalid_rom", "Genesis cartridge system signature or complete header is missing")
    checksum = sum((image[index] << 8) | image[index + 1] for index in range(512, len(image) - 1, 2)) & 65535
    stored = int.from_bytes(image[0x18E:0x190], "big")
    return {
        "console_id": "genesis",
        "format": "sega_smd" if interleaved else "sega_cartridge",
        "header_offset": 0x100,
        "system": _ascii(image[0x100:0x110]),
        "copyright_header": _ascii(image[0x110:0x120]),
        "domestic_title": _ascii(image[0x120:0x150]),
        "international_title": _ascii(image[0x150:0x180]),
        "product_code": _ascii(image[0x180:0x18E]),
        "device_support": _ascii(image[0x190:0x1A0]),
        "rom_address_start": int.from_bytes(image[0x1A0:0x1A4], "big"),
        "rom_address_end": int.from_bytes(image[0x1A4:0x1A8], "big"),
        "ram_address_start": int.from_bytes(image[0x1A8:0x1AC], "big"),
        "ram_address_end": int.from_bytes(image[0x1AC:0x1B0], "big"),
        "sram_signature": _ascii(image[0x1B0:0x1B2]),
        "region_header": _ascii(image[0x1F0:0x200]),
        "checksum_stored": stored,
        "checksum_computed": checksum,
        "checksum_valid": stored == checksum,
        "normalized_rom_digest": _sha(image),
        "header_digest": _sha(image[0x100:0x200]),
        "layout": [] if interleaved else [_layout(data, 0, len(data), "cartridge_rom")],
        "warnings": (
            [
                "SMD byte order was normalized for header inspection; source digest remains the exact original upload."
            ]
            if interleaved
            else []
        )
        + (
            []
            if stored == checksum
            else ["Genesis word checksum mismatch is observed; execution compatibility is not established."]
        ),
    }


def _rom_gba(data: bytes) -> dict[str, Any]:
    if len(data) < 192 or data[0xB2] != 0x96:
        _fail("invalid_rom", "GBA fixed header byte or complete header is missing")
    code = data[0xAC:0xB0]
    if not all(32 <= byte < 127 for byte in code):
        _fail("invalid_rom", "GBA game code is not structurally valid ASCII")
    checksum = (-sum(data[0xA0:0xBD]) - 0x19) & 255
    return {
        "console_id": "gba",
        "format": "gba_structural_header",
        "header_offset": 0,
        "title": _ascii(data[0xA0:0xAC]),
        "game_code": _ascii(code),
        "maker_code": _ascii(data[0xB0:0xB2]),
        "unit_code": data[0xB3],
        "device_type": data[0xB4],
        "software_version": data[0xBC],
        "header_checksum_stored": data[0xBD],
        "header_checksum_computed": checksum,
        "header_checksum_valid": checksum == data[0xBD],
        "logo_digest": _sha(data[4:0xA0]),
        "header_digest": _sha(data[:192]),
        "layout": [_layout(data, 0, len(data), "cartridge_rom")],
        "warnings": [
            "GBA identification is structural; Nintendo logo/boot validation, save-chip detection and code execution are not implemented."
        ],
    }


def _rom_n64(data: bytes) -> dict[str, Any]:
    if len(data) < 64:
        _fail("invalid_rom", "N64 cartridge header is truncated")
    header = data[:64]
    if header[:4] == bytes.fromhex("80371240"):
        order = "big_endian"
    elif header[:4] == bytes.fromhex("37804012"):
        header = bytes(header[index ^ 1] for index in range(64))
        order = "byte_swapped"
    elif header[:4] == bytes.fromhex("40123780"):
        header = bytes(header[(index // 4) * 4 + 3 - index % 4] for index in range(64))
        order = "little_endian_words"
    else:
        _fail("invalid_rom", "N64 byte-order signature is missing")
    return {
        "console_id": "n64",
        "format": "n64_cartridge",
        "byte_order": order,
        "title": _ascii(header[0x20:0x34]),
        "clock_rate": int.from_bytes(header[4:8], "big"),
        "entry_point": int.from_bytes(header[8:12], "big"),
        "sdk_release": int.from_bytes(header[12:16], "big"),
        "crc1_stored": int.from_bytes(header[16:20], "big"),
        "crc2_stored": int.from_bytes(header[20:24], "big"),
        "cartridge_id": _ascii(header[0x3C:0x3E]),
        "country_code": header[0x3E],
        "version": header[0x3F],
        "normalized_header_digest": _sha(header),
        "header_offset": 0,
        "layout": [_layout(data, 0, len(data), "cartridge_rom")],
        "warnings": ["N64 CIC-specific CRC verification and console execution are not implemented."],
    }


def _parse_rom(data: bytes, filename: str) -> dict[str, Any]:
    extension = PurePosixPath(filename).suffix.casefold()
    if data.startswith(b"NES\x1a"):
        return _rom_nes(data)
    if len(data) >= 0x150 and data[0x104:0x134] == _GB_LOGO:
        return _rom_gb(data)
    if data[:4] in {bytes.fromhex("80371240"), bytes.fromhex("37804012"), bytes.fromhex("40123780")}:
        return _rom_n64(data)
    if len(data) >= 512 and data[0x100:0x110].startswith(b"SEGA") or extension == ".smd":
        return _rom_genesis(data, filename)
    if extension in {".sfc", ".smc"}:
        return _rom_snes(data)
    if extension == ".gba":
        return _rom_gba(data)
    _fail(
        "unsupported_rom",
        "No supported cartridge format was identified from actual bytes and declared format",
    )


def _has_rom_signature(data: bytes) -> bool:
    return (
        data.startswith(b"NES\x1a")
        or len(data) >= 0x150
        and data[0x104:0x134] == _GB_LOGO
        or data[:4] in {bytes.fromhex("80371240"), bytes.fromhex("37804012"), bytes.fromhex("40123780")}
        or len(data) >= 512
        and data[0x100:0x110].startswith(b"SEGA")
    )


def _finite(value: Any, name: str, *, maximum: float = 1e9) -> float:
    if (
        type(value) not in (int, float)
        or abs(value) > maximum
        or (type(value) is float and not math.isfinite(value))
    ):
        _fail("invalid_trace", f"{name} must be a bounded finite number")
    return float(value)


def _validate_trace(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema_version") != "skeleton.game.trace.v1":
        _fail("invalid_trace", "Offline trace schema is unsupported")
    required = {
        "schema_version",
        "environment",
        "episode_id",
        "seed",
        "source_lineage",
        "transitions",
        "return",
        "steps",
        "trace_digest",
    }
    if set(raw) != required:
        _fail("invalid_trace", "Offline trace must contain the exact bounded episode schema")
    _text(raw["episode_id"], "episode_id", limit=256)
    if any(ord(char) < 32 for char in raw["episode_id"]):
        _fail("invalid_trace", "Trace episode identity contains control characters")
    if type(raw["seed"]) is not int or not 0 <= raw["seed"] <= 2**63 - 1:
        _fail("invalid_trace", "Offline episode seed is invalid")
    environment = raw["environment"]
    if not isinstance(environment, dict):
        _fail("invalid_trace", "Trace environment descriptor is missing")
    environment_fields = {
        "environment_id",
        "environment_digest",
        "actions",
        "observation_bins",
        "reward_components",
        "max_episode_steps",
    }
    if set(environment) != environment_fields:
        _fail("invalid_trace", "Trace environment descriptor must match its exact supported schema")
    _text(environment["environment_id"], "environment_id", limit=256)
    if any(ord(char) < 32 for char in environment["environment_id"]):
        _fail("invalid_trace", "Trace environment identity contains control characters")
    if not isinstance(environment["environment_digest"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", environment["environment_digest"]
    ):
        _fail("invalid_trace", "Trace environment digest is invalid")
    actions = environment["actions"]
    components = environment["reward_components"]
    bins = environment["observation_bins"]
    if (
        not isinstance(actions, list)
        or not 1 <= len(actions) <= 32
        or any(
            not isinstance(item, str) or not item or len(item) > 64 or any(ord(char) < 32 for char in item)
            for item in actions
        )
        or len(set(actions)) != len(actions)
    ):
        _fail("invalid_trace", "Trace action domain is invalid")
    if not isinstance(components, list) or not all(isinstance(item, str) for item in components):
        _fail("invalid_trace", "Trace reward component domain is invalid")
    component_names = set(components)
    if (
        not 1 <= len(component_names) <= 16
        or len(component_names) != len(components)
        or any(not item or len(item) > 64 or any(ord(char) < 32 for char in item) for item in component_names)
    ):
        _fail("invalid_trace", "Trace reward component names are invalid")
    if not isinstance(bins, dict) or not 1 <= len(bins) <= 32:
        _fail("invalid_trace", "Trace observation feature domain is invalid")
    for name, thresholds in bins.items():
        _text(name, "observation feature", limit=64)
        if any(ord(char) < 32 for char in name):
            _fail("invalid_trace", "Trace observation feature contains control characters")
        if not isinstance(thresholds, list) or not 1 <= len(thresholds) <= 64:
            _fail("invalid_trace", "Trace observation thresholds exceed their bounded domain")
        clean = [_finite(value, "observation threshold") for value in thresholds]
        if any(right <= left for left, right in pairwise(clean)):
            _fail("invalid_trace", "Trace observation thresholds must strictly increase")
    max_steps = environment["max_episode_steps"]
    if type(max_steps) is not int or not 1 <= max_steps <= 4096:
        _fail("invalid_trace", "Trace episode horizon exceeds its bound")
    transitions = raw["transitions"]
    if not isinstance(transitions, list) or not 1 <= len(transitions) <= min(
        MAX_TRACE_TRANSITIONS, max_steps
    ):
        _fail("invalid_trace", "Trace transition count is invalid")
    if type(raw["steps"]) is not int or raw["steps"] != len(transitions):
        _fail("invalid_trace", "Trace declared step count differs from its transitions")
    if not isinstance(raw["source_lineage"], dict) or len(_canonical(raw["source_lineage"])) > 16384:
        _fail("invalid_trace", "Trace lineage is invalid or too large")
    previous = None
    rewards = []
    for index, row in enumerate(transitions):
        fields = {
            "sequence",
            "observation",
            "action",
            "next_observation",
            "reward",
            "reward_components",
            "terminated",
            "truncated",
        }
        if not isinstance(row, dict) or (
            not fields <= set(row) or not set(row) <= fields | {"info", "transition_digest"}
        ):
            _fail("invalid_trace", "Trace transition schema is invalid")
        if type(row["sequence"]) is not int or row["sequence"] != index + 1 or row["action"] not in actions:
            _fail("invalid_trace", "Trace transition sequence or action is invalid")
        for field in ("observation", "next_observation"):
            observation = row[field]
            if not isinstance(observation, dict) or set(observation) != set(bins):
                _fail("invalid_trace", "Trace observation differs from its exact feature domain")
            for name, value in observation.items():
                _finite(value, f"observation.{name}")
        if previous is not None and _canonical(previous) != _canonical(row["observation"]):
            _fail("invalid_trace", "Trace observations do not form a contiguous chain")
        previous = row["next_observation"]
        parts = row["reward_components"]
        if not isinstance(parts, dict) or set(parts) != component_names:
            _fail("invalid_trace", "Trace reward components differ from their declared domain")
        values = [_finite(value, "reward component") for value in parts.values()]
        reward = _finite(row["reward"], "reward")
        if reward != math.fsum(values):
            _fail("invalid_trace", "Trace reward does not equal its supplied components")
        rewards.append(reward)
        if type(row["terminated"]) is not bool or type(row["truncated"]) is not bool:
            _fail("invalid_trace", "Trace terminal flags are invalid")
        if row["terminated"] and row["truncated"]:
            _fail("invalid_trace", "Trace transition cannot both terminate and truncate")
        if (row["terminated"] or row["truncated"]) != (index == len(transitions) - 1):
            _fail("invalid_trace", "Only the final trace transition must terminate or truncate")
        if "transition_digest" in row and (
            not isinstance(row["transition_digest"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["transition_digest"])
        ):
            _fail("invalid_trace", "Trace transition digest is invalid")
        if "info" in row and (not isinstance(row["info"], dict) or len(_canonical(row["info"])) > 4096):
            _fail("invalid_trace", "Trace transition info must be a bounded object")
    if _finite(raw["return"], "episode return", maximum=1e15) != math.fsum(rewards):
        _fail("invalid_trace", "Trace return differs from its supplied rewards")
    unsigned = {key: value for key, value in raw.items() if key != "trace_digest"}
    if raw["trace_digest"] != _sha(_canonical(unsigned)):
        _fail("invalid_trace", "Trace digest does not bind its complete supplied episode")
    if len(_canonical(raw)) > MAX_TRACE_BYTES:
        _fail("trace_limit", "Offline trace exceeds its byte bound")
    return raw


def _asset(data: bytes, path: str, ref: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "source_ref": ref,
        "byte_length": len(data),
        "content_digest": _sha(data),
        "format": "opaque",
        "classification": "observed_file_metadata",
    }
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 33 or data[12:16] != b"IHDR" or int.from_bytes(data[8:12], "big") != 13:
            _fail("invalid_asset", "PNG image header is truncated or malformed")
        width, height = struct.unpack(">II", data[16:24])
        if not 1 <= width <= 16384 or not 1 <= height <= 16384 or width * height > 16 * 1024 * 1024:
            _fail("asset_limit", "Image dimensions exceed the bounded inventory scope")
        result.update(
            format="png",
            width=width,
            height=height,
            bit_depth=data[24],
            color_type=data[25],
            header_crc_valid=zlib.crc32(data[12:29]) & 0xFFFFFFFF == int.from_bytes(data[29:33], "big"),
        )
    elif data[:6] in {b"GIF87a", b"GIF89a"}:
        if len(data) < 13:
            _fail("invalid_asset", "GIF logical screen header is truncated")
        width, height = struct.unpack("<HH", data[6:10])
        if not width or not height or width * height > 16 * 1024 * 1024:
            _fail("asset_limit", "GIF dimensions exceed the bounded inventory scope")
        result.update(format="gif", width=width, height=height, global_color_table=bool(data[10] & 128))
    elif data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        if len(data) < 12 or int.from_bytes(data[4:8], "little") + 8 > len(data):
            _fail("invalid_asset", "WAVE container is truncated")
        offset = 12
        fmt = None
        audio_bytes = 0
        chunks = 0
        while offset + 8 <= len(data):
            chunks += 1
            if chunks > 256:
                _fail("asset_limit", "WAVE chunk count exceeds its bound")
            size = int.from_bytes(data[offset + 4 : offset + 8], "little")
            end = offset + 8 + size
            if end > len(data):
                _fail("invalid_asset", "WAVE chunk exceeds its actual file")
            if data[offset : offset + 4] == b"fmt " and size >= 16:
                fmt = struct.unpack("<HHIIHH", data[offset + 8 : offset + 24])
            if data[offset : offset + 4] == b"data":
                audio_bytes += size
            offset = end + (size & 1)
        if fmt:
            encoding, channels, rate, _, align, bits = fmt
            if not 1 <= channels <= 32 or not 1 <= rate <= 384000 or not align:
                _fail("invalid_asset", "WAVE sample format is invalid")
            result.update(
                format="wav",
                encoding=encoding,
                channels=channels,
                sample_rate=rate,
                bits_per_sample=bits,
                audio_data_bytes=audio_bytes,
                duration_seconds=audio_bytes / (rate * align) if encoding in {1, 3} else None,
            )
    return result


def _archive_path(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    if (
        not value
        or len(value) > 240
        or "\\" in value
        or "\x00" in value
        or ":" in value
        or value.startswith("/")
    ):
        _fail("unsafe_archive", "Archive contains an unsafe member path")
    parts = value.split("/")
    if any(part in {".", ".."} or not part for part in parts) or any(ord(char) < 32 for char in value):
        _fail("unsafe_archive", "Archive contains traversal or control characters")
    return "/".join(parts)


def _preflight_zip(data: bytes) -> None:
    offset = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if offset < 0 or offset + 22 > len(data):
        _fail("invalid_archive", "ZIP end-of-directory record is missing")
    disk, start_disk, local_count, count, size, directory, comment = struct.unpack(
        "<HHHHIIH", data[offset + 4 : offset + 22]
    )
    if disk or start_disk or local_count != count or not 1 <= count <= MAX_ARCHIVE_MEMBERS:
        _fail("archive_limit", "Split, ZIP64 or over-limit ZIP member directories are not admitted")
    if (
        offset + 22 + comment != len(data)
        or directory + size != offset
        or directory < 0
        or directory + size > len(data)
    ):
        _fail("invalid_archive", "ZIP central directory bounds are invalid")
    cursor = directory
    for _ in range(count):
        if cursor + 46 > offset or data[cursor : cursor + 4] != b"PK\x01\x02":
            _fail("invalid_archive", "ZIP central directory entry is malformed")
        name, extra, entry_comment = struct.unpack("<HHH", data[cursor + 28 : cursor + 34])
        if (
            not 1 <= name <= 960
            or extra > 4096
            or entry_comment > 4096
            or struct.unpack("<H", data[cursor + 34 : cursor + 36])[0]
        ):
            _fail("archive_limit", "ZIP directory metadata exceeds its bound")
        cursor += 46 + name + extra + entry_comment
        if cursor > offset:
            _fail("invalid_archive", "ZIP central directory entry exceeds actual bytes")
    if cursor != offset:
        _fail("invalid_archive", "ZIP actual member count differs from its bounded directory declaration")


class GameLearningIngestor:
    """Normalize exact supplied bytes. Current rights enforcement stays with caller authority."""

    def ingest_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        provenance: GameSourceProvenance,
        source_kind: str = "auto",
        console_id: str | None = None,
    ) -> GameSourceBundle:
        if type(data) is not bytes or not data or len(data) > MAX_SOURCE_BYTES:
            _fail("source_limit", "Source must contain 1 byte to 16 MiB of exact bytes")
        if not isinstance(provenance, GameSourceProvenance):
            _fail("rights_required", "Validated scoped source provenance is required")
        filename = _filename(filename)
        console = _platform(console_id)
        if source_kind not in {"auto", "rom", "text", "project", "trace", "archive"}:
            _fail("unsupported_source", "Source kind is unsupported")
        accumulator = _Accumulator(provenance.source_ref)
        extension = PurePosixPath(filename).suffix.casefold()
        kind = source_kind
        if kind == "auto":
            kind = (
                "archive"
                if extension == ".zip" or data.startswith(b"PK\x03\x04")
                else (
                    "rom"
                    if extension in _ROM_EXTENSIONS or _has_rom_signature(data)
                    else "project" if extension == ".json" else "text"
                )
            )
        if kind == "rom":
            accumulator.rom(data, filename, provenance.source_ref)
        elif kind == "archive":
            self._archive(data, accumulator)
        elif kind in {"project", "trace"}:
            raw = _json(data)
            if (
                kind == "trace"
                or isinstance(raw, dict)
                and raw.get("schema_version") == "skeleton.game.trace.v1"
            ):
                kind = "trace"
                accumulator.trace = _validate_trace(raw)
                accumulator.document(
                    json.dumps(
                        {key: value for key, value in raw.items() if key != "transitions"}, sort_keys=True
                    ),
                    ref=provenance.source_ref,
                    kind="reported_trace_descriptor",
                    byte_digest=_sha(data),
                )
                accumulator.warning(
                    "Offline trace observations and rewards are supplied evidence; simulator validity and policy performance require independent actual execution."
                )
            else:
                self._project(raw, accumulator, provenance.source_ref, _sha(data))
        else:
            self._text_document(data, filename, accumulator, provenance.source_ref)
        return self._bundle(data, filename, kind, provenance, accumulator, console)

    def ingest_dragon_record(
        self, record: Mapping[str, Any], *, provenance: GameSourceProvenance, console_id: str | None = None
    ) -> GameSourceBundle:
        if not isinstance(provenance, GameSourceProvenance) or provenance.origin not in {
            "dragon_record",
            "local_record",
        }:
            _fail("record_binding_required", "Collected knowledge requires scoped local-record provenance")
        if not isinstance(record, dict):
            _fail("invalid_record", "Collected record must be an exact canonical JSON object")
        encoded = _canonical(record)
        if len(encoded) > MAX_TEXT_TREE_BYTES or _sha(encoded) != provenance.record_digest:
            _fail("record_binding_required", "Collected record does not match its admitted exact digest")
        for field, expected in (("tenant_id", provenance.tenant_id), ("owner_id", provenance.owner_id)):
            if field in record and record[field] != expected:
                _fail("foreign_record", "Collected record belongs to a different authority scope")
        accumulator = _Accumulator(provenance.source_ref)
        identifier = record.get("id", record.get("record_id", record.get("_id")))
        _text(identifier, "record_id", limit=512)
        texts = []
        title = record.get("title", "")
        if title:
            texts.append(_text(title, "record title", limit=1000))
        body_found = False
        for field in ("summary", "content", "text", "description", "body"):
            value = record.get(field)
            if value is not None:
                texts.append(_text(value, f"record {field}", limit=MAX_TEXT_FILE_BYTES))
                body_found = True
        claims = record.get("claims", [])
        if not isinstance(claims, (list, tuple)) or len(claims) > 64:
            _fail("invalid_record", "Collected claims are invalid")
        for claim in claims:
            texts.append(_text(claim, "record claim", limit=4000))
        body_found = body_found or bool(claims)
        if not body_found:
            _fail(
                "content_unavailable", "Collected record has a locator/title but no actual acquired content"
            )
        accumulator.document(
            "\n\n".join(texts),
            ref=provenance.source_ref,
            kind="collected_record_claims",
            byte_digest=_sha(encoded),
        )
        accumulator.declared_features(record, provenance.source_ref)
        accumulator.projects.append(
            {
                "record_id": identifier,
                "source_ref": provenance.source_ref,
                "origin": provenance.origin,
                "record_digest": _sha(encoded),
                "evidence": record.get("evidence", []),
                "tags": record.get("tags", []),
                "locator": record.get("url", record.get("link", "")),
            }
        )
        accumulator.warning(
            "Collected record claims and lexical features are not independent verification, legal clearance or model training performance."
        )
        return self._bundle(
            encoded, "knowledge-record.json", "dragon", provenance, accumulator, _platform(console_id)
        )

    def _text_document(self, data: bytes, filename: str, accumulator: _Accumulator, ref: str) -> None:
        if len(data) > MAX_TEXT_FILE_BYTES:
            _fail("text_limit", "Static source text exceeds its per-file byte limit")
        accumulator.text_bytes += len(data)
        if accumulator.text_bytes > MAX_TEXT_TREE_BYTES:
            _fail("text_limit", "Static source text exceeds its total tree byte limit")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError as exc:
            raise GameIngestionError("unsupported_text", "Source text must be actual UTF-8 bytes") from exc
        if "\x00" in text:
            _fail("unsupported_text", "Binary source is not a UTF-8 text document")
        accumulator.document(text, ref=ref, kind="static_source_text", byte_digest=_sha(data))
        dimension = re.search(r"\b(?:CharacterBody|RigidBody|Node|Sprite|Camera)(2D|3D)\b", text)
        if dimension:
            accumulator.features["project"]["dimension"] = {
                "value": dimension.group(1).casefold(),
                "classification": "syntax_observation",
                "evidence_ref": ref,
                "character_span": [dimension.start(), dimension.end()],
            }
        constants = {}
        for match in re.finditer(
            r"(?im)^\s*(?:(?:const|var|let|float|int|public|private|static|readonly)\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[A-Za-z_][A-Za-z0-9_]*)?\s*=\s*(-?\d+(?:\.\d+)?)(?![\w.])",
            text,
        ):
            name = match.group(1).casefold()
            if name not in {
                "speed",
                "move_speed",
                "player_speed",
                "jump_speed",
                "jump_velocity",
                "gravity",
                "friction",
                "max_health",
                "enemy_speed",
                "coin_value",
            }:
                continue
            value = float(match.group(2))
            if math.isfinite(value) and abs(value) <= 1e6 and name not in constants:
                constants[name] = {
                    "value": value,
                    "classification": "source_literal",
                    "evidence_ref": ref,
                    "character_span": [match.start(2), match.end(2)],
                    "units": "not_established",
                }
        if constants:
            accumulator.features["project"].setdefault("numeric_hints", {}).update(constants)
        if PurePosixPath(filename).name == "project.godot":
            accumulator.features["project"]["engine"] = {
                "value": "godot",
                "classification": "observed_manifest",
                "evidence_ref": ref,
            }
            for match in re.finditer(r"(?m)^config/name\s*=\s*\"([^\"\r\n]{1,200})\"", text):
                accumulator.features["project"]["title"] = {
                    "value": match.group(1),
                    "classification": "observed_manifest",
                    "evidence_ref": ref,
                }

    def _project(self, raw: Any, accumulator: _Accumulator, ref: str, byte_digest: str) -> None:
        if not isinstance(raw, dict):
            _fail("invalid_project", "Project manifest must be a bounded JSON object")
        accumulator.declared_features(raw, ref)
        title = _text(raw.get("title", raw.get("name", "")), "project title", limit=300, empty=True)
        if raw.get("type") == "map" and type(raw.get("width")) is int and type(raw.get("height")) is int:
            width, height = raw["width"], raw["height"]
            if not 1 <= width <= 4096 or not 1 <= height <= 4096:
                _fail("invalid_project", "Declared tilemap dimensions exceed their bound")
            accumulator.features["project"]["map_dimensions"] = {
                "value": [width, height],
                "classification": "declared",
                "evidence_ref": ref,
                "source_field": "width/height",
                "units": "tiles",
            }
        files = raw.get("files", raw.get("source_tree", {}))
        if files:
            if not isinstance(files, dict) or len(files) > MAX_ARCHIVE_MEMBERS:
                _fail("invalid_project", "Project source tree must be a bounded path-to-text mapping")
            names = set()
            for path, content in sorted(files.items()):
                path = _archive_path(path)
                if path.casefold() in names:
                    _fail("invalid_project", "Project source tree contains normalized path aliases")
                names.add(path.casefold())
                content = _text(content, "project source file", limit=MAX_TEXT_FILE_BYTES, empty=True)
                self._text_document(
                    content.encode("utf-8"), path, accumulator, ref + "#file=" + quote(path, safe="/")
                )
        manifest = {key: value for key, value in raw.items() if key not in {"files", "source_tree"}}
        if len(_canonical(manifest)) > MAX_TEXT_FILE_BYTES:
            _fail("invalid_project", "Project manifest exceeds its bounded metadata limit")
        accumulator.projects.append(
            {
                "title": title,
                "manifest": manifest,
                "source_ref": ref,
                "content_digest": byte_digest,
                "file_count": len(files),
            }
        )
        accumulator.document(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            ref=ref,
            kind="declared_game_project",
            byte_digest=byte_digest,
        )
        accumulator.warning(
            "Uploaded project scripts are inspected as static untrusted text and are never executed by ingestion."
        )

    def _archive(self, data: bytes, accumulator: _Accumulator) -> None:
        _preflight_zip(data)
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError) as exc:
            raise GameIngestionError(
                "invalid_archive", "Only bounded valid ZIP archives are supported"
            ) from exc
        with archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_MEMBERS:
                _fail("archive_limit", "ZIP member count exceeds its bound")
            names = set()
            expanded = 0
            validated = []
            for info in infos:
                path = _archive_path(info.filename.rstrip("/"))
                if path.casefold() in names:
                    _fail("unsafe_archive", "ZIP contains duplicate or normalized aliased paths")
                names.add(path.casefold())
                if info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                    _fail("unsafe_archive", "Encrypted ZIP members and symlinks are not admitted")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    _fail("unsupported_archive", "ZIP compression method is unsupported")
                if info.is_dir():
                    continue
                expanded += info.file_size
                if (
                    info.file_size < 0
                    or info.file_size > MAX_SOURCE_BYTES
                    or expanded > MAX_SOURCE_BYTES
                    or info.file_size > max(1, info.compress_size) * 100
                ):
                    _fail("archive_limit", "ZIP expanded size or compression ratio exceeds its bound")
                if PurePosixPath(path).suffix.casefold() in _ARCHIVE_EXTENSIONS:
                    _fail("unsafe_archive", "Nested archive sources are not admitted")
                validated.append((info, path))
            for info, path in validated:
                try:
                    with archive.open(info) as handle:
                        member = handle.read(info.file_size + 1)
                except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, zlib.error) as exc:
                    raise GameIngestionError(
                        "invalid_archive", "ZIP member failed bounded integrity reading"
                    ) from exc
                if len(member) != info.file_size:
                    _fail("invalid_archive", "ZIP actual member length differs from its directory record")
                ref = accumulator.source_ref + "#file=" + quote(path, safe="/")
                extension = PurePosixPath(path).suffix.casefold()
                if extension in _ROM_EXTENSIONS or _has_rom_signature(member):
                    accumulator.rom(member, path, ref)
                elif extension in _TEXT_EXTENSIONS:
                    if any(part in {".git", ".env"} for part in PurePosixPath(path).parts) or PurePosixPath(
                        path
                    ).name.startswith(".env"):
                        accumulator.assets.append(
                            {
                                "path": path,
                                "source_ref": ref,
                                "content_digest": _sha(member),
                                "byte_length": len(member),
                                "format": "private_configuration_omitted",
                            }
                        )
                        accumulator.warning(
                            "Obvious private configuration files are inventoried by digest and omitted from learning documents."
                        )
                    elif extension == ".json":
                        raw = _json(member)
                        if isinstance(raw, dict) and raw.get("schema_version") == "skeleton.game.trace.v1":
                            if accumulator.trace is not None:
                                _fail(
                                    "invalid_archive", "An archive may contain only one offline episode trace"
                                )
                            accumulator.trace = _validate_trace(raw)
                        else:
                            self._project(raw, accumulator, ref, _sha(member))
                    else:
                        self._text_document(member, path, accumulator, ref)
                else:
                    accumulator.assets.append(_asset(member, path, ref))
            if not accumulator.documents and not accumulator.assets and not accumulator.trace:
                _fail("content_unavailable", "ZIP contains no supported game source content")

    def _bundle(
        self,
        data: bytes,
        filename: str,
        kind: str,
        provenance: GameSourceProvenance,
        accumulator: _Accumulator,
        console: str | None,
    ) -> GameSourceBundle:
        if (
            accumulator.platforms
            and console is not None
            and console not in accumulator.platforms
            and not (
                console == "gb"
                and accumulator.platforms == {"gbc"}
                and all(rom.get("cgb_flag") == 0x80 for rom in accumulator.roms)
            )
        ):
            _fail("platform_mismatch", "Declared console differs from the actual recognized cartridge source")
        platform = (
            next(iter(accumulator.platforms))
            if len(accumulator.platforms) == 1
            else "multiple" if accumulator.platforms else console or "unknown"
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "bundle_id": "game-source:" + _sha(data),
            "source_digest": _sha(data),
            "source_kind": kind,
            "filename": filename,
            "console_id": platform,
            "byte_length": len(data),
            "provenance": provenance.to_dict(),
            "metadata": {
                "roms": accumulator.roms,
                "projects": accumulator.projects,
                "source_execution": "not_performed",
                "classification_authority": "bounded_source_observations",
            },
            "features": accumulator.bounded_features(),
            "documents": accumulator.documents,
            "assets": accumulator.assets,
            "warnings": accumulator.warnings,
            "trace": accumulator.trace,
        }
        payload["bundle_digest"] = _sha(_canonical(payload))
        return GameSourceBundle(_canonical(payload).decode("utf-8"))


class DragonGameKnowledgeAdapter:
    """Read existing reviewed Dragon records; never create a knowledge authority.

    ``owner`` comes from Dragon Academy's authenticated principal derivation.
    The host owns this connection and live rights checks. Review/consent is
    rechecked on each resolution and is distinct from permission to reuse text.
    """

    def __init__(self, db: sqlite3.Connection, owner: str) -> None:
        if not isinstance(db, sqlite3.Connection):
            _fail("dragon_storage_unavailable", "Existing Dragon Academy connection is required")
        if not isinstance(owner, str) or not re.fullmatch(r"[0-9a-f]{64}", owner):
            _fail("dragon_scope_invalid", "Canonical authenticated Dragon owner is required")
        from skeleton.ai.webcrawler.dragon_family_custody_bridge import (
            DragonFamilyCustodyBridge,
        )

        self.db = db
        self.owner = owner
        self.custody = DragonFamilyCustodyBridge(db, owner)

    @staticmethod
    def _reference(reference: str) -> tuple[str, str]:
        _text(reference, "dragon source reference", limit=512)
        if not reference.startswith("dragon:") or ":" not in reference[7:]:
            _fail("dragon_reference_invalid", "Use an exact dragon:source_id:revision_sha256 reference")
        source_id, revision = reference[7:].rsplit(":", 1)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}", source_id) or not re.fullmatch(
            r"[0-9a-f]{64}", revision
        ):
            _fail("dragon_reference_invalid", "Dragon source identity or exact revision is invalid")
        return source_id, revision

    def _record(self, reference: str) -> dict[str, Any]:
        from skeleton.ai.webcrawler.dragon_family import SourceReceipt

        source_id, revision = self._reference(reference)
        source_limits = self.db.execute(
            "SELECT length(url),length(media),length(topics_json) FROM dragon_family_sources "
            "WHERE owner=? AND source_id=?",
            (self.owner, source_id),
        ).fetchone()
        if source_limits is None or any(
            type(size) is not int or size > bound
            for size, bound in zip(source_limits, (2048, 64, 4096), strict=True)
        ):
            _fail("dragon_record_unavailable", "Source metadata is missing or exceeds the digestion budget")
        source = self.db.execute(
            "SELECT url,media,topics_json FROM dragon_family_sources WHERE owner=? AND source_id=?",
            (self.owner, source_id),
        ).fetchone()
        if source is None:
            _fail("dragon_record_unavailable", "Source is absent from this authenticated Dragon catalog")
        url, media, topics_json = source
        _text(url, "Dragon source URL", limit=2048)
        _text(media, "Dragon media", limit=64)
        _text(topics_json, "Dragon topics", limit=4096)
        topics = _json(topics_json.encode("utf-8"))
        if not isinstance(topics, list) or len(topics) > 64:
            _fail("dragon_record_invalid", "Dragon source topics exceed their bounded schema")
        for topic in topics:
            _text(topic, "Dragon topic", limit=128)
        # Reject oversized rows before bringing their bodies into memory.
        bounds = self.db.execute(
            "SELECT COUNT(*),COALESCE(MAX(length(improvement)),0),COALESCE(MAX(length(review_digest)),0) "
            "FROM dragon_family_readings "
            "WHERE owner=? AND source_id=? AND content_digest=?",
            (self.owner, source_id, revision),
        ).fetchone()
        if not 1 <= bounds[0] <= 64 or bounds[1] > 240 or bounds[2] > 64:
            _fail("dragon_record_unavailable", "Exact gathered revision is missing or exceeds reading limits")
        readings = self.db.execute(
            "SELECT review_digest,observed_at,improvement FROM dragon_family_readings "
            "WHERE owner=? AND source_id=? AND content_digest=? ORDER BY observed_at DESC,dragon LIMIT 64",
            (self.owner, source_id, revision),
        ).fetchall()
        active = []
        # Bound each current claim before the canonical verifier reads its
        # complete history to recompute the approved evidence fingerprint.
        claim_limits = self.db.execute(
            "SELECT COUNT(DISTINCT l.claim_id),COALESCE(MAX(length(l.claim_id)),0) "
            "FROM dragon_practice_lessons l JOIN dragon_evidence_passes e "
            "ON e.owner=l.owner AND e.claim_id=l.claim_id WHERE l.owner=? AND l.consent=1 "
            "AND e.source_id=? AND e.source_revision=?",
            (self.owner, source_id, revision),
        ).fetchone()
        if not 1 <= claim_limits[0] <= 20 or claim_limits[1] > 256:
            _fail("dragon_record_limit", "Current reviewed source exceeds bounded claim identity limits")
        claim_rows = self.db.execute(
            "SELECT DISTINCT l.claim_id FROM dragon_practice_lessons l JOIN dragon_evidence_passes e "
            "ON e.owner=l.owner AND e.claim_id=l.claim_id WHERE l.owner=? AND l.consent=1 "
            "AND e.source_id=? AND e.source_revision=? LIMIT 21",
            (self.owner, source_id, revision),
        ).fetchall()
        if not 1 <= len(claim_rows) <= 20:
            _fail("dragon_record_unavailable", "Source has no bounded current consented review")
        for (claim_id,) in claim_rows:
            _text(claim_id, "Dragon claim identity", limit=256)
            count, size, longest, invalid = self.db.execute(
                "SELECT COUNT(*),COALESCE(SUM(length(observation)+length(evidence_locator)+"
                "length(source_id)+length(source_revision)+length(pass_id)+length(independence_group)),0),"
                "COALESCE(MAX(length(observation)),0),COALESCE(SUM(CASE WHEN "
                "typeof(supports)='integer' AND supports IN (0,1) "
                "AND typeof(confidence) IN ('real','integer') AND confidence BETWEEN 0 AND 1 "
                "AND typeof(reliability) IN ('real','integer') AND reliability BETWEEN 0 AND 1 "
                "THEN 0 ELSE 1 END),0) FROM dragon_evidence_passes WHERE owner=? AND claim_id=?",
                (self.owner, claim_id),
            ).fetchone()
            if not 1 <= count <= 256 or size > MAX_TEXT_TREE_BYTES or longest > 4000 or invalid:
                _fail("dragon_record_limit", "Current claim exceeds bounded evidence inspection")
        seen_reviews = set()
        for review, observed, improvement in readings:
            if review in seen_reviews:
                continue
            seen_reviews.add(review)
            receipt = SourceReceipt(source_id, revision, review, observed, improvement)
            if self.custody.verify(receipt):
                active.append(receipt)
                break
        if not active:
            _fail("dragon_review_withdrawn", "This revision has no current canonical consent and review")
        selected = active[0]
        lesson_limits = self.db.execute(
            "SELECT COALESCE(MAX(length(title)),0),COALESCE(MAX(length(mechanics_json)),0) "
            "FROM dragon_practice_lessons WHERE owner=? AND consent=1 AND review_digest=?",
            (self.owner, selected.review_digest),
        ).fetchone()
        if lesson_limits[0] > 1000 or lesson_limits[1] > 4096:
            _fail("dragon_record_limit", "Reviewed lesson metadata exceeds the digestion budget")
        lessons = self.db.execute(
            "SELECT DISTINCT l.claim_id,l.title,l.evidence_digest,l.review_digest,l.mechanics_json "
            "FROM dragon_practice_lessons l JOIN dragon_evidence_passes e "
            "ON e.owner=l.owner AND e.claim_id=l.claim_id WHERE l.owner=? AND l.consent=1 "
            "AND l.review_digest=? AND e.source_id=? AND e.source_revision=? ORDER BY l.claim_id LIMIT 21",
            (self.owner, selected.review_digest, source_id, revision),
        ).fetchall()
        evidence = []
        claims = []
        mechanics = set()
        for claim_id, title, recorded_digest, review, mechanics_json in lessons:
            belief = self.custody.ledger.belief(self.owner, claim_id, authorized=True)
            if belief.evidence_digest != recorded_digest:
                continue
            _text(title, "Dragon lesson title", limit=1000)
            _text(mechanics_json, "Dragon reviewed mechanics", limit=4096)
            declared = _json(mechanics_json.encode("utf-8"))
            if not isinstance(declared, list) or len(declared) > 64:
                _fail("dragon_record_invalid", "Reviewed Dragon mechanics are invalid")
            for mechanic in declared:
                mechanics.add(_text(mechanic, "reviewed mechanic", limit=80))
            claims.append(
                {"claim_id": claim_id, "title": title, "review_digest": review, "belief": asdict(belief)}
            )
            for item in self.custody.ledger.readings(self.owner, claim_id, authorized=True):
                if item.source_id == source_id and item.source_revision == revision:
                    evidence.append(asdict(item))
                    if len(evidence) > 64:
                        _fail(
                            "dragon_record_limit",
                            "Source observation count exceeds the game digestion budget",
                        )
        if not evidence or not claims:
            _fail("dragon_review_withdrawn", "Current ledger no longer matches the reviewed lesson")
        body = "\n\n".join(item["observation"] for item in evidence)
        if len(body.encode("utf-8")) > MAX_TEXT_FILE_BYTES:
            _fail("dragon_record_limit", "Actual source observations exceed the source text budget")
        record = {
            "schema_version": "skeleton.game.dragon_record.v1",
            "id": reference,
            "dragon_owner": self.owner,
            "title": claims[0]["title"],
            "content": body,
            "url": url,
            "media": media,
            "tags": topics,
            "mechanics": sorted(mechanics),
            "source_id": source_id,
            "source_revision": revision,
            "review_digest": selected.review_digest,
            "observed_at": selected.observed_at,
            "reviewed_claims": claims,
            "evidence": evidence,
            "content_semantics": "Exact gathered ledger observations; heuristic belief is not factual proof",
        }
        if len(_canonical(record)) > MAX_TEXT_TREE_BYTES:
            _fail("dragon_record_limit", "Normalized Dragon record exceeds its bounded evidence budget")
        return record

    def resolve_record(self, *, source_ref: str, authorized: bool) -> dict[str, Any]:
        """Return exact acquired observation record for canonical-byte storage.

        Encode with UTF-8, sorted keys, compact JSON and ensure_ascii=False.
        The source revision hashes acquired crawler bytes; the normalized
        record's digest separately hashes this exact projection.
        """
        if authorized is not True:
            _fail(
                "dragon_authorization_required",
                "Authenticated Dragon and source rights authority is required",
            )
        # Savepoint preserves a coherent read of consent, source custody and
        # evidence even if another connection changes them during decoding.
        self.db.execute("SAVEPOINT game_dragon_read")
        try:
            record = self._record(source_ref)
            self.db.execute("RELEASE SAVEPOINT game_dragon_read")
            return record
        except sqlite3.DatabaseError as exc:
            self.db.execute("ROLLBACK TO SAVEPOINT game_dragon_read")
            self.db.execute("RELEASE SAVEPOINT game_dragon_read")
            raise GameIngestionError(
                "dragon_storage_unavailable", "Canonical Dragon storage cannot be read"
            ) from exc
        except (TypeError, ValueError, OverflowError) as exc:
            self.db.execute("ROLLBACK TO SAVEPOINT game_dragon_read")
            self.db.execute("RELEASE SAVEPOINT game_dragon_read")
            if isinstance(exc, GameIngestionError):
                raise
            raise GameIngestionError("dragon_record_invalid", "Canonical Dragon record is malformed") from exc
        except BaseException:
            self.db.execute("ROLLBACK TO SAVEPOINT game_dragon_read")
            self.db.execute("RELEASE SAVEPOINT game_dragon_read")
            raise

    def resolve(
        self,
        *,
        source_ref: str,
        tenant_id: str,
        owner_id: str,
        rights_refs: tuple[str, ...],
        rights_acknowledged: bool,
        authorized: bool,
        console_id: str | None = None,
    ) -> GameSourceBundle:
        record = self.resolve_record(source_ref=source_ref, authorized=authorized)
        provenance = GameSourceProvenance(
            source_ref=source_ref,
            tenant_id=tenant_id,
            owner_id=owner_id,
            rights_refs=rights_refs,
            rights_acknowledged=rights_acknowledged,
            origin="dragon_record",
            record_digest=_sha(_canonical(record)),
            license_ref="existing-dragon-review-plus-explicit-source-rights",
        )
        return GameLearningIngestor().ingest_dragon_record(
            record, provenance=provenance, console_id=console_id
        )

    def assert_current(self, bundle: GameSourceBundle, *, authorized: bool) -> None:
        if not isinstance(bundle, GameSourceBundle):
            _fail("dragon_record_invalid", "Exact normalized Dragon source bundle is required")
        payload = bundle.to_dict()
        provenance = payload["provenance"]
        if provenance.get("origin") != "dragon_record" or payload.get("source_kind") != "dragon":
            _fail(
                "dragon_record_invalid",
                "A Dragon source bundle with its exact original provenance is required",
            )
        record = self.resolve_record(source_ref=provenance["source_ref"], authorized=authorized)
        original = GameSourceProvenance(
            source_ref=provenance["source_ref"],
            tenant_id=provenance["tenant_id"],
            owner_id=provenance["owner_id"],
            rights_refs=tuple(provenance["rights_refs"]),
            license_ref=provenance["license_ref"],
            rights_acknowledged=provenance["rights_acknowledged"],
            origin="dragon_record",
            record_digest=_sha(_canonical(record)),
        )
        current = GameLearningIngestor().ingest_dragon_record(
            record,
            provenance=original,
            console_id=payload["console_id"] if payload["console_id"] != "unknown" else None,
        )
        if current.bundle_digest != bundle.bundle_digest:
            _fail("dragon_source_changed", "Exact reviewed Dragon source evidence changed or was withdrawn")

    def list_sources(self, *, authorized: bool, limit: int = 32) -> list[dict[str, Any]]:
        if authorized is not True or type(limit) is not int or not 1 <= limit <= 64:
            _fail(
                "dragon_authorization_required", "Authenticated bounded Dragon inventory access is required"
            )
        rows = self.db.execute(
            "SELECT source_id,content_digest,MAX(observed_at) FROM dragon_family_readings "
            "WHERE owner=? GROUP BY source_id,content_digest ORDER BY MAX(observed_at) DESC,source_id LIMIT ?",
            (self.owner, limit),
        ).fetchall()
        result = []
        for source_id, revision, observed in rows:
            reference = "dragon:" + source_id + ":" + revision
            try:
                record = self.resolve_record(source_ref=reference, authorized=True)
            except GameIngestionError:
                continue
            result.append(
                {
                    "source_ref": reference,
                    "source_id": source_id,
                    "source_revision": revision,
                    "title": record["title"],
                    "url": record["url"],
                    "media": record["media"],
                    "observed_at": observed,
                    "current_review": True,
                }
            )
        return result


def ingest_source(
    *,
    kind: str,
    filename: str,
    provenance: GameSourceProvenance,
    data: bytes | None = None,
    record: Mapping[str, Any] | None = None,
    console_id: str | None = None,
) -> GameSourceBundle:
    ingestor = GameLearningIngestor()
    if kind == "dragon":
        if record is None:
            _fail("content_unavailable", "Exact admitted local knowledge record is required")
        return ingestor.ingest_dragon_record(record, provenance=provenance, console_id=console_id)
    if data is None:
        _fail("content_unavailable", "Exact source bytes are required")
    return ingestor.ingest_bytes(
        data, filename=filename, provenance=provenance, source_kind=kind, console_id=console_id
    )
