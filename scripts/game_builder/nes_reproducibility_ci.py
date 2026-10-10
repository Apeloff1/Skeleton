"""Reproducible, original-homebrew NES NROM cartridge attestation.

Reads two independent ca65 source exports and two compiled files; enforces
exact unlinked game bytes, source maps, world provenance, safe-route identity
and standard iNES NROM-256. Toolchain invocation is observed by CI, not this
offline file inspector. File equality does NOT grant publication permissions,
hardware certification, copyright ownership, or emulator gameplay evidence.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from skeleton.ai.game_builder.native_release_intake import (
    _json, _open_directory, _read_bounded,
)
from scripts.game_builder.native_nes_ci import inspect_rom

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SOURCES = ("main.s", "nes.cfg", "Makefile", "manifest.json")
_ROM_BYTES = 16 + 32768 + 8192
_FALSE = ("cartridge_built", "emulator_verified", "hardware_verified",
          "release_approved", "distribution_licensed")
_WORLD_KEYS = ("project_id", "target", "world_digest", "safe_replay_digest",
               "blueprint_digest", "rights_reference_sha256", "levels",
               "width", "height", "reference_safe_moves")


class NESReproducibilityError(ValueError):
    """The separately generated original NES source or ROM did not match."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NESReproducibilityError(message)


def _digest(value: Any, name: str) -> str:
    _require(isinstance(value, str) and bool(_SHA.fullmatch(value)),
             name + " must be an exact SHA-256 digest")
    return value


def _source(source_dir: Path) -> dict[str, Any]:
    fd = _open_directory(source_dir)
    try:
        files = set(os.listdir(fd))
        allowed = set(_SOURCES)
        if "build" in files:
            data = os.stat("build", dir_fd=fd, follow_symlinks=False)
            _require(stat.S_ISDIR(data.st_mode),
                     "original NES compiler output folder is not an ordinary directory")
            allowed.add("build")
        _require(files == allowed,
                 "NES source package has missing or unreviewed files")
        parts = tuple(
            _read_bounded(Path(name),max_bytes=1024*1024,root_fd=fd)
            for name in _SOURCES
        )
    finally:
        os.close(fd)
    # Mirrors compile_native_nes() exactly; each source is UTF-8 and the
    # digest spans the original four exported generated text files.
    try:
        texts = tuple(part.decode("utf-8") for part in parts)
    except UnicodeError as exc:
        raise NESReproducibilityError("native NES source text encoding invalid") from exc
    digest = sha256("\0".join(texts).encode("utf-8")).hexdigest()
    manifest = _json(parts[3], "original NES generated source")
    _require(
        manifest.get("schema") == "skeleton.game_builder.native_nes_source.v1"
        and manifest.get("target") == "nintendo_famicom"
        and manifest.get("format") == "ines_nrom256_mapper0"
        and manifest.get("original_artwork_only") is True,
        "NES source hardware/creative scope does not match homebrew target",
    )
    for name in _FALSE:
        _require(manifest.get(name) is False,
                 "NES source cannot pre-certify publication or hardware success")
    for key in ("world_digest","safe_replay_digest","blueprint_digest",
                "rights_reference_sha256"):
        _digest(manifest.get(key),key)
    _require(
        isinstance(manifest.get("project_id"),str)
        and bool(manifest["project_id"])
        and type(manifest.get("levels")) is int
        and 1 <= manifest["levels"] <= 8
        and type(manifest.get("width")) is int
        and 9 <= manifest["width"] <= 31
        and type(manifest.get("height")) is int
        and 9 <= manifest["height"] <= 29
        and type(manifest.get("reference_safe_moves")) is int
        and 1 <= manifest["reference_safe_moves"] <= 20_000,
        "original NES game map, route or level bounds invalid",
    )
    return {"digest": digest, "manifest": manifest, "parts": parts}


def _validate_world_against_receipt(source: dict[str, Any], evidence: dict[str, Any]) -> None:
    meta=source["manifest"]
    _require(
        evidence.get("source_digest") == source["digest"]
        and evidence.get("world_digest") == meta["world_digest"]
        and evidence.get("safe_moves") == meta["reference_safe_moves"]
        and evidence.get("native_cartridge_compiled") is False,
        "world-specific NES source generation does not match prebuild evidence",
    )


