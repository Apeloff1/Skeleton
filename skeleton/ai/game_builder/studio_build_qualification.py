"""Explicit local qualification of original console source into real ROM binaries.

Three initial adapters use known commands, never a generated Makefile or shell.
The module must not be called by the autonomous Jeeves planner: executing any
external assembler requires the operator's explicit authorization and opt-in.
This does not qualify controller behavior, emulator playthroughs or hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from time import monotonic

from .contracts import canonical_digest

SCHEMA = "skeleton.game_builder.native_build_qualification.v1"
MAX_SOURCE_BYTES = 512_000
MAX_ROM_BYTES = 8 * 1024 * 1024
MAX_STDIO_BYTES = 16_384
MAX_SECONDS = 120

# (source entry, companions, command chain, output name, header family).
# No PATH strings, filenames, arguments, or shell fragments are user-supplied.
_BUILD_ADAPTERS = {
    "nintendo_game_boy": (
        "main.asm", (), (
            ("rgbasm", "-o", "game.o", "main.asm"),
            ("rgblink", "-n", "game.sym", "-o", "game.gb", "game.o"),
            ("rgbfix", "-v", "-p", "0", "-t", "SKELORIG", "game.gb"),
        ), "game.gb", "gb",
    ),
    "nintendo_game_boy_color": (
        "main.asm", (), (
            ("rgbasm", "-o", "game.o", "main.asm"),
            ("rgblink", "-n", "game.sym", "-o", "game.gbc", "game.o"),
            ("rgbfix", "-v", "-C", "-p", "0", "-t", "SKELCOLOR", "game.gbc"),
        ), "game.gbc", "gbc",
    ),
    "nintendo_famicom": (
        "main.s", ("nes.cfg",), (
            ("ca65", "-o", "game.o", "main.s"),
            ("ld65", "-C", "nes.cfg", "-Ln", "game.sym", "-o", "game.nes", "game.o"),
        ), "game.nes", "nes",
    ),
}


class NativeBuildQualificationError(ValueError):
    """A native build cannot be safely attempted or evidence is inconsistent."""


@dataclass(frozen=True, slots=True)
class BuildQualification:
    target: str
    source_digest: str
    toolchain_available: bool
    tools_invoked: bool
    binary_built: bool
    rom_header_verified: bool
    binary_sha256: str | None
    binary_size: int | None
    symbol_sha256: str | None
    blocker: str | None
    tool_versions: tuple[str, ...]
    receipt_digest: str

    def as_receipt(self) -> dict:
        body = {
            "schema": SCHEMA,
            "target": self.target,
            "source_digest": self.source_digest,
            "toolchain_available": self.toolchain_available,
            "tools_invoked": self.tools_invoked,
            "binary_built": self.binary_built,
            "rom_header_verified": self.rom_header_verified,
            "binary_sha256": self.binary_sha256,
            "binary_size": self.binary_size,
            "symbol_sha256": self.symbol_sha256,
            "blocker": self.blocker,
            "tool_versions": list(self.tool_versions),
            "emulator_playthrough_verified": False,
            "controller_verified": False,
            "physical_hardware_verified": False,
            "publication_approved": False,
        }
        if canonical_digest(body) != self.receipt_digest:
            raise NativeBuildQualificationError("qualification receipt was changed")
        return {**body, "receipt_digest": self.receipt_digest}


def _receipt(target: str, source_digest: str, *, available: bool = False,
             invoked: bool = False, built: bool = False, header: bool = False,
             digest: str | None = None, size: int | None = None,
             symbol_sha256: str | None = None,
             blocker: str | None = None, versions: tuple[str, ...] = ()) -> BuildQualification:
    body = {
        "schema": SCHEMA,
        "target": target, "source_digest": source_digest,
        "toolchain_available": available, "tools_invoked": invoked,
        "binary_built": built, "rom_header_verified": header,
        "binary_sha256": digest, "binary_size": size,
        "symbol_sha256": symbol_sha256,
        "blocker": blocker, "tool_versions": list(versions),
        "emulator_playthrough_verified": False,
        "controller_verified": False,
        "physical_hardware_verified": False,
        "publication_approved": False,
    }
    return BuildQualification(target, source_digest, available, invoked, built,
                              header, digest, size, symbol_sha256, blocker, versions, canonical_digest(body))


def _regular(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise NativeBuildQualificationError("build input requires ordinary regular file")
    before = path.stat()
    if (not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum):
        raise NativeBuildQualificationError("source bytes exceed qualified budget")
    payload = path.read_bytes()
    after = path.stat()
    if (len(payload) != before.st_size
            or (before.st_dev, before.st_ino, before.st_mtime_ns)
               != (after.st_dev, after.st_ino, after.st_mtime_ns)):
        raise NativeBuildQualificationError("build source changed during admission")
    return payload


def _verify_source(project: Path, target: str) -> tuple[dict[str, bytes], str]:
    if not project.is_dir() or project.is_symlink():
        raise NativeBuildQualificationError("original native source folder is not a real directory")
    adapter = _BUILD_ADAPTERS[target]
    manifest_bytes = _regular(project / "manifest.json", MAX_SOURCE_BYTES)
    try:
        manifest = json.loads(manifest_bytes)
    except (ValueError, UnicodeError) as exc:
        raise NativeBuildQualificationError("native manifest has invalid JSON") from exc
    if type(manifest) is not dict:
        raise NativeBuildQualificationError("invalid source manifest")
    # Check the canonical source owner rather than trusting a caller-declared
    # target. Older manifest schemas record target in different named keys.
    expected = manifest.get("target_platform_id",
             manifest.get("target_platform", manifest.get("target")))
    expected = expected or manifest.get("platform")
    if expected != target:
        raise NativeBuildQualificationError("manifest does not bind exact target platform")
    files = {}
    for name in (adapter[0], *adapter[1], "manifest.json"):
        files[name] = _regular(project / name, MAX_SOURCE_BYTES)
    signed = _regular(project / "source_attestation.json", MAX_SOURCE_BYTES)
    try:
        attestation = json.loads(signed)
    except (ValueError, UnicodeError) as exc:
        raise NativeBuildQualificationError("source attestation is invalid") from exc
    if (type(attestation) is not dict
            or attestation.get("schema") != "skeleton.game_builder.source_attestation.v1"
            or attestation.get("target") != target
            or not isinstance(attestation.get("input_files"), dict)
            or attestation.get("binary_compiled") is not False):
        raise NativeBuildQualificationError("original source attestation is missing or mismatched")
    index = attestation["input_files"]
    allowed = {adapter[0], *adapter[1], "Makefile", "manifest.json"}
    if not set(files).issubset(index) or not set(index).issubset(allowed):
        raise NativeBuildQualificationError("source attestation file inventory differs")
    for name, expected_sha in index.items():
        if (type(expected_sha) is not str or len(expected_sha) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha)):
            raise NativeBuildQualificationError("source attestation contains invalid digest")
        data = files.get(name)
        if data is None:
            data = _regular(project / name, MAX_SOURCE_BYTES)
        if sha256(data).hexdigest() != expected_sha:
            raise NativeBuildQualificationError("source file changed since native export")
    if canonical_digest({k: v for k, v in attestation.items()
                         if k != "attestation_digest"}) != attestation.get("attestation_digest"):
        raise NativeBuildQualificationError("original source attestation receipt corrupted")
    source_digest = canonical_digest({
        "target": target,
        "sources": {name: sha256(data).hexdigest() for name, data in sorted(files.items())},
        "source_attestation": sha256(signed).hexdigest(),
    })
    return files, source_digest


def _header(family: str, payload: bytes) -> None:
    if not 16 <= len(payload) <= MAX_ROM_BYTES:
        raise NativeBuildQualificationError("compiled cartridge length is outside budget")
    if family == "nes":
        if not payload.startswith(b"NES\x1a") or len(payload) < 16:
            raise NativeBuildQualificationError("NES iNES header not present")
        banks_prg, banks_chr = payload[4], payload[5]
        if not banks_prg or len(payload) != 16 + banks_prg * 16384 + banks_chr * 8192:
            raise NativeBuildQualificationError("NES cartridge bank extent invalid")
        if payload[6] & 0x04:
            raise NativeBuildQualificationError("unexpected NES trainer")
    elif family in ("gb", "gbc"):
        if len(payload) < 32768 or len(payload) % 16384:
            raise NativeBuildQualificationError("GB bankless ROM size invalid")
        check = 0
        for byte in payload[0x134:0x14D]:
            check = (check - byte - 1) & 255
        if check != payload[0x14D]:
            raise NativeBuildQualificationError("GB cartridge header checksum invalid")
        if family == "gbc" and payload[0x143] not in (0x80, 0xC0):
            raise NativeBuildQualificationError("GBC mode flag not set")
    else:
        raise NativeBuildQualificationError("unsupported cartridge format")


_GB_WRAM_LABELS = ("Level", "PlayerX", "PlayerY", "Health", "Score",
                   "ScoreHigh", "TurnCount", "TurnCountHigh",
                   "GemsRemaining", "GameWon", "GameLost")


def parse_game_boy_symbols(payload: bytes) -> dict[str, int]:
    """Read *assembler-generated* WRAM symbol addresses, never guessed offsets."""
    import re
    if type(payload) is not bytes or len(payload) > 128_000:
        raise NativeBuildQualificationError("bounded actual RGBDS symbol map required")
    labels: dict[str, int] = {}
    for line in payload.decode("ascii", errors="strict").splitlines():
        if not line or line.lstrip().startswith(";"):
            continue
        match = re.fullmatch(r"([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+([A-Za-z][A-Za-z0-9_]*)", line.strip())
        if match is None:
            continue
        bank, address, name = int(match[1], 16), int(match[2], 16), match[3]
        if name not in _GB_WRAM_LABELS:
            continue
        if name in labels or bank != 0 or not 0xC000 <= address <= 0xDFFF:
            raise NativeBuildQualificationError("Game Boy state label is duplicated/outside WRAM")
        labels[name] = address
    if set(labels) != set(_GB_WRAM_LABELS) or len(set(labels.values())) != len(labels):
        raise NativeBuildQualificationError("Game Boy symbol map lacks exact engine state")
    return labels


_NES_RAM_LABELS = _GB_WRAM_LABELS


def parse_nes_labels(payload: bytes) -> dict[str, int]:
    """Parse actual ld65 -Ln VICE export labels within CPU zero-page RAM."""
    import re
    if type(payload) is not bytes or not 1 <= len(payload) <= 128_000:
        raise NativeBuildQualificationError("bounded actual ca65 linker symbol map required")
    try:
        decoded = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise NativeBuildQualificationError("non-ASCII ca65 linker symbols") from exc
    found: dict[str, int] = {}
    for line in decoded.splitlines():
        match = re.fullmatch(r"al ([0-9A-Fa-f]{6}) \.([A-Za-z][A-Za-z0-9_]*)", line.strip())
        if match is None:
            continue
        name = match.group(2)
        if name not in _NES_RAM_LABELS:
            continue
        address = int(match.group(1), 16)
        if name in found or not 0 <= address <= 0xFF:
            raise NativeBuildQualificationError("NES original game state label outside zero-page")
        found[name] = address
    if set(found) != set(_NES_RAM_LABELS) or len(set(found.values())) != len(found):
        raise NativeBuildQualificationError("NES label file lacks distinct original game state")
    return found


def qualify_native_build(
    project: str | Path, target: str, *, authorized: bool,
    execute: bool = False, output: str | Path | None = None,
    output_symbols: str | Path | None = None,
    timeout_seconds: int = 45,
) -> BuildQualification:
    """Preflight by default; opt-in build publishes a hash-verified cartridge.

    No user-supplied command or custom Makefile execution. Staging is isolated
    in a system temporary directory; no source file in the project is edited.
    """
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native build inspection requires local operator authority")
    if type(execute) is not bool:
        raise NativeBuildQualificationError("execute flag must be an explicit boolean")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_SECONDS:
        raise NativeBuildQualificationError("native build time budget must be 1..120 seconds")
    if target not in _BUILD_ADAPTERS:
        raise NativeBuildQualificationError(
            "target has no independently bounded native build adapter"
        )
    folder = Path(project)
    sources, source_digest = _verify_source(folder, target)
    adapter = _BUILD_ADAPTERS[target]
    programs = tuple(dict.fromkeys(command[0] for command in adapter[2]))
    binaries = tuple(shutil.which(name) for name in programs)
    available = all(binaries)
    if not available:
        missing = ",".join(name for name, candidate in zip(programs, binaries) if not candidate)
        return _receipt(target, source_digest, blocker="toolchain_missing:" + missing)
    if not execute:
        return _receipt(target, source_digest, available=True, blocker="execution_not_authorized")
    if output is None:
        raise NativeBuildQualificationError("explicit new ROM output path required")
    destination = Path(output)
    if (destination.exists() or destination.is_symlink()
            or not destination.parent.is_dir() or destination.parent.is_symlink()):
        raise NativeBuildQualificationError("native binary output must be a new contained path")
    symbols_path = None
    if adapter[4] in ("gb", "gbc", "nes"):
        if output_symbols is None:
            raise NativeBuildQualificationError("native GB/GBC/NES qualification requires explicit symbol output")
        symbols_path = Path(output_symbols)
        if (symbols_path.parent != destination.parent
                or symbols_path == destination
                or symbols_path.exists() or symbols_path.is_symlink()
                or symbols_path.parent.is_symlink()):
            raise NativeBuildQualificationError("symbol map must be a separate new file beside ROM")
    elif output_symbols is not None:
        raise NativeBuildQualificationError("symbol output unsupported for target")
    names = dict(zip(programs, binaries))
    versions = tuple(sha256(str(Path(item).resolve()).encode()).hexdigest() for item in binaries)
    invoked = False
    deadline = monotonic() + timeout_seconds
    with tempfile.TemporaryDirectory(prefix="skeleton-native-qualify-") as temp:
        work = Path(temp)
        for name, payload in sources.items():
            with (work / name).open("xb") as stream:
                stream.write(payload)
        for step, template in enumerate(adapter[2]):
            remaining = deadline - monotonic()
            if remaining <= 0:
                return _receipt(target, source_digest, available=True, invoked=invoked,
                                blocker="whole_toolchain_timeout", versions=versions)
            args = [str(names[template[0]]), *template[1:]]
            invoked = True
            # Never capture an unlimited stderr/stdout buffer in memory.
            # Write to a bounded staging artifact and discard it; compiler
            # diagnostics are never sent into Dragon evidence receipts.
            log_path = work / ("tool-step-" + str(step) + ".log")
            try:
                with log_path.open("wb") as stream:
                    result = subprocess.run(
                        args, cwd=work, shell=False, timeout=remaining,
                        stdout=stream, stderr=subprocess.STDOUT, check=False,
                        env={"PATH": os.defpath, "HOME": str(work), "LC_ALL": "C"},
                    )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return _receipt(target, source_digest, available=True, invoked=True,
                                blocker="toolchain_execution_failed:" + type(exc).__name__,
                                versions=versions)
            if log_path.stat().st_size > MAX_STDIO_BYTES:
                return _receipt(target, source_digest, available=True, invoked=True,
                                blocker="toolchain_output_exceeds_budget", versions=versions)
            if result.returncode:
                return _receipt(target, source_digest, available=True, invoked=True,
                                blocker="toolchain_exit_code:" + str(result.returncode),
                                versions=versions)
            # An assembler is a native program, not a sandbox. Keep the
            # generated file count/size bounded before each following step.
            count, total = 0, 0
            for item in work.rglob("*"):
                if item.is_symlink():
                    return _receipt(target, source_digest, available=True, invoked=True,
                                    blocker="toolchain_created_symlink", versions=versions)
                if item.is_file():
                    count += 1
                    total += item.stat().st_size
                if count > 128 or total > 64 * 1024 * 1024:
                    return _receipt(target, source_digest, available=True, invoked=True,
                                    blocker="toolchain_workspace_exceeds_budget", versions=versions)
        try:
            rom = _regular(work / adapter[3], MAX_ROM_BYTES)
            _header(adapter[4], rom)
        except (NativeBuildQualificationError, OSError):
            return _receipt(target, source_digest, available=True, invoked=invoked,
                            blocker="compiled_cartridge_failed_header_or_extent",
                            versions=versions)
        # Stage verified ROM bytes, then atomically hard-link exclusively
        # into an as-yet nonexistent output. Concurrent writers cannot replace
        # a previously published image and failed writes leave no partial ROM.
        symbol_data = None
        if symbols_path is not None:
            try:
                symbol_data = _regular(work / "game.sym", 128_000)
                (parse_nes_labels(symbol_data) if target == "nintendo_famicom"
                 else parse_game_boy_symbols(symbol_data))
            except (OSError, ValueError) as exc:
                return _receipt(target, source_digest, available=True, invoked=True,
                                blocker="gameboy_symbol_map_invalid", versions=versions)
        # Publish the two verified artifacts as new exclusive paths. If
        # either exclusive link fails, reclaim only files created by this
        # invocation; never overwrite another compiler's result.
        published = []
        try:
            if symbols_path is not None and symbol_data is not None:
                fd, candidate = tempfile.mkstemp(
                    prefix=".skeleton-sym-", dir=destination.parent,
                )
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(symbol_data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.link(candidate, symbols_path)
                    published.append(symbols_path)
                finally:
                    if os.path.exists(candidate):
                        os.unlink(candidate)
            fd, candidate = tempfile.mkstemp(prefix=".skeleton-rom-", dir=destination.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(rom)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(candidate, destination)
                published.append(destination)
            finally:
                if os.path.exists(candidate):
                    os.unlink(candidate)
        except OSError:
            for written in reversed(published):
                written.unlink(missing_ok=True)
            raise
        digest = sha256(rom).hexdigest()
        return _receipt(target, source_digest, available=True, invoked=True,
                        built=True, header=True, digest=digest, size=len(rom),
                        symbol_sha256=sha256(symbol_data).hexdigest() if symbol_data else None,
                        versions=versions)


def adapter_catalog() -> dict:
    return {
        "schema": SCHEMA,
        "executable_adapters": sorted(_BUILD_ADAPTERS),
        "source_only_other_native_targets": True,
        "operator_opt_in_required": True,
        "allows_makefile_execution": False,
        "emulator_qualified": False,
        "hardware_qualified": False,
    }


__all__ = [
    "NativeBuildQualificationError", "BuildQualification",
    "qualify_native_build", "adapter_catalog",
]
