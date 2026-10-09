"""Offline machine-history ingest for archival discovery, never ROM extraction.

Imports *only descriptive machine metadata* from user-supplied MAME -listxml.
It deliberately does not convert MAME software entries, hashes, ROM sets, BIOS
requirements or clones into native-toolchain claims. Machine rows are NOT
automatically admitted to the curated PlatformRegistry.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree
import json
import re

from .platform_registry import PlatformRegistry, default_registry

MAX_IMPORT_BYTES = 512 * 1024 * 1024
MAX_MACHINE_RECORDS = 250_000
_XML_ID = re.compile(r"^[a-z0-9_]{1,32}$")
_YEAR = re.compile(r"^(?:1[89][0-9]{2}|20[0-9]{2}|\?)$")
_BLOCKED_XML = (b"<!ENTITY", b"<![CDATA[", b"<![INCLUDE[", b"<![IGNORE[")


class MachineArchiveError(ValueError):
    """Invalid, dangerous, or incomplete historical inventory input."""


@dataclass(frozen=True, slots=True)
class MachineRecord:
    """External MAME inventory row: not a distinct physical platform assertion."""
    key: str
    title: str
    year: str | None
    manufacturer: str | None
    clone_of: str | None
    rom_of: str | None
    sourcefile: str | None
    runnable: bool
    is_device: bool
    is_bios: bool
    driver_status: str | None
    display_types: tuple[str, ...]
    input_players: int | None

    @property
    def archive_candidate(self) -> bool:
        return self.runnable and not self.is_device and not self.is_bios


@dataclass(frozen=True, slots=True)
class MachineSnapshot:
    source_format: str
    source_sha256: str
    declared_mame_build: str
    records: tuple[MachineRecord, ...]

    def summary(self, registry: PlatformRegistry | None = None) -> dict[str, object]:
        curated = default_registry() if registry is None else registry
        curated_names = {p.name.casefold() for p in curated.profiles.values()}
        count = sum(p.archive_candidate for p in self.records)
        exact_name_matches = sum(
            p.archive_candidate and p.title.casefold() in curated_names for p in self.records
        )
        return {
            "source": self.source_format, "build": self.declared_mame_build,
            "source_sha256": self.source_sha256,
            "machine_records": len(self.records),
            "runnable_candidate_records": count,
            "devices_bios_and_nonrunnable": len(self.records) - count,
            "exact_curated_name_matches": exact_name_matches,
            "unmatched_machine_records": count - exact_name_matches,
            "automatic_promotions": 0,
            "native_builds_verified": 0,
            "archival_status": "machine_metadata_candidate_census_not_complete_platform_reconciliation",
        }

    def review_queue(self, registry: PlatformRegistry | None = None, *, limit: int = 1000) -> tuple[MachineRecord, ...]:
        if type(limit) is not int or not 0 <= limit <= MAX_MACHINE_RECORDS:
            raise MachineArchiveError("invalid review queue limit")
        curated = default_registry() if registry is None else registry
        curated_names = {p.name.casefold() for p in curated.profiles.values()}
        return tuple(
            p for p in self.records if p.archive_candidate and p.title.casefold() not in curated_names
        )[:limit]


def _safe_text(value: object, *, field: str, length: int = 240) -> str:
    if not isinstance(value, str) or not value or len(value) > length:
        raise MachineArchiveError("invalid machine " + field)
    if any(ord(c) < 32 and c not in "\t" for c in value):
        raise MachineArchiveError("control characters in " + field)
    return value


def _opt_text(value: object, *, field: str, length: int = 240) -> str | None:
    if value is None or value == "":
        return None
    return _safe_text(value, field=field, length=length)


def _machine_from_xml(elem: ElementTree.Element) -> MachineRecord:
    key = elem.get("name")
    if not isinstance(key, str) or not _XML_ID.fullmatch(key):
        raise MachineArchiveError("invalid MAME machine shortname")
    title = _safe_text(elem.findtext("description"), field="description")
    year = _opt_text(elem.findtext("year"), field="year", length=10)
    if year is not None and not (
        _YEAR.fullmatch(year) or
        re.fullmatch(r"(?:1[89]|20)[0-9?]{2}", year)
    ):
        # Some archive records contain uncertain historical dates; do not infer.
        year = None
    maker = _opt_text(elem.findtext("manufacturer"), field="manufacturer", length=128)
    cloneof = _opt_text(elem.get("cloneof"), field="cloneof", length=32)
    romof = _opt_text(elem.get("romof"), field="romof", length=32)
    source = _opt_text(elem.get("sourcefile"), field="sourcefile", length=240)
    display_types = tuple(sorted(set(
        t for child in elem.findall("display")
        if (t := child.get("type")) in {"raster", "vector", "lcd", "svg", "unknown"}
    )))
    players = None
    input_ = elem.find("input")
    if input_ is not None:
        raw_players = input_.get("players")
        if raw_players is not None and raw_players.isdecimal() and 0 <= int(raw_players) <= 64:
            players = int(raw_players)
    driver = elem.find("driver")
    driver_status = driver.get("status") if driver is not None else None
    if driver_status not in {None, "good", "imperfect", "preliminary"}:
        driver_status = None
    return MachineRecord(
        key=key, title=title, year=year, manufacturer=maker,
        clone_of=cloneof, rom_of=romof, sourcefile=source,
        runnable=elem.get("runnable") != "no",
        is_device=elem.get("isdevice") == "yes",
        is_bios=elem.get("isbios") == "yes",
        driver_status=driver_status,
        display_types=display_types, input_players=players,
    )


def _inspect_source(path: Path, *, maximum_bytes: int) -> tuple[int, str]:
    if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_IMPORT_BYTES:
        raise MachineArchiveError("invalid maximum input size")
    if not path.is_file() or path.is_symlink():
        raise MachineArchiveError("expected an existing, non-symlink MAME XML file")
    size = path.stat().st_size
    if size == 0 or size > maximum_bytes:
        raise MachineArchiveError("missing or oversize MAME metadata")
    digest = sha256()
    # MAME listxml may include a DTD; reject explicitly declared user entities
    # to prevent billion-laughs expansions and unintended entity interpolation.
    lookbehind = b""
    with path.open("rb") as stream:
        while chunk := stream.read(128 * 1024):
            digest.update(chunk)
            scan = (lookbehind + chunk).upper()
            if any(block.upper() in scan for block in _BLOCKED_XML):
                raise MachineArchiveError("untrusted XML entity or conditional section")
            lookbehind = scan[-32:]
    return size, digest.hexdigest()


def import_mame_listxml(
    path: str | Path, *, maximum_bytes: int = MAX_IMPORT_BYTES,
    maximum_machines: int = MAX_MACHINE_RECORDS,
) -> MachineSnapshot:
    """Bounded streaming read of MAME official XML, excluding all binary assets.

    DO NOT use this function to download proprietary BIOS, ROMs, firmware,
    dumps, game executables, keys or SDKs. Input must be supplied offline.
    """
    if type(maximum_machines) is not int or not 1 <= maximum_machines <= MAX_MACHINE_RECORDS:
        raise MachineArchiveError("invalid machine count limit")
    source = Path(path)
    _, digest = _inspect_source(source, maximum_bytes=maximum_bytes)
    seen: set[str] = set()
    records: list[MachineRecord] = []
    mame_build = ""
    root = None
    try:
        for event, elem in ElementTree.iterparse(source, events=("start", "end")):
            if root is None:
                if event != "start" or elem.tag != "mame":
                    raise MachineArchiveError("expected official MAME -listxml root")
                root = elem
                mame_build = _safe_text(elem.get("build") or "unspecified", field="build")
            if event == "end" and elem.tag == "machine":
                record = _machine_from_xml(elem)
                if record.key in seen:
                    raise MachineArchiveError("duplicate MAME machine shortname")
                seen.add(record.key)
                records.append(record)
                if len(records) > maximum_machines:
                    raise MachineArchiveError("too many machine records")
                elem.clear()
                if root is not None:
                    root.clear()
    except (ElementTree.ParseError, OSError) as exc:
        raise MachineArchiveError("malformed/unreadable MAME XML") from exc
    if not records:
        raise MachineArchiveError("empty MAME machine inventory")
    return MachineSnapshot(
        source_format="mame-listxml-machine-metadata-only", source_sha256=digest,
        declared_mame_build=mame_build,
        records=tuple(sorted(records, key=lambda m: m.key)),
    )


def export_review_queue(
    snapshot: MachineSnapshot, destination: str | Path, *,
    limit: int = 1000, authorized: bool,
    registry: PlatformRegistry | None = None,
) -> Path:
    """Write bounded metadata-only JSONL for human curation, no auto promotion."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("archival metadata export requires authorization")
    if not isinstance(snapshot, MachineSnapshot):
        raise MachineArchiveError("typed MAME metadata snapshot required")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise FileExistsError(str(path))
    candidates = snapshot.review_queue(registry, limit=limit)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        for record in candidates:
            data: dict[str, object] = {
                "machine_key": record.key,
                "description": record.title,
                "year_label": record.year,
                "manufacturer": record.manufacturer,
                "mame_cloneof": record.clone_of,
                "mame_romof": record.rom_of,
                "mame_driver_sourcefile": record.sourcefile,
                "display_types": list(record.display_types),
                "input_players": record.input_players,
                "driver_status": record.driver_status,
                "source_sha256": snapshot.source_sha256,
                "review_state": "candidate_unverified",
                "rom_firmware_or_game_assets_included": False,
                "native_toolchain_available": False,
                "may_auto_promote_to_platform": False,
            }
            output.write(json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n")
    return path