def verify_original_nes_rebuild(
    *,
    first_source: str | Path,
    second_source: str | Path,
    first_rom: str | Path,
    second_rom: str | Path,
    first_source_evidence: dict[str, Any],
    second_source_evidence: dict[str, Any],
    expected_first_rom_sha256: str,
) -> dict[str, object]:
    """Inspect two actual ROM files and independent regenerated original code."""
    _require(isinstance(first_source_evidence, dict)
             and isinstance(second_source_evidence, dict),
             "independent NES source-generation evidence missing")
    expected_hash=_digest(expected_first_rom_sha256, "first compiled NES ROM")
    _require(Path(first_source) != Path(second_source)
             and Path(first_rom) != Path(second_rom),
             "independent NES source runs and compiled outputs require distinct paths")

    first=_source(Path(first_source))
    second=_source(Path(second_source))
    _validate_world_against_receipt(first, first_source_evidence)
    _validate_world_against_receipt(second, second_source_evidence)
    _require(first["digest"]==second["digest"]
             and first["parts"]==second["parts"],
             "NES game generation not byte-deterministic across two sources")
    for name in _WORLD_KEYS:
        _require(first["manifest"].get(name)==second["manifest"].get(name),
                 "NES original game provenance differs between generation runs")

    fpath, spath=Path(first_rom),Path(second_rom)
    _require(fpath.suffix==spath.suffix==".nes",
             "native ROM must use original iNES cartridge format")
    first_data=_read_bounded(fpath,max_bytes=_ROM_BYTES)
    second_data=_read_bounded(spath,max_bytes=_ROM_BYTES)
    _require(len(first_data)==len(second_data)==_ROM_BYTES,
             "actual NES ROMs differ from mapper-zero NROM-256 length")
    _require(sha256(first_data).hexdigest()==expected_hash,
             "original compiled NES cartridge differs from expected first-build hash")
    _require(first_data==second_data,
             "original NES PRG or CHR differs between independent compiler runs")

    # A header-signature-only stub or reset vector into empty PRG cannot
    # inherit a deterministic-rebuild receipt.
    checked_first=inspect_rom(fpath)
    checked_second=inspect_rom(spath)
    _require(checked_first["sha256"]==checked_second["sha256"]==expected_hash
             and checked_first["reset_vector"]==checked_second["reset_vector"]
             and checked_first["nmi_vector"]==checked_second["nmi_vector"]
             and checked_first["irq_vector"]==checked_second["irq_vector"],
             "NES cartridge bytes changed during structural inspection")

    core: dict[str, object] = {
        "schema":"skeleton.game_builder.nes_reproducibility.v1",
        "target":"nintendo_famicom",
        "mapper":0,
        "prg_rom_bytes":32768,
        "chr_rom_bytes":8192,
        "source_sha256":first["digest"],
        "world_sha256":first["manifest"]["world_digest"],
        "safe_replay_sha256":first["manifest"]["safe_replay_digest"],
        "source_rights_reference_sha256":first["manifest"]["rights_reference_sha256"],
        "original_game_project_id":first["manifest"]["project_id"],
        "rom_sha256":expected_hash,
        "rom_bytes":_ROM_BYTES,
        "reset_vector":checked_first["reset_vector"],
        "nmi_vector":checked_first["nmi_vector"],
        "irq_vector":checked_first["irq_vector"],
        "two_distinct_source_directories_checked":True,
        "identical_generated_source_bytes":True,
        "two_distinct_cartridge_files_checked":True,
        "exact_nrom_prg_chr_bytes_match":True,
        "file_backed_interrupt_vectors_checked":True,
        "separate_generator_invocations_independently_attested":False,
        "assembler_execution_independently_attested":False,
        "emulator_gameplay_verified":False,
        "physical_hardware_verified":False,
        "third_party_rights_independently_cleared":False,
        "publication_authorized":False,
    }
    core["receipt_sha256"]=sha256(json.dumps(
        core,sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode("utf-8")).hexdigest()
    return core


def main() -> None:
    import argparse
    from scripts.game_builder.sega_reproducibility_ci import emit_receipt
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("first-source","second-source","first-rom","second-rom",
                "first-evidence","second-evidence","expected-rom-sha256","receipt-out"):
        p.add_argument("--"+key,required=True)
    args=p.parse_args()
    output=verify_original_nes_rebuild(
        first_source=args.first_source,second_source=args.second_source,
        first_rom=args.first_rom,second_rom=args.second_rom,
        first_source_evidence=_json(
            _read_bounded(Path(args.first_evidence),max_bytes=32768),"first NES authoring"
        ),
        second_source_evidence=_json(
            _read_bounded(Path(args.second_evidence),max_bytes=32768),"second NES authoring"
        ),
        expected_first_rom_sha256=args.expected_rom_sha256,
    )
    emit_receipt(args.receipt_out,output)
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
