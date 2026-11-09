"""Vendor-neutral system-memory topology for AI context retention."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ctypes
import os
from pathlib import Path
import platform
import re
import struct
from typing import Iterable

_MIB = 1024 * 1024
_TECH = re.compile(
    r"(?<![A-Z0-9])(?P<family>LPDDR|GDDR|DDR|HBM)"
    r"(?P<generation>\d+)?(?P<variant>[A-Z][A-Z0-9+]*)?(?![A-Z0-9])",
    re.I,
)
_SMBIOS_TYPES = {
    0x03: "DRAM", 0x04: "EDRAM", 0x07: "RAM", 0x0F: "SDRAM",
    0x11: "RDRAM", 0x12: "DDR", 0x13: "DDR2", 0x18: "DDR3",
    0x1A: "DDR4", 0x1B: "LPDDR", 0x1C: "LPDDR2", 0x1D: "LPDDR3",
    0x1E: "LPDDR4", 0x20: "HBM", 0x21: "HBM2", 0x22: "DDR5",
    0x23: "LPDDR5", 0x24: "HBM3",
}
_FORM = {
    0x03: "SIMM", 0x05: "Chip", 0x09: "DIMM", 0x0B: "Row Of Chips",
    0x0D: "SODIMM", 0x0F: "FB-DIMM", 0x10: "Die",
}
_SYSTEM = frozenset({"DRAM", "EDRAM", "RAM", "SDRAM", "RDRAM", "DDR", "LPDDR", "HBM", "CXL"})


class MemoryAttachment(str, Enum):
    MODULE = "module"
    BOARD = "board"
    PACKAGE = "package"
    CXL = "cxl"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MemoryTechnology:
    raw: str
    family: str
    generation: int | None = None
    variant: str = ""

    @property
    def canonical(self) -> str:
        if self.family in {"DDR", "LPDDR", "GDDR", "HBM"}:
            return f"{self.family}{self.generation or ''}{self.variant}"
        return self.family


@dataclass(frozen=True, slots=True)
class MemoryDevice:
    technology: MemoryTechnology
    capacity_bytes: int | None = None
    locator: str = ""
    form_factor: str = ""
    attachment: MemoryAttachment = MemoryAttachment.UNKNOWN
    source: str = "unknown"
    system_addressable: bool = True


@dataclass(frozen=True, slots=True)
class MemoryTopology:
    total_bytes: int
    available_bytes: int
    devices: tuple[MemoryDevice, ...] = ()
    platform_system: str = ""
    platform_machine: str = ""

    @property
    def recognized_devices(self) -> tuple[MemoryDevice, ...]:
        return tuple(
            d for d in self.devices
            if d.system_addressable and d.technology.family in _SYSTEM
        )

    @property
    def has_memory_silicon(self) -> bool:
        return bool(self.recognized_devices)

    @property
    def has_board_memory(self) -> bool:
        return any(
            d.attachment in {MemoryAttachment.BOARD, MemoryAttachment.PACKAGE}
            for d in self.recognized_devices
        )

    @property
    def has_high_bandwidth_memory(self) -> bool:
        return any(d.technology.family == "HBM" for d in self.recognized_devices)

    @property
    def technologies(self) -> tuple[str, ...]:
        return tuple(sorted({d.technology.canonical for d in self.recognized_devices}))


def parse_memory_technology(raw: str) -> MemoryTechnology:
    """Parse DDR/LPDDR/HBM generations without a generation allowlist."""
    if not isinstance(raw, str):
        raise TypeError("memory technology must be text")
    value = raw.strip().upper().replace("_", " ")
    match = _TECH.search(value)
    if match:
        generation = match.group("generation")
        return MemoryTechnology(
            raw=raw,
            family=match.group("family").upper(),
            generation=int(generation) if generation else None,
            variant=(match.group("variant") or "").upper(),
        )
    for name in ("SDRAM", "RDRAM", "EDRAM", "DRAM"):
        if name in value:
            return MemoryTechnology(raw, name)
    if "CXL" in value:
        return MemoryTechnology(raw, "CXL")
    if value in {"RAM", "SYSTEM RAM", "SYSTEM MEMORY"}:
        return MemoryTechnology(raw, "RAM")
    return MemoryTechnology(raw, "UNKNOWN")


def _attachment(tech: MemoryTechnology, form: str, locator: str) -> MemoryAttachment:
    form = form.upper()
    locator = locator.upper()
    if tech.family == "CXL" or locator.startswith("CXL"):
        return MemoryAttachment.CXL
    if tech.family == "HBM" or form == "DIE":
        return MemoryAttachment.PACKAGE
    if form in {"CHIP", "ROW OF CHIPS"} or "SOLDER" in locator or "ONBOARD" in locator:
        return MemoryAttachment.BOARD
    if form in {"DIMM", "SODIMM", "FB-DIMM", "SIMM"}:
        return MemoryAttachment.MODULE
    return MemoryAttachment.SYSTEM if tech.family in _SYSTEM else MemoryAttachment.UNKNOWN


def _dmi_structures(blob: bytes) -> Iterable[tuple[int, bytes, tuple[str, ...]]]:
    offset = 0
    while offset + 4 <= len(blob):
        kind, length = blob[offset], blob[offset + 1]
        if length < 4 or offset + length > len(blob):
            return
        formatted = blob[offset:offset + length]
        cursor = offset + length
        strings: list[str] = []
        while cursor < len(blob):
            end = blob.find(b"\0", cursor)
            if end < 0:
                return
            if end == cursor:
                cursor += 1
                if cursor < len(blob) and blob[cursor] == 0:
                    cursor += 1
                break
            strings.append(blob[cursor:end].decode("utf-8", errors="replace"))
            cursor = end + 1
            if cursor < len(blob) and blob[cursor] == 0:
                cursor += 1
                break
        yield kind, formatted, tuple(strings)
        offset = cursor
        if kind == 127:
            return


def _smbios_string(strings: tuple[str, ...], index: int) -> str:
    return strings[index - 1] if 0 < index <= len(strings) else ""


def parse_smbios_memory_devices(blob: bytes) -> tuple[MemoryDevice, ...]:
    devices: list[MemoryDevice] = []
    for kind, data, strings in _dmi_structures(bytes(blob)):
        if kind != 17 or len(data) <= 0x12:
            continue
        type_code = data[0x12]
        raw_type = _SMBIOS_TYPES.get(type_code)
        technology = (
            parse_memory_technology(raw_type)
            if raw_type is not None
            else MemoryTechnology(f"SMBIOS-0x{type_code:02X}", "RAM")
        )
        size = struct.unpack_from("<H", data, 0x0C)[0]
        if size in {0, 0xFFFF}:
            continue
        if size == 0x7FFF and len(data) >= 0x20:
            capacity = struct.unpack_from("<I", data, 0x1C)[0] * _MIB
        else:
            capacity = (size & 0x7FFF) * (1024 if size & 0x8000 else _MIB)
        form = _FORM.get(data[0x0E], "Unknown") if len(data) > 0x0E else "Unknown"
        locator = _smbios_string(strings, data[0x10] if len(data) > 0x10 else 0)
        devices.append(
            MemoryDevice(
                technology=technology,
                capacity_bytes=capacity,
                locator=locator,
                form_factor=form,
                attachment=_attachment(technology, form, locator),
                source="smbios",
            )
        )
    return tuple(devices)


def _portable_capacity() -> tuple[int, int]:
    try:
        page = int(os.sysconf("SC_PAGE_SIZE"))
        total = page * int(os.sysconf("SC_PHYS_PAGES"))
        available = page * int(os.sysconf("SC_AVPHYS_PAGES"))
        return total, min(total, available or total // 2)
    except (AttributeError, OSError, ValueError):
        return 0, 0


def _linux_capacity(path: Path) -> tuple[int, int]:
    try:
        values = {}
        for line in path.read_text(encoding="ascii", errors="replace").splitlines():
            if ":" in line:
                key, raw = line.split(":", 1)
                fields = raw.split()
                if fields:
                    values[key] = int(fields[0]) * (1024 if len(fields) > 1 else 1)
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
        return total, min(total, available)
    except (OSError, ValueError):
        return 0, 0


def _windows_capacity() -> tuple[int, int]:
    class Status(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
            ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
            ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
            ("virt_total", ctypes.c_ulonglong), ("virt_available", ctypes.c_ulonglong),
            ("extended", ctypes.c_ulonglong),
        ]
    try:
        status = Status()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total), int(status.available)
    except (AttributeError, OSError):
        pass
    return 0, 0


def _windows_smbios() -> tuple[MemoryDevice, ...]:
    try:
        getter = ctypes.windll.kernel32.GetSystemFirmwareTable
        provider = struct.unpack("<I", b"RSMB")[0]
        size = int(getter(provider, 0, None, 0))
        if not 8 < size <= 64 * _MIB:
            return ()
        buffer = ctypes.create_string_buffer(size)
        written = int(getter(provider, 0, buffer, size))
        raw = bytes(buffer.raw[:written])
        length = struct.unpack_from("<I", raw, 4)[0]
        return parse_smbios_memory_devices(raw[8:8 + length])
    except (AttributeError, OSError, ValueError, struct.error):
        return ()


class SystemMemoryProbe:
    """Discover OS-addressable capacity and available physical-memory topology."""

    def __init__(
        self,
        *,
        meminfo_path: Path = Path("/proc/meminfo"),
        dmi_path: Path = Path("/sys/firmware/dmi/tables/DMI"),
        cxl_root: Path = Path("/sys/bus/cxl/devices"),
    ) -> None:
        self.meminfo_path, self.dmi_path, self.cxl_root = meminfo_path, dmi_path, cxl_root

    def capacity_snapshot(self) -> tuple[int, int]:
        system = platform.system().lower()
        if system == "linux":
            total, available = _linux_capacity(self.meminfo_path)
        elif system == "windows":
            total, available = _windows_capacity()
        else:
            total, available = _portable_capacity()
        return (total, available) if total else _portable_capacity()

    def probe(self) -> MemoryTopology:
        total, available = self.capacity_snapshot()
        system = platform.system()
        devices: list[MemoryDevice] = []
        if system.lower() == "linux":
            try:
                devices.extend(parse_smbios_memory_devices(self.dmi_path.read_bytes()))
            except OSError:
                pass
            try:
                for path in sorted(self.cxl_root.glob("mem*")):
                    devices.append(
                        MemoryDevice(
                            parse_memory_technology("CXL"),
                            locator=path.name,
                            attachment=MemoryAttachment.CXL,
                            source="cxl",
                        )
                    )
            except OSError:
                pass
        elif system.lower() == "windows":
            devices.extend(_windows_smbios())
        return MemoryTopology(
            total_bytes=max(0, total),
            available_bytes=max(0, min(total, available) if total else available),
            devices=tuple(devices),
            platform_system=system,
            platform_machine=platform.machine(),
        )


__all__ = [
    "MemoryAttachment", "MemoryDevice", "MemoryTechnology", "MemoryTopology",
    "SystemMemoryProbe", "parse_memory_technology", "parse_smbios_memory_devices",
]
