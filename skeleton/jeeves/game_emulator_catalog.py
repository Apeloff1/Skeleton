"""Operator-approved local emulator libraries and exact bounded game content.

Catalog inspection never loads native code. Actual libretro initialization is
owned by the isolated emulator worker, which must revalidate these descriptors.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import stat
import struct
import tempfile
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

REGISTRY_SCHEMA = "skeleton.game.emulator_registry.v1"
CONTENT_SCHEMA = "skeleton.game.emulator_content.v1"
REGISTRY_ENV = "SKL_GAME_EMULATOR_REGISTRY"
MAX_MANIFEST_BYTES = 1048576
MAX_LIBRARY_BYTES = 256 * 1024 * 1024
MAX_CONTENT_BYTES = 16 * 1024 * 1024
MAX_CONTENT_FILES = 96
MAX_REFERENCED_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_REFERENCED_BUNDLE_BYTES = 4 * 1024 * 1024 * 1024
MAX_STREAM_CHUNK_BYTES = 1024 * 1024
MAX_CONTENT_PREFIX_BYTES = 256 * 1024
MAX_FIRMWARE_BYTES = 64 * 1024 * 1024
_LIBRARY_INSPECTION_CACHE: dict[str, tuple[tuple[int, ...], dict[str, Any]]] = {}
REQUIRED_SYMBOLS = frozenset(
    {
        "retro_api_version",
        "retro_set_environment",
        "retro_set_video_refresh",
        "retro_set_audio_sample",
        "retro_set_audio_sample_batch",
        "retro_set_input_poll",
        "retro_set_input_state",
        "retro_init",
        "retro_deinit",
        "retro_get_system_info",
        "retro_get_system_av_info",
        "retro_set_controller_port_device",
        "retro_reset",
        "retro_run",
        "retro_serialize_size",
        "retro_serialize",
        "retro_unserialize",
        "retro_load_game",
        "retro_unload_game",
        "retro_get_memory_data",
        "retro_get_memory_size",
    }
)


class EmulatorCatalogError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _fail(code: str, message: str):
    raise EmulatorCatalogError(code, message)


def _canonical(value: Any) -> bytes:
    try:
        result = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise EmulatorCatalogError("invalid_json", "Emulator metadata must be bounded finite JSON") from exc
    if len(result) > MAX_MANIFEST_BYTES:
        _fail("metadata_limit", "Emulator metadata exceeds its byte budget")
    return result


def _json(data: bytes) -> Any:
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                _fail("invalid_manifest", "Emulator metadata contains duplicate JSON keys")
            result[key] = value
        return result

    if len(data) > MAX_MANIFEST_BYTES:
        _fail("metadata_limit", "Emulator metadata exceeds its byte budget")
    try:
        return json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda _: _fail("invalid_manifest", "Non-finite emulator metadata"),
        )
    except EmulatorCatalogError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EmulatorCatalogError("invalid_manifest", "Emulator metadata is not valid bounded JSON") from exc


def _text(value: Any, label: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 for c in value):
        _fail("invalid_manifest", f"Invalid {label}")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_canonical(value))


def _safe_path(value: str) -> Path:
    path = Path(_text(value, "operator path", 4096))
    if not path.is_absolute() or ".." in path.parts:
        _fail("unsafe_path", "Operator paths must be exact absolute paths")
    for component in (path, *path.parents):
        try:
            if stat.S_ISLNK(component.lstat().st_mode):
                _fail("unsafe_path", "Operator paths cannot traverse symbolic links")
        except FileNotFoundError:
            _fail("missing_installation", "An operator-approved installation path is unavailable")
    return path


def _read_file(path: Path, maximum: int, *, trusted: bool = False) -> bytes:
    path = _safe_path(str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum:
                _fail("file_limit", "Installation files must be nonempty bounded regular files")
            if trusted and (before.st_mode & 0o022 or before.st_uid not in {0, os.geteuid()}):
                _fail(
                    "untrusted_installation", "Operator installation files cannot be writable by other users"
                )
            data = stream.read(maximum + 1)
            after, final = os.fstat(stream.fileno()), path.stat(follow_symlinks=False)
            identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
            if (
                len(data) > maximum
                or identity(before) != identity(after)
                or identity(after) != identity(final)
            ):
                _fail("installation_changed", "Installation bytes changed during inspection")
            return data
    except EmulatorCatalogError:
        raise
    except OSError as exc:
        raise EmulatorCatalogError(
            "installation_unavailable", "Operator installation files cannot be read"
        ) from exc


def inspect_libretro_library(path: str | Path) -> dict[str, Any]:
    """Read actual ELF dynamic symbols without dlopen or executing constructors."""
    path = _safe_path(str(path))
    current = path.stat(follow_symlinks=False)
    fingerprint = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
        current.st_ctime_ns,
        current.st_mode,
        current.st_uid,
    )
    previous = _LIBRARY_INSPECTION_CACHE.get(str(path))
    if previous is not None and previous[0] == fingerprint:
        return {**previous[1], "exported_symbols": list(previous[1]["exported_symbols"])}
    data = _read_file(path, MAX_LIBRARY_BYTES, trusted=True)
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] not in {1, 2} or data[5] not in {1, 2}:
        _fail("unsupported_library", "This host admits inspected ELF shared libraries only")
    bits, order = data[4], "<" if data[5] == 1 else ">"
    if struct.unpack_from(order + "H", data, 16)[0] != 3:
        _fail("unsupported_library", "An installed ELF shared object is required")
    machine = struct.unpack_from(order + "H", data, 18)[0]
    arch = {3: "x86", 62: "x86_64", 40: "arm", 183: "aarch64", 243: "riscv64"}.get(machine)
    host = {"amd64": "x86_64", "arm64": "aarch64", "i386": "x86", "i686": "x86"}.get(
        platform.machine().lower(), platform.machine().lower()
    )
    if platform.system() != "Linux" or arch != host or bits != (2 if struct.calcsize("P") == 8 else 1):
        _fail("architecture_mismatch", "Installed core architecture does not match this local host")
    if bits == 2:
        section_offset = struct.unpack_from(order + "Q", data, 40)[0]
        section_size, count = struct.unpack_from(order + "HH", data, 58)
        fmt, expected_size = order + "IIQQQQIIQQ", 64
    else:
        section_offset = struct.unpack_from(order + "I", data, 32)[0]
        section_size, count = struct.unpack_from(order + "HH", data, 46)
        fmt, expected_size = order + "IIIIIIIIII", 40
    if (
        section_size < expected_size
        or not 1 <= count <= 4096
        or section_offset + section_size * count > len(data)
    ):
        _fail("invalid_library", "ELF section directory is missing or exceeds its bounded layout")
    sections = [struct.unpack_from(fmt, data, section_offset + i * section_size) for i in range(count)]
    exported = set()
    for section in sections:
        if section[1] != 11:  # SHT_DYNSYM, not unexported debugging symbols.
            continue
        offset, size, link, stride = section[4], section[5], section[6], section[9]
        entry_min = 24 if bits == 2 else 16
        if not 0 <= link < count or stride < entry_min or size % stride or size // stride > 262144:
            _fail("invalid_library", "ELF dynamic symbols exceed their bounded structure")
        strings = sections[link]
        if strings[1] != 3:
            _fail("invalid_library", "ELF dynamic symbols require an actual string-table section")
        start, length = strings[4], strings[5]
        if offset + size > len(data) or start + length > len(data) or length > 32 * 1024 * 1024:
            _fail("invalid_library", "ELF dynamic symbols or strings exceed actual bytes")
        for pos in range(offset, offset + size, stride):
            name_offset = struct.unpack_from(order + "I", data, pos)[0]
            info, visibility, definition = (
                (data[pos + 4], data[pos + 5], struct.unpack_from(order + "H", data, pos + 6)[0])
                if bits == 2
                else (data[pos + 12], data[pos + 13], struct.unpack_from(order + "H", data, pos + 14)[0])
            )
            if (
                definition == 0
                or info >> 4 not in {1, 2}
                or info & 15 not in {2, 10}
                or visibility & 3 not in {0, 3}
            ):
                continue
            if name_offset >= length:
                _fail("invalid_library", "ELF dynamic symbol name lies outside its string table")
            end = data.find(b"\x00", start + name_offset, min(start + length, start + name_offset + 256))
            if end < 0:
                continue
            name = data[start + name_offset : end].decode("ascii", errors="replace")
            if name.startswith("retro_"):
                exported.add(name)
    missing = REQUIRED_SYMBOLS - exported
    if missing:
        _fail("missing_libretro_abi", "Installed library lacks required exported libretro ABI functions")
    result = {
        "library_path": str(_safe_path(str(path))),
        "library_sha256": _sha(data),
        "architecture": arch,
        "library_bytes": len(data),
        "exported_symbols": sorted(exported),
    }
    after = path.stat(follow_symlinks=False)
    final_fingerprint = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_uid,
    )
    if final_fingerprint != fingerprint:
        _fail("installation_changed", "Installed core changed during ABI inspection")
    if len(_LIBRARY_INSPECTION_CACHE) >= 96 and str(path) not in _LIBRARY_INSPECTION_CACHE:
        _LIBRARY_INSPECTION_CACHE.pop(next(iter(_LIBRARY_INSPECTION_CACHE)))
    _LIBRARY_INSPECTION_CACHE[str(path)] = (fingerprint, result)
    return {**result, "exported_symbols": list(result["exported_symbols"])}


# These are real named libretro implementations, not compatibility evidence.
# Each canonical hardware row remains visible even where no adapter is mapped.
_CORE_TARGET_GROUPS = {
    "fceumm": ("nes", "famicom_disk_system"),
    "nestopia": ("nes", "famicom_disk_system"),
    "mesen": ("nes", "famicom_disk_system"),
    "snes9x": ("snes",),
    "bsnes": ("snes",),
    "genesis_plus_gx": ("genesis", "master_system", "sega_mark_iii", "sega_sg1000", "game_gear", "sega_cd"),
    "picodrive": ("genesis", "master_system", "sega_cd", "sega_32x"),
    "gambatte": ("game_boy", "game_boy_color", "game_boy_pocket", "game_boy_light"),
    "sameboy": ("game_boy", "game_boy_color", "game_boy_pocket", "game_boy_light"),
    "mgba": ("game_boy", "game_boy_color", "game_boy_advance", "game_boy_micro", "game_boy_player"),
    "vba_next": ("game_boy_advance", "game_boy_micro", "game_boy_player"),
    "mupen64plus_next": ("nintendo_64",),
    "parallel_n64": ("nintendo_64",),
    "swanstation": ("ps1",),
    "pcsx_rearmed": ("ps1",),
    "mednafen_psx_hw": ("ps1",),
    "mednafen_saturn": ("saturn",),
    "yabause": ("saturn",),
    "flycast": ("dreamcast", "sega_naomi", "sega_atom_iswave"),
    "melonds": ("nintendo_ds", "nintendo_dsi"),
    "desmume": ("nintendo_ds",),
    "ppsspp": ("psp", "psp_go", "psp_street"),
    "dolphin": ("gamecube", "wii"),
    "pcsx2": ("ps2",),
    "citra": ("nintendo_3ds", "nintendo_2ds", "new_nintendo_3ds"),
    "stella": ("atari_2600",),
    "stella2014": ("atari_2600",),
    "prosystem": ("atari_7800",),
    "a5200": ("atari_5200",),
    "atari800": ("atari_5200", "atari_400_800", "atari_130xe"),
    "virtualjaguar": ("atari_jaguar",),
    "handy": ("lynx",),
    "hatari": ("atari_st", "atari_falcon"),
    "vecx": ("vectrex",),
    "freeintv": ("intellivision",),
    "gearcoleco": ("colecovision",),
    "mednafen_pce_fast": ("turbografx_16", "pc_engine_cd"),
    "mednafen_supergrafx": ("turbografx_16",),
    "mednafen_pcfx": ("pc_fx",),
    "mednafen_vb": ("virtual_boy",),
    "mednafen_wswan": ("wonderswan", "wonderswan_color"),
    "mednafen_ngp": ("neo_geo_pocket", "neo_geo_pocket_color"),
    "pokemini": ("pokemon_mini",),
    "opera": ("3do",),
    "neocd": ("neo_geo_cd",),
    "fbneo": ("neo_geo",),
    "fuse": ("zx_spectrum",),
    "eightyone": ("zx81",),
    "cap32": ("amstrad_cpc",),
    "crocods": ("amstrad_cpc",),
    "bluemsx": ("msx1", "msx2", "msx_turbo_r", "colecovision"),
    "fmsx": ("msx1", "msx2"),
    "vice_x64": ("commodore_64",),
    "vice_x64sc": ("commodore_64",),
    "vice_x128": ("commodore_128",),
    "vice_xvic": ("commodore_vic20",),
    "vice_xplus4": ("commodore_plus4",),
    "vice_xpet": ("commodore_pet",),
    "puae": ("amiga_500", "amiga_1200", "amiga_cd32"),
    "px68k": ("sharp_x68000",),
    "quasi88": ("nec_pc_8801",),
    "nekop2": ("nec_pc_9801",),
    "np2kai": ("nec_pc_9801",),
    "dosbox_pure": (
        "dos_8086",
        "dos_vga",
        "dos_cga",
        "dos_ega",
        "dos_vesa",
        "windows_31",
        "windows_95",
        "windows_98",
        "windows_me",
    ),
    "dosbox_svn": ("dos_8086", "dos_vga", "dos_cga", "dos_ega", "dos_vesa", "windows_31"),
    "gearboy": ("game_boy", "game_boy_color", "game_boy_pocket", "game_boy_light"),
    "gearsystem": ("master_system", "sega_mark_iii", "sega_sg1000", "game_gear"),
    "gpsp": ("game_boy_advance", "game_boy_micro", "game_boy_player"),
    "mednafen_psx": ("ps1",),
    "snes9x2005": ("snes",),
    "snes9x2010": ("snes",),
    "mednafen_supafaust": ("snes",),
    "blastem": ("genesis",),
    "mame": (
        "fairchild_channel_f",
        "rca_studio_ii",
        "bally_astrocade",
        "apple_ii",
        "apple_iigs",
        "bbc_micro",
        "acorn_electron",
        "trs80_model_i",
        "ti_99_4a",
        "oric_atmos",
        "fm_towns",
        "philips_cdi",
    ),
    "scummvm": ("dos_8086", "dos_vga", "pc_linux", "pc_windows", "pc_macos"),
}

# Data admission hints taken from the pinned upstream retro_system_info
# declarations. The worker validates its actual loaded implementation again.
# Unsafe archive containers and DSi-specific content are intentionally excluded.
_CORE_CONTENT_EXTENSIONS = {
    # Extension hints are grounded in the pinned libretro system-info sources.
    # These DO NOT activate a core or bypass the worker's live extension check.
    "nestopia": "nes|unf|unif",
    "sameboy": "gb|gbc",
    "vba_next": "gba",
    "a5200": "a52|bin",
    "vice_x64sc": "d64|d71|d80|d81|d82|g64|g41|x64|t64|tap|prg|p00|crt|bin|cmd|m3u|vfl|vsf|rom",
    "vice_x128": "d64|d71|d81|g64|x64|t64|tap|prg|p00|crt|bin|cmd|m3u",
    "vice_xvic": "d64|t64|tap|prg|p00|crt|bin|cmd|m3u|rom",
    "vice_xplus4": "d64|d81|t64|tap|prg|p00|crt|bin|cmd|m3u|rom",
    "vice_xpet": "d64|t64|tap|prg|p00|bin|cmd|m3u|rom",
    "mesen": "nes|unf|unif",
    "bluemsx": "rom|ri|mx1|mx2|dsk|col|sg|sc|sf|cas|m3u",
    "fmsx": "rom|mx1|mx2|dsk|fdi|cas|m3u",
    "vice_x64": "d64|d71|d80|d81|d82|g64|g41|x64|t64|tap|prg|p00|crt|bin|cmd|m3u|vfl|vsf|rom",
    "px68k": "dim|img|d88|88d|hdm|dup|2hd|xdf|hdf|cmd|m3u",
    "quasi88": "d88|m3u|t88|cmt",
    "mednafen_saturn": "cue|ccd|chd|toc|m3u",
    "stella2014": "a26|bin|mvc",
    "prosystem": "a78|bin|cdf",
    "handy": "lnx|lyx|o",
    "mednafen_ngp": "ngp|ngc|ngpc|npc",
    "mednafen_wswan": "ws|wsc|pc2",
    "mednafen_vb": "vb|vboy|bin",
    "mednafen_pce_fast": "pce|cue|chd|m3u",
    "mednafen_supergrafx": "pce|sgx|cue|chd|m3u",
    "vecx": "bin|vec",
    "pokemini": "min",
    "freeintv": "int|bin|rom",
    "fuse": "tzx|tap|z80|rzx|scl|trd|dsk|dck|sna|szx|ipf|m3u",
    "eightyone": "p|tzx|t81",
    "atari800": "xfd|atr|dcm|cas|bin|a52|atx|car|rom|com|xex|m3u",
    "cap32": "dsk|sna|tap|cdt|voc|cpr|m3u",
    "crocods": "sna|dsk|kcr",
    "virtualjaguar": "j64|jag|rom|abs|cof|bin|prg|cue|cdi|chd",
    "gearcoleco": "col|cv|bin|rom|ddp|dsk|m3u",
    "neocd": "cue|chd",
    "opera": "iso|bin|chd|cue",
    "melonds": "nds",
    "picodrive": "bin|gen|smd|md|32x|cue|iso|chd|m3u|sms|gg|sg|sc|68k|sgd|pco|vgm|vgz",
    "dosbox_pure": "zip|dosz|exe|com|bat|iso|chd|cue|ins|img|ima|vhd|jrc|tc|m3u|conf",
    "fbneo": "zip|cue|chd",
    "ppsspp": "elf|iso|cso|prx|pbp|chd",
    "flycast": "chd|cdi|elf|cue|gdi|lst|bin|dat|m3u",
    "bsnes": "sfc|smc|fig|swc|bs",
    "puae": "adf|adz|dms|fdi|ipf|hdf|hdz|m3u",
    "np2kai": "d88|d98|fdi|hdm|nfd|nhd|hdi|hdd|m3u",
    "dosbox_svn": "exe|com|bat|conf|iso|cue|img|ima",
    "yabause": "cue|iso|ccd|mds|chd|m3u",
    "hatari": "st|msa|stx|dim|ipf|m3u",
    "swanstation": "cue|bin|img|chd|pbp|m3u|iso",
    "mupen64plus_next": "n64|v64|z64|bin",
    "gearboy": "gb|gbc|dmg|sgb",
    "gearsystem": "sms|gg|sg|bin|rom",
    "gpsp": "gba|bin",
    "mednafen_psx": "cue|ccd|chd|toc|m3u",
    "snes9x2005": "sfc|smc|fig|swc",
    "snes9x2010": "sfc|smc|fig|swc",
    "mednafen_supafaust": "sfc|smc|fig|swc",
    "blastem": "md|bin|gen|smd",
}


def emulator_content_extensions(core_id: str) -> tuple[str, ...]:
    """Return bounded suffix hints; this never grants execution authority."""
    if not isinstance(core_id, str) or core_id not in _CORE_TARGET_GROUPS:
        _fail("unknown_core", "Core identity has no declared hardware mapping")
    return tuple("." + value for value in _CORE_CONTENT_EXTENSIONS.get(core_id, "").split("|") if value)


_TARGET_ALIASES = {
    "sms": "master_system",
    "n64": "nintendo_64",
    "gb": "game_boy",
    "gameboy": "game_boy",
    "dmg": "game_boy",
    "gba": "game_boy_advance",
    "gbc": "game_boy_color",
    "dos_pc": "dos_vga",
    "mega_drive": "genesis",
}


def canonical_targets() -> dict[str, dict[str, Any]]:
    from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

    rows = target_catalog()
    if not isinstance(rows, tuple) or not 1 <= len(rows) <= 512:
        _fail("target_registry_invalid", "Canonical Dragon hardware inventory is unavailable")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in result:
            _fail("target_registry_invalid", "Canonical hardware identities are invalid")
        result[row["id"]] = row
    return result


def _target(value: str) -> str:
    value = _text(value, "hardware target", 128).removeprefix("dragon_native:").removeprefix("emulator:")
    value = _TARGET_ALIASES.get(value, value)
    if value not in canonical_targets():
        _fail("unknown_target", "Hardware target is absent from the canonical Dragon registry")
    return value


@dataclass(frozen=True, slots=True)
class ApprovedEmulatorCore:
    registry_digest: str
    core_id: str
    library_path: str
    library_sha256: str
    architecture: str
    target_ids: tuple[str, ...]
    system_directory: str
    options_json: str
    required_bios: tuple[str, ...]
    firmware_digest: str

    def __post_init__(self):
        for field in ("registry_digest", "library_sha256", "firmware_digest"):
            if not isinstance(getattr(self, field), str) or not re.fullmatch(
                r"[0-9a-f]{64}", getattr(self, field)
            ):
                _fail("invalid_core_binding", "Approved core identity requires exact SHA256 fields")
        if self.core_id not in _CORE_TARGET_GROUPS or self.architecture not in {
            "x86",
            "x86_64",
            "arm",
            "aarch64",
            "riscv64",
        }:
            _fail("invalid_core_binding", "Approved core backend or architecture is undeclared")
        if (
            type(self.target_ids) is not tuple
            or not self.target_ids
            or len(self.target_ids) != len(set(self.target_ids))
        ):
            _fail("invalid_core_binding", "Approved core target scope must remain immutable and distinct")
        if any(target not in _CORE_TARGET_GROUPS[self.core_id] for target in self.target_ids):
            _fail("invalid_core_binding", "Approved core target scope exceeds its declared mapping")
        for value in (self.library_path, self.system_directory):
            if not Path(_text(value, "approved core path", 4096)).is_absolute():
                _fail("invalid_core_binding", "Approved core paths must be absolute")
        options = _json(_text(self.options_json, "approved core configuration", 131072).encode())
        if not isinstance(options, dict) or _canonical(options).decode() != self.options_json:
            _fail("invalid_core_binding", "Approved core configuration must retain canonical JSON")
        if type(self.required_bios) is not tuple:
            _fail("invalid_core_binding", "Approved firmware references must remain immutable")
        for name in self.required_bios:
            _content_name(name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "registry_digest": self.registry_digest,
            "core_id": self.core_id,
            "library_path": self.library_path,
            "library_sha256": self.library_sha256,
            "architecture": self.architecture,
            "target_ids": list(self.target_ids),
            "system_directory": self.system_directory,
            "options": _json(self.options_json.encode()),
            "required_bios": list(self.required_bios),
            "firmware_digest": self.firmware_digest,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]):
        fields = {
            "registry_digest",
            "core_id",
            "library_path",
            "library_sha256",
            "architecture",
            "target_ids",
            "system_directory",
            "options",
            "required_bios",
            "firmware_digest",
        }
        if (
            not isinstance(raw, dict)
            or set(raw) != fields
            or not isinstance(raw["target_ids"], list)
            or not isinstance(raw["required_bios"], list)
            or not isinstance(raw["options"], dict)
        ):
            _fail("invalid_core_binding", "Serialized approved core descriptor schema differs")
        result = cls(
            raw["registry_digest"],
            raw["core_id"],
            raw["library_path"],
            raw["library_sha256"],
            raw["architecture"],
            tuple(raw["target_ids"]),
            raw["system_directory"],
            _canonical(raw["options"]).decode(),
            tuple(raw["required_bios"]),
            raw["firmware_digest"],
        )
        if result.as_dict() != raw:
            _fail(
                "invalid_core_binding", "Serialized approved core descriptor differs from canonical identity"
            )
        return result

    def public_dict(self) -> dict[str, Any]:
        return {
            "registry_digest": self.registry_digest,
            "core_id": self.core_id,
            "library_sha256": self.library_sha256,
            "architecture": self.architecture,
            "target_ids": list(self.target_ids),
            "declared_firmware_ready": True,
            "firmware_digest": self.firmware_digest,
            "execution_checked": False,
            "commercial_rom_compatibility_verified": False,
            "content_scope": (
                "engine_specific_game_data_not_a_complete_operating_system"
                if self.core_id == "scummvm"
                else "operator_approved_hardware_mapping_requires_actual_content_admission"
            ),
        }


class GameEmulatorRegistry:
    def __init__(self, manifest_path: str | Path | None = None):
        self._environment_bound = False
        self._system_inventories: dict[str, tuple[Mapping[str, Any], ...]] = {}
        self.manifest_path = None if manifest_path is None else str(_safe_path(str(manifest_path)))
        self._raw = {"schema_version": REGISTRY_SCHEMA, "cores": []}
        if self.manifest_path is not None:
            self._raw = _json(_read_file(Path(self.manifest_path), MAX_MANIFEST_BYTES, trusted=True))
        self._validate_manifest()
        self.registry_digest = _digest(self._raw)

    @classmethod
    def from_environment(cls):
        raw = os.environ.get(REGISTRY_ENV, "").strip()
        result = cls(raw or None)
        result._environment_bound = True
        return result

    @property
    def live_manifest_digest(self) -> str:
        return self._current().registry_digest

    def _current(self):
        return (
            GameEmulatorRegistry.from_environment()
            if self._environment_bound
            else GameEmulatorRegistry(self.manifest_path)
        )

    def _validate_manifest(self):
        if (
            not isinstance(self._raw, dict)
            or set(self._raw) != {"schema_version", "cores"}
            or self._raw["schema_version"] != REGISTRY_SCHEMA
        ):
            _fail("invalid_manifest", "Operator registry must contain the exact supported schema")
        cores = self._raw["cores"]
        if not isinstance(cores, list) or len(cores) > 96:
            _fail("invalid_manifest", "Operator core registry exceeds its bounded capacity")
        seen, targets = set(), canonical_targets()
        for core in cores:
            fields = {
                "core_id",
                "approved",
                "library_path",
                "library_sha256",
                "target_ids",
                "system_directory",
                "options",
                "firmware",
            }
            if not isinstance(core, dict) or set(core) != fields or type(core["approved"]) is not bool:
                _fail("invalid_manifest", "Each core requires an exact operator approval descriptor")
            identity = _text(core["core_id"], "core identity", 80)
            if identity not in _CORE_TARGET_GROUPS or identity in seen:
                _fail("unknown_core", "Core identity must be a unique declared libretro implementation")
            seen.add(identity)
            for field in ("library_path", "system_directory"):
                _text(core[field], field, 4096)
            if not re.fullmatch(r"[0-9a-f]{64}", _text(core["library_sha256"], "library SHA256", 64)):
                _fail("invalid_manifest", "Core library requires exact SHA256")
            values = core["target_ids"]
            if (
                not isinstance(values, list)
                or not 1 <= len(values) <= 512
                or any(not isinstance(item, str) for item in values)
                or len(values) != len(set(values))
            ):
                _fail("invalid_manifest", "Core target scope must be distinct bounded canonical identities")
            if any(item not in targets or item not in _CORE_TARGET_GROUPS[identity] for item in values):
                _fail("incompatible_target_mapping", "Core approval exceeds its declared hardware mapping")
            options, firmware = core["options"], core["firmware"]
            if not isinstance(options, dict) or len(options) > 128:
                _fail("invalid_manifest", "Core configuration exceeds its bounded option schema")
            for key, value in options.items():
                _text(key, "core option key", 128)
                _text(value, "core option value", 1024)
            if not isinstance(firmware, list) or len(firmware) > 64:
                _fail("invalid_manifest", "Firmware requirements exceed their bounded schema")
            names = set()
            for item in firmware:
                if (
                    not isinstance(item, dict)
                    or set(item) != {"name", "required"}
                    or type(item["required"]) is not bool
                ):
                    _fail("invalid_manifest", "Firmware requirements must be exact names and required flags")
                name = _content_name(item["name"])
                if name.casefold() in names:
                    _fail("invalid_manifest", "Firmware requirement names cannot alias")
                names.add(name.casefold())
            bios_targets = {
                "famicom_disk_system",
                "sega_cd",
                "pc_engine_cd",
                "pc_fx",
                "ps2",
                "saturn",
                "sega_naomi",
                "sega_atom_iswave",
                "nintendo_dsi",
            }
            bios_core = identity in {
                "swanstation",
                "mednafen_psx_hw",
                "px68k",
                "freeintv",
                "gearcoleco",
                "fbneo",
            }
            if (bios_core or set(values) & bios_targets) and not any(item["required"] for item in firmware):
                _fail(
                    "firmware_declaration_required",
                    "This hardware/core scope requires explicit installed firmware requirements",
                )

    def _inspect(self, raw: dict[str, Any]) -> ApprovedEmulatorCore:
        if raw["approved"] is not True:
            _fail("core_not_approved", "This installed core is not currently operator approved")
        inspected = inspect_libretro_library(raw["library_path"])
        if inspected["library_sha256"] != raw["library_sha256"]:
            _fail("core_identity_changed", "Installed core bytes differ from the operator-approved SHA256")
        directory = _safe_path(raw["system_directory"])
        if not directory.is_dir():
            _fail("firmware_directory_unavailable", "Operator system directory is unavailable")
        requirements, fingerprints, total = [], [], 0
        present = set()
        pending = [(directory, 0)]
        directories_seen = 0
        while pending:
            folder, depth = pending.pop()
            directories_seen += 1
            if depth > 8 or directories_seen > 1024:
                _fail("firmware_limit", "Operator system directory nesting exceeds its bounded inventory")
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        _fail("unsafe_path", "Operator system assets cannot contain symbolic links")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((Path(entry.path), depth + 1))
                        if len(pending) > 1024:
                            _fail("firmware_limit", "Operator system directory exceeds its inventory bound")
                    elif entry.is_file(follow_symlinks=False):
                        name = _content_name(str(Path(entry.path).relative_to(directory)))
                        if len(present) >= 1024:
                            _fail("firmware_limit", "Operator system assets exceed their inventory bound")
                        data = _read_file(Path(entry.path), MAX_FIRMWARE_BYTES, trusted=True)
                        total += len(data)
                        if total > MAX_FIRMWARE_BYTES:
                            _fail(
                                "firmware_limit", "Operator system assets exceed their aggregate byte budget"
                            )
                        present.add(name)
                        fingerprints.append(
                            {"name": name, "present": True, "sha256": _sha(data), "size": len(data)}
                        )
                    else:
                        _fail("unsafe_path", "Operator system assets must be ordinary directories and files")
        for item in raw["firmware"]:
            name = _content_name(item["name"])
            path = directory / name
            if not path.exists():
                if item["required"]:
                    _fail("required_firmware_missing", "A declared required firmware file is not installed")
                fingerprints.append({"name": name, "present": False})
                continue
            if name not in present:
                _fail(
                    "firmware_identity_changed",
                    "Declared firmware lies outside the bounded exact system inventory",
                )
            if item["required"]:
                requirements.append(name)
        ordered = tuple(MappingProxyType(row) for row in sorted(fingerprints, key=lambda row: row["name"]))
        self._system_inventories[raw["core_id"]] = ordered
        return ApprovedEmulatorCore(
            self.registry_digest,
            raw["core_id"],
            inspected["library_path"],
            inspected["library_sha256"],
            inspected["architecture"],
            tuple(raw["target_ids"]),
            str(directory),
            _canonical(raw["options"]).decode(),
            tuple(requirements),
            _digest([dict(row) for row in ordered]),
        )

    def resolve_core(self, core_id: str) -> ApprovedEmulatorCore:
        _text(core_id, "core identity", 80)
        for raw in self._raw["cores"]:
            if raw["core_id"] == core_id:
                return self._inspect(raw)
        _fail("core_not_installed", "No approved installed core matches this identity")

    def resolve(self, target_id: str) -> ApprovedEmulatorCore:
        target = _target(target_id)
        failures = []
        for raw in self._raw["cores"]:
            if target in raw["target_ids"]:
                try:
                    return self._inspect(raw)
                except EmulatorCatalogError as exc:
                    failures.append(exc)
        if failures:
            raise failures[0]
        _fail("emulator_unavailable", "No operator-approved installed core is available for this hardware")

    def revalidate(self, binding: ApprovedEmulatorCore) -> None:
        if not isinstance(binding, ApprovedEmulatorCore):
            _fail("unissued_core_binding", "An exact approved emulator core descriptor is required")
        current = self._current().resolve_core(binding.core_id)
        if current != binding:
            _fail(
                "core_authority_changed", "Operator approval, configuration, firmware or core bytes changed"
            )

    def validate_active(self, binding: ApprovedEmulatorCore | Mapping[str, Any]) -> None:
        self.revalidate(ApprovedEmulatorCore.from_dict(binding) if isinstance(binding, Mapping) else binding)

    def system_inventory(self, binding: ApprovedEmulatorCore) -> tuple[Mapping[str, Any], ...]:
        if not isinstance(binding, ApprovedEmulatorCore):
            _fail(
                "invalid_core_binding", "Exact approved core descriptor is required for its system inventory"
            )
        current = self._current()
        if current.resolve_core(binding.core_id) != binding:
            _fail("core_authority_changed", "Current system inventory does not match the approved binding")
        return current._system_inventories[binding.core_id]

    def catalog(self) -> list[dict[str, Any]]:
        available, failures = {}, {}
        for raw in self._raw["cores"]:
            try:
                available[raw["core_id"]] = self._inspect(raw)
            except EmulatorCatalogError as exc:
                failures[raw["core_id"]] = exc
        rows = []
        for target, metadata in canonical_targets().items():
            candidates = [identity for identity, values in _CORE_TARGET_GROUPS.items() if target in values]
            selected = next(
                (value for identity, value in available.items() if target in value.target_ids), None
            )
            failed = next(
                (
                    failures[raw["core_id"]]
                    for raw in self._raw["cores"]
                    if target in raw["target_ids"] and raw["core_id"] in failures
                ),
                None,
            )
            code = (
                "operator_approved_installation"
                if selected
                else (
                    failed.code
                    if failed
                    else "core_installation_required" if candidates else "external_adapter_unimplemented"
                )
            )
            message = (
                "Installed approved core and declared firmware are ready; actual content compatibility is checked by the isolated host"
                if selected
                else (
                    failed.message
                    if failed
                    else (
                        "Install and explicitly approve a compatible libretro core and its legitimate firmware"
                        if candidates
                        else "No installed emulator adapter is declared for this hardware; native source/toolchain requirements remain separate"
                    )
                )
            )
            rows.append(
                {
                    "target_id": target,
                    "label": metadata["family"] + " · " + target,
                    "candidate_core_ids": candidates,
                    "available": selected is not None,
                    "core": selected.public_dict() if selected else None,
                    "readiness": {"code": code, "message": message, "execution_checked": False},
                    "hardware_compatibility_verified": False,
                }
            )
        return rows


def _content_name(value: Any) -> str:
    value = _text(value, "content filename", 240)
    if unicodedata.normalize("NFC", value) != value:
        _fail("unsafe_content_path", "Content filenames require exact canonical NFC spelling")
    if (
        "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        _fail("unsafe_content_path", "Content filenames must be exact safe relative paths")
    return value


@dataclass(frozen=True, slots=True)
class GameContentReference:
    name: str
    size_bytes: int
    sha256: str
    artifact_ref: str
    prefix: bytes = b""

    def __post_init__(self):
        if _content_name(self.name) != self.name:
            _fail("unsafe_content_path", "Referenced artifact filename must retain exact canonical spelling")
        if type(self.size_bytes) is not int or not 1 <= self.size_bytes <= MAX_REFERENCED_FILE_BYTES:
            _fail("content_limit", "Referenced artifact size exceeds its per-file budget")
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            _fail("invalid_content", "Referenced artifact requires exact SHA256")
        _text(self.artifact_ref, "governed artifact reference", 2048)
        if type(self.prefix) is not bytes or len(self.prefix) > min(self.size_bytes, 65536):
            _fail("invalid_content", "Referenced artifact prefix exceeds its bounded actual-byte span")
        if PurePosixPath(self.name).suffix.casefold() in {".cue", ".gdi", ".m3u"} and (
            self.size_bytes != len(self.prefix) or _sha(self.prefix) != self.sha256
        ):
            _fail(
                "invalid_disc_descriptor",
                "Referenced disc descriptors require their complete digest-verified bounded text",
            )

    def as_dict(self):
        return {
            "name": self.name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "artifact_ref": self.artifact_ref,
            "prefix_hex": self.prefix.hex(),
        }


def _content_head(value: bytes | GameContentReference) -> bytes:
    return value.prefix if isinstance(value, GameContentReference) else value


def _content_size(value: bytes | GameContentReference) -> int:
    return value.size_bytes if isinstance(value, GameContentReference) else len(value)


@dataclass(frozen=True, slots=True)
class GameContentBundle:
    entrypoint: str
    files: Mapping[str, bytes | GameContentReference]
    source_digest: str

    def __post_init__(self):
        if not isinstance(self.files, Mapping) or not 1 <= len(self.files) <= MAX_CONTENT_FILES:
            _fail("content_limit", "Game content files exceed their bounded count")
        clean, seen, total, inline_total, prefix_total = {}, set(), 0, 0, 0
        for key, value in self.files.items():
            name = _content_name(key)
            if (
                name != key
                or name.casefold() in seen
                or not (
                    type(value) is bytes
                    and value
                    or isinstance(value, GameContentReference)
                    and value.name == name
                )
            ):
                _fail("invalid_content", "Content requires exact nonempty bytes and nonaliased filenames")
            total += _content_size(value)
            if type(value) is bytes:
                inline_total += len(value)
            else:
                prefix_total += len(value.prefix)
            if (
                total > MAX_REFERENCED_BUNDLE_BYTES
                or inline_total > MAX_CONTENT_BYTES
                or prefix_total > MAX_CONTENT_PREFIX_BYTES
            ):
                _fail("content_limit", "Expanded game content exceeds its byte budget")
            seen.add(name.casefold())
            clean[name] = value
        entry = _content_name(self.entrypoint)
        if (
            entry not in clean
            or not isinstance(self.source_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.source_digest)
        ):
            _fail("invalid_content", "Exact content entrypoint and source digest are required")
        object.__setattr__(self, "files", MappingProxyType(dict(sorted(clean.items()))))
        directories = {}
        for name in clean:
            parents = PurePosixPath(name).parents
            if len(parents) > 9:
                _fail("content_limit", "Content directory nesting exceeds its bounded depth")
            for parent in parents:
                if str(parent) == ".":
                    continue
                alias = str(parent).casefold()
                if alias in seen or alias in directories and directories[alias] != str(parent):
                    _fail(
                        "invalid_content",
                        "Content files and directories contain conflicting normalized paths",
                    )
                directories[alias] = str(parent)
                if len(directories) > 96:
                    _fail("content_limit", "Content directory count exceeds its bounded inventory")
        _validate_dependencies(self.entrypoint, self.files)

    @property
    def bundle_digest(self) -> str:
        return _digest(self._descriptor())

    def _descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": CONTENT_SCHEMA,
            "entrypoint": self.entrypoint,
            "source_digest": self.source_digest,
            "files": [
                (
                    data.as_dict()
                    if isinstance(data, GameContentReference)
                    else {"name": name, "sha256": _sha(data), "size_bytes": len(data)}
                )
                for name, data in self.files.items()
            ],
        }

    def as_dict(self) -> dict[str, Any]:
        result = self._descriptor()
        result["bundle_digest"] = _digest(result)
        return result

    @classmethod
    def from_descriptor(cls, raw: Mapping[str, Any], *, inline_files: Mapping[str, bytes] | None = None):
        if (
            not isinstance(raw, dict)
            or set(raw) != {"schema_version", "entrypoint", "source_digest", "files", "bundle_digest"}
            or raw["schema_version"] != CONTENT_SCHEMA
        ):
            _fail("invalid_content", "Content descriptor requires its exact supported schema")
        rows = raw["files"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CONTENT_FILES:
            _fail("content_limit", "Content descriptor exceeds its bounded file count")
        files = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) not in (
                {"name", "size_bytes", "sha256"},
                {"name", "size_bytes", "sha256", "artifact_ref", "prefix_hex"},
            ):
                _fail("invalid_content", "Content file descriptor schema is invalid")
            name = _content_name(row["name"])
            if name in files:
                _fail("invalid_content", "Content descriptor repeats an exact filename")
            if "artifact_ref" in row:
                prefix = row["prefix_hex"]
                if (
                    not isinstance(prefix, str)
                    or len(prefix) > 131072
                    or not re.fullmatch(r"(?:[0-9a-f]{2})*", prefix)
                ):
                    _fail("invalid_content", "Content prefix encoding is invalid")
                files[name] = GameContentReference(
                    name, row["size_bytes"], row["sha256"], row["artifact_ref"], bytes.fromhex(prefix)
                )
            else:
                data = (inline_files or {}).get(name)
                if type(data) is not bytes or len(data) != row["size_bytes"] or _sha(data) != row["sha256"]:
                    _fail(
                        "content_bytes_required",
                        "Inline content descriptor requires its exact admitted bytes",
                    )
                files[name] = data
        result = cls(raw["entrypoint"], files, raw["source_digest"])
        if result.as_dict() != raw:
            _fail("content_identity_changed", "Content descriptor digest or canonical file order differs")
        return result

    def materialize_private(
        self, root: str | Path, reader: Callable[[GameContentReference], Iterable[bytes]] | None = None
    ) -> Path:
        """Write exact streamed artifacts into a host-owned empty private root.

        ``reader`` is the application's current-rights artifact reader, never
        an untrusted URI fetcher. Successful files are complete and verified
        before any core is allowed to load the returned entrypoint.
        """
        directory = _safe_path(str(root))
        details = directory.stat()
        if (
            not directory.is_dir()
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o077
            or any(directory.iterdir())
        ):
            _fail("unsafe_content_root", "Materialization requires an empty private host-owned directory")
        written, folders, aggregate_chunks = [], [], 0
        try:
            for name, source in self.files.items():
                destination = directory / name
                for folder in reversed(destination.parent.relative_to(directory).parents):
                    candidate = directory / folder
                    if candidate != directory and not candidate.exists():
                        candidate.mkdir(mode=0o700)
                        folders.append(candidate)
                if not destination.parent.exists():
                    destination.parent.mkdir(mode=0o700)
                    folders.append(destination.parent)
                if isinstance(source, GameContentReference):
                    if reader is None:
                        _fail(
                            "content_reader_required",
                            "Referenced artifacts require their current-authority application reader",
                        )
                    chunks, expected, expected_size = reader(source), source.sha256, source.size_bytes
                    prefix = source.prefix
                else:
                    chunks = (
                        source[pos : pos + MAX_STREAM_CHUNK_BYTES]
                        for pos in range(0, len(source), MAX_STREAM_CHUNK_BYTES)
                    )
                    expected, expected_size, prefix = _sha(source), len(source), b""
                descriptor = os.open(
                    destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
                )
                written.append(destination)
                digest, size, observed_prefix, chunk_count = hashlib.sha256(), 0, bytearray(), 0
                with os.fdopen(descriptor, "wb") as stream:
                    for chunk in chunks:
                        chunk_count += 1
                        aggregate_chunks += 1
                        if (
                            type(chunk) is not bytes
                            or not 1 <= len(chunk) <= MAX_STREAM_CHUNK_BYTES
                            or chunk_count > min(expected_size, 131072)
                            or aggregate_chunks > 262144
                        ):
                            _fail(
                                "content_stream_invalid",
                                "Artifact reader must provide bounded nonempty exact-byte chunks",
                            )
                        size += len(chunk)
                        if size > expected_size:
                            _fail(
                                "content_identity_changed",
                                "Artifact reader exceeded the exact admitted byte length",
                            )
                        if len(observed_prefix) < len(prefix):
                            observed_prefix.extend(chunk[: len(prefix) - len(observed_prefix)])
                        digest.update(chunk)
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                if (
                    size != expected_size
                    or digest.hexdigest() != expected
                    or bytes(observed_prefix) != prefix
                ):
                    _fail(
                        "content_identity_changed",
                        "Streamed artifact differs from its admitted size, SHA256 or actual prefix",
                    )
            return directory / self.entrypoint
        except BaseException:
            for path in reversed(written):
                path.unlink(missing_ok=True)
            for path in reversed(folders):
                path.rmdir()
            raise


ContentBundle = GameContentBundle


def _relative_reference(owner: str, reference: str, files: Mapping[str, bytes | GameContentReference]) -> str:
    reference = _content_name(reference)
    path = str(PurePosixPath(owner).parent / reference)
    if path not in files:
        _fail("missing_disc_dependency", "Disc descriptor references a file absent from the exact bundle")
    return path


def _descriptor_text(data: bytes) -> str:
    if len(data) > 65536:
        _fail("disc_descriptor_limit", "Disc descriptor exceeds its byte budget")
    try:
        value = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise EmulatorCatalogError(
            "invalid_disc_descriptor", "Disc descriptors must be actual UTF-8 text"
        ) from exc
    if "\x00" in value or len(value.splitlines()) > 4096:
        _fail("invalid_disc_descriptor", "Disc descriptor text is malformed or exceeds its line budget")
    return value


def _validate_dependencies(entry: str, files: Mapping[str, bytes | GameContentReference]) -> None:
    visited, pending = set(), [(entry, 0)]
    while pending:
        name, depth = pending.pop()
        if depth > 8:
            _fail("disc_descriptor_limit", "Disc dependency nesting exceeds its bounded depth")
        if name in visited:
            continue
        visited.add(name)
        data, extension = _content_head(files[name]), PurePosixPath(name).suffix.casefold()
        references = []
        if extension == ".m3u":
            for line in _descriptor_text(data).splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if PurePosixPath(line).suffix.casefold() == ".m3u":
                    _fail("invalid_disc_playlist", "Nested disc playlists are not admitted")
                references.append(_relative_reference(name, line, files))
            if not 1 <= len(references) <= 32 or len(references) != len(set(references)):
                _fail("invalid_disc_playlist", "Disc playlists require 1..32 distinct exact relative files")
        elif extension == ".cue":
            text = _descriptor_text(data)
            tracks = 0
            for line in text.splitlines():
                match = re.fullmatch(
                    r'\s*FILE\s+(?:"([^"\r\n]+)"|(\S+))\s+(BINARY|MOTOROLA|WAVE|AIFF|MP3)\s*',
                    line,
                    re.IGNORECASE,
                )
                if match:
                    references.append(_relative_reference(name, match.group(1) or match.group(2), files))
                elif re.match(r"\s*CDTEXTFILE\b", line, re.IGNORECASE):
                    text_file = re.fullmatch(
                        r'\s*CDTEXTFILE\s+(?:"([^"\r\n]+)"|(\S+))\s*', line, re.IGNORECASE
                    )
                    if text_file is None:
                        _fail("invalid_disc_descriptor", "CUE CDTEXT file reference is malformed")
                    references.append(
                        _relative_reference(name, text_file.group(1) or text_file.group(2), files)
                    )
                elif re.match(r"\s*FILE\b", line, re.IGNORECASE):
                    _fail("invalid_disc_descriptor", "CUE file reference syntax is invalid")
                elif re.match(r"\s*TRACK\s+\d{1,2}\s+", line, re.IGNORECASE):
                    tracks += 1
            if not references or not 1 <= tracks <= 99 or len(references) > 96:
                _fail("invalid_disc_descriptor", "CUE requires actual track and file descriptors")
        elif extension == ".gdi":
            lines = [line.strip() for line in _descriptor_text(data).splitlines() if line.strip()]
            if (
                not lines
                or not re.fullmatch(r"\d{1,2}", lines[0])
                or not 1 <= int(lines[0]) <= 99
                or len(lines) != int(lines[0]) + 1
            ):
                _fail("invalid_disc_descriptor", "GDI track count differs from its exact descriptor")
            for index, line in enumerate(lines[1:], 1):
                match = re.fullmatch(
                    r'(\d{1,2})\s+(\d{1,10})\s+(\d{1,2})\s+(2352|2048)\s+(?:"([^"\r\n]+)"|(\S+))\s+(\d{1,10})',
                    line,
                )
                if match is None or int(match.group(1)) != index:
                    _fail("invalid_disc_descriptor", "GDI track descriptor is invalid")
                target = _relative_reference(name, match.group(5) or match.group(6), files)
                if int(match.group(7)) >= _content_size(files[target]):
                    _fail("invalid_disc_descriptor", "GDI track offset exceeds actual supplied bytes")
                references.append(target)
        elif extension == ".chd":
            if len(data) < 16 or data[:8] != b"MComprHD":
                _fail("invalid_chd", "CHD container magic/header is missing")
            length, version = struct.unpack_from(">II", data, 8)
            if version not in {3, 4, 5} or length != {3: 120, 4: 108, 5: 124}[version] or len(data) < length:
                _fail("invalid_chd", "CHD structural header/version is unsupported or truncated")
        elif extension == ".iso":
            if len(data) < 17 * 2048 or data[32769:32774] != b"CD001" or data[32774] != 1:
                _fail("invalid_iso", "ISO9660 volume descriptor is missing from actual image bytes")
        for target in references:
            if target == name:
                _fail("invalid_disc_descriptor", "A disc descriptor cannot reference itself")
            pending.append((target, depth + 1))


def load_game_content(
    data: bytes, filename: str, *, entrypoint: str | None = None, expected_source_digest: str | None = None
) -> GameContentBundle:
    if type(data) is not bytes or not 1 <= len(data) <= MAX_CONTENT_BYTES:
        _fail("content_limit", "Exact game source bytes exceed their bounded upload size")
    filename = _content_name(filename)
    if "/" in filename:
        _fail("unsafe_content_path", "Uploaded content filename must be a basename")
    actual = _sha(data)
    if expected_source_digest is not None and expected_source_digest != actual:
        _fail("content_identity_changed", "Game content differs from the admitted source digest")
    files = {}
    if filename.casefold().endswith(".zip") or data.startswith(b"PK\x03\x04"):
        from .game_learning_ingestion import GameIngestionError, _preflight_zip

        try:
            _preflight_zip(data)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                total, seen = 0, set()
                for member in archive.infolist():
                    name = _content_name(member.filename.rstrip("/"))
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode) or member.flag_bits & 1 or name.casefold() in seen:
                        _fail(
                            "unsafe_archive",
                            "Content archives cannot contain symlinks, encryption or path aliases",
                        )
                    seen.add(name.casefold())
                    if member.is_dir():
                        continue
                    if PurePosixPath(name).suffix.casefold() in {
                        ".zip",
                        ".7z",
                        ".rar",
                        ".tar",
                        ".gz",
                        ".bz2",
                        ".xz",
                    }:
                        _fail("unsafe_archive", "Nested content archives are not admitted")
                    total += member.file_size
                    if (
                        member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                        or not 1 <= member.file_size <= MAX_CONTENT_BYTES
                        or total > MAX_CONTENT_BYTES
                        or member.file_size > max(1, member.compress_size) * 100
                    ):
                        _fail("content_limit", "Archive expansion exceeds its bounded content budget")
                    with archive.open(member) as stream:
                        body = stream.read(member.file_size + 1)
                    if len(body) != member.file_size:
                        _fail("invalid_archive", "Archive member differs from its actual declared bytes")
                    files[name] = body
        except EmulatorCatalogError:
            raise
        except (GameIngestionError, zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise EmulatorCatalogError(
                "invalid_archive", "Game content requires a valid bounded classic ZIP"
            ) from exc
        if entrypoint is None:
            candidates = [name for name in files if PurePosixPath(name).suffix.casefold() == ".m3u"]
            if not candidates:
                candidates = [
                    name
                    for name in files
                    if PurePosixPath(name).suffix.casefold() in {".cue", ".gdi", ".chd", ".iso"}
                ]
            if not candidates and len(files) == 1:
                candidates = list(files)
            if len(candidates) != 1:
                _fail(
                    "content_entrypoint_required", "Multi-file content requires one explicit exact entrypoint"
                )
            entrypoint = candidates[0]
    else:
        files[filename] = data
        if entrypoint is not None and entrypoint != filename:
            _fail("invalid_content", "Single-file content entrypoint must retain its exact filename")
        entrypoint = filename
    return GameContentBundle(entrypoint, files, actual)


def load_game_content_for_core(
    core: ApprovedEmulatorCore,
    data: bytes,
    filename: str,
    *,
    entrypoint: str | None = None,
    expected_source_digest: str | None = None,
    registry: GameEmulatorRegistry | None = None,
) -> GameContentBundle:
    """Keep native DOS/arcade ZIPs intact after bounded actual archive inspection.

    The worker must also verify its actual ``block_extract`` declaration. This
    source admission does not infer game compatibility or execute archived code.
    """
    (registry or GameEmulatorRegistry.from_environment()).revalidate(core)
    if core.core_id not in {"dosbox_pure", "fbneo"}:
        return load_game_content(
            data, filename, entrypoint=entrypoint, expected_source_digest=expected_source_digest
        )
    if type(data) is not bytes or not 1 <= len(data) <= MAX_CONTENT_BYTES:
        _fail("content_limit", "Exact game source bytes exceed their bounded upload size")
    filename = _content_name(filename)
    if "/" in filename:
        _fail("unsafe_content_path", "Uploaded content filename must be a basename")
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix != ".zip" and not (core.core_id == "dosbox_pure" and suffix == ".dosz"):
        return load_game_content(
            data, filename, entrypoint=entrypoint, expected_source_digest=expected_source_digest
        )
    actual = _sha(data)
    if expected_source_digest is not None and expected_source_digest != actual:
        _fail("content_identity_changed", "Game content differs from the admitted source digest")
    if entrypoint is not None and entrypoint != filename:
        _fail("invalid_content", "Opaque native archive entrypoint must retain its exact filename")
    from .game_learning_ingestion import GameIngestionError, _preflight_zip

    try:
        _preflight_zip(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > MAX_CONTENT_FILES:
                _fail("content_limit", "Native archive member count exceeds its bounded inventory")
            seen, directories, files, total = set(), {}, set(), 0
            for member in members:
                name = _content_name(member.filename.rstrip("/"))
                alias, mode = name.casefold(), member.external_attr >> 16
                if (
                    alias in seen
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or member.flag_bits & 1
                ):
                    _fail("unsafe_archive", "Native archives cannot contain aliases, symlinks or encryption")
                seen.add(alias)
                if len(PurePosixPath(name).parents) > 9:
                    _fail("content_limit", "Native archive directory nesting exceeds its bounded depth")
                for parent in PurePosixPath(name).parents:
                    if str(parent) != ".":
                        normalized = str(parent).casefold()
                        if normalized in directories and directories[normalized] != str(parent):
                            _fail("unsafe_archive", "Native archive directories contain normalized aliases")
                        directories[normalized] = str(parent)
                if member.is_dir():
                    if alias in directories and directories[alias] != name:
                        _fail("unsafe_archive", "Native archive directories contain normalized aliases")
                    directories[alias] = name
                    continue
                files.add(alias)
                if PurePosixPath(name).suffix.casefold() in {
                    ".zip",
                    ".7z",
                    ".rar",
                    ".tar",
                    ".gz",
                    ".bz2",
                    ".xz",
                }:
                    _fail("unsafe_archive", "Nested native archives are not admitted")
                total += member.file_size
                if (
                    member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or not 1 <= member.file_size <= MAX_CONTENT_BYTES
                    or total > MAX_CONTENT_BYTES
                    or member.file_size > max(1, member.compress_size) * 100
                ):
                    _fail("content_limit", "Native archive expansion exceeds its bounded byte budget")
                observed = 0
                with archive.open(member) as stream:
                    while chunk := stream.read(min(65536, member.file_size - observed + 1)):
                        observed += len(chunk)
                        if observed > member.file_size:
                            _fail("invalid_archive", "Native archive member exceeds its exact declared bytes")
                if observed != member.file_size:
                    _fail("invalid_archive", "Native archive member differs from its exact declared bytes")
            if not files or files.intersection(directories) or len(directories) > 96:
                _fail("unsafe_archive", "Native archive file/directory inventory is conflicting or exhausted")
    except EmulatorCatalogError:
        raise
    except (GameIngestionError, zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise EmulatorCatalogError(
            "invalid_archive", "Native content requires a valid bounded classic ZIP"
        ) from exc
    return GameContentBundle(filename, {filename: data}, actual)


def _write_manifest(path: Path, raw: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _safe_path(str(path.parent))
    if path.exists():
        _read_file(path, MAX_MANIFEST_BYTES, trusted=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".game-emulators-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(raw) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _operator_registry_lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _safe_path(str(path.parent))
    lock_path = path.with_name(path.name + ".lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid not in {0, os.geteuid()}
            or details.st_mode & 0o022
        ):
            _fail(
                "unsafe_registry_lock", "Operator registry update lock must be a trusted private regular file"
            )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    approve = commands.add_parser("approve")
    approve.add_argument("--core-id", required=True, choices=sorted(_CORE_TARGET_GROUPS))
    approve.add_argument("--library", type=Path, required=True)
    approve.add_argument("--target", action="append", required=True)
    approve.add_argument("--system-directory", type=Path, required=True)
    approve.add_argument("--firmware", action="append", default=[])
    approve.add_argument("--optional-firmware", action="append", default=[])
    approve.add_argument("--option", action="append", default=[])
    approve.add_argument(
        "--defer-approval",
        action="store_true",
        help="Record an inspected inactive candidate without granting execution",
    )
    remove = commands.add_parser("remove")
    remove.add_argument("--core-id", required=True)
    args = parser.parse_args(argv)
    try:
        path = args.registry or (Path(os.environ[REGISTRY_ENV]) if os.environ.get(REGISTRY_ENV) else None)
        if args.command == "catalog":
            registry = GameEmulatorRegistry(path)
            print(
                json.dumps(
                    {"registry_digest": registry.registry_digest, "targets": registry.catalog()}, indent=2
                )
            )
            return 0
        if path is None or not path.is_absolute():
            _fail(
                "registry_path_required", "Operator configuration requires an explicit absolute registry path"
            )
        with _operator_registry_lock(path):
            raw = (
                GameEmulatorRegistry(path)._raw
                if path.exists()
                else {"schema_version": REGISTRY_SCHEMA, "cores": []}
            )
            raw["cores"] = [row for row in raw["cores"] if row["core_id"] != args.core_id]
            if args.command == "approve":
                inspected = inspect_libretro_library(args.library.resolve(strict=True))
                directory = args.system_directory.resolve(strict=True)
                if not directory.is_dir():
                    _fail("firmware_directory_unavailable", "Operator system directory must already exist")
                options = {}
                for item in args.option:
                    if "=" not in item:
                        _fail("invalid_option", "Core options use exact KEY=VALUE syntax")
                    key, value = item.split("=", 1)
                    if key in options:
                        _fail("invalid_option", "Core configuration keys cannot be repeated")
                    options[key] = value
                raw["cores"].append(
                    {
                        "core_id": args.core_id,
                        "approved": not args.defer_approval,
                        "library_path": inspected["library_path"],
                        "library_sha256": inspected["library_sha256"],
                        "target_ids": [_target(value) for value in args.target],
                        "system_directory": str(directory),
                        "options": options,
                        "firmware": [{"name": value, "required": True} for value in args.firmware]
                        + [{"name": value, "required": False} for value in args.optional_firmware],
                    }
                )
            temporary = GameEmulatorRegistry()
            temporary._raw = raw
            temporary._validate_manifest()
            temporary.registry_digest = _digest(raw)
            if args.command == "approve" and not args.defer_approval:
                temporary.resolve_core(args.core_id)
            _write_manifest(path, raw)
        print(
            json.dumps(
                {
                    "status": "operator_registry_updated",
                    "registry_digest": _digest(raw),
                    "core_id": args.core_id,
                    "execution_checked": False,
                }
            )
        )
        return 0
    except (EmulatorCatalogError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": getattr(exc, "code", "installation_unavailable"),
                    "message": str(exc),
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
