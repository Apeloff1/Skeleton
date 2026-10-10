"""Local original native Linux puzzle game compilation and executable selftest.

Produces a REAL host-machine ELF executable of the existing C99 Sokoban
game, replays every emitted level in the compiled runtime, and archives
source, executable and bounded receipts in one offline-verifiable package.

This is an explicitly authorized *local operator* action, never an HTTP
endpoint, crawler/browser action, sandbox substitute, cross-compiled console
binary, distribution/legal clearance or unattended untrusted code runner.
The machine executing this must be a disposable, appropriately restricted
Linux build environment with an independently installed trusted C compiler.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile
import json
import os
import re
import shutil
import subprocess
import sys

from .dragon_native_production import (
    PortableGameDesign, ProductionRequest, _atomic_new, _canonical,
    _hash, _path, _render, _zipinfo, make_source_release,
    verify_source_release,
)

SCHEMA = "skeleton.ai.dragon.original_puzzle_executable.v1"
MAX_BUNDLE = 8_000_000
MAX_EXECUTABLE = 3_000_000
MAX_CAPTURE = 16384
COMPILER_FLAGS = (
    "-std=c99", "-O2", "-Wall", "-Wextra", "-Wpedantic",
    "-Iinclude", "src/main.c", "-o", "dragon_game",
)
REQUIRED_SOURCE_FILES = frozenset({
    "src/main.c", "include/dragon_puzzle.h", "dragon-puzzle-proof.json",
})


@dataclass(frozen=True)
class PuzzleBuildEvidence:
    schema: str
    source_sha256: str
    source_fingerprint: str
    native_target: str
    gameplay_mode: str
    executable_sha256: str
    executable_bytes: int
    executable_format: str
    compiler_executable: str
    compiler_flags: tuple[str, ...]
    compiler_std: str
    runtime_selftest: str
    runtime_output_sha256: str
    runtime_stages_verified: int
    abstract_levels_verified: int
    legal_claim: str
    trust_boundary: str


def _require_platform() -> None:
    if sys.platform != "linux" or os.name != "posix":
        raise OSError("native puzzle compilation is supported only on a Linux host")


def _elf_format(payload: bytes) -> str:
    """Architecture-independent, bounded ELF identification, never execution."""
    if len(payload) < 64 or payload[:4] != b"\x7fELF":
        raise ValueError("executable is not an ELF binary")
    if payload[4] == 1:
        kind = "elf32"
    elif payload[4] == 2:
        kind = "elf64"
    else:
        raise ValueError("unknown ELF class")
    if payload[5] not in (1, 2):
        raise ValueError("unknown ELF endianness")
    # e_type is at bytes 16..17 for 32- and 64-bit ELF.
    byteorder = "little" if payload[5] == 1 else "big"
    e_type = int.from_bytes(payload[16:18], byteorder)
    if e_type not in (2, 3):
        raise ValueError("ELF payload is not an executable or PIE")
    return kind + ("-le" if payload[5] == 1 else "-be")


def _puzzle_proof(source_archive: bytes) -> tuple[dict, dict[str, str]]:
    """Verify source archive, then decode original finite-grid solutions."""
    receipt = verify_source_release(source_archive)
    if receipt["target"] != "pc_linux" or receipt["style"] != "fixed_screen_puzzle":
        raise ValueError("native playable lane supports Linux original puzzle games only")
    with ZipFile(BytesIO(source_archive)) as archive:
        inventory = {}
        for name in REQUIRED_SOURCE_FILES:
            inventory[name] = archive.read("source/" + name).decode("utf-8")
    proof = json.loads(inventory["dragon-puzzle-proof.json"])
    rows = proof.get("level_proofs")
    if (proof.get("schema") != "skeleton.ai.dragon.puzzle_proof.v1" or
            proof.get("mode") != "original_native_sokoban" or
            not isinstance(rows, list) or not 1 <= len(rows) <= 8 or
            proof.get("stages") != len(rows) or
            receipt["campaign_stages"] != len(rows)):
        raise ValueError("native puzzle proof does not match source release")
    # Recheck every level with the existing exact bounded BFS solver, rather
    # than just accepting a plausible-looking declared solution string.
    from .dragon_native_puzzle import transformed_level, solve_grid
    expected_seed = proof["seed"]
    difficulty = proof["difficulty"]
    if (type(expected_seed) is not int or not 0 <= expected_seed <= 0xffffffff or
            type(difficulty) is not int or not 1 <= difficulty <= 10):
        raise ValueError("invalid puzzle replay parameters")
    for number, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("stage") != number:
            raise ValueError("puzzle stages are not canonical or contiguous")
        layout = transformed_level(number, expected_seed, difficulty)
        solution, explored = solve_grid(layout)
        if row.get("solution") != solution or row.get("steps") != len(solution):
            raise ValueError("native puzzle solution does not replay")
        if row.get("examined_states") != explored:
            raise ValueError("puzzle solver state count differs")
        if row.get("input_digest") != sha256(
            "\n".join(layout).encode("utf-8")
        ).hexdigest() or row.get("solution_digest") != sha256(
            solution.encode("utf-8")
        ).hexdigest():
            raise ValueError("native puzzle level proof hashes changed")
        if row.get("optimal_within_abstract_grid") is not True:
            raise ValueError("puzzle optimality scope absent")
    return receipt, inventory


def _invoke(argv: list[str], *, root: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    """Allowlisted host process with bounded runtime/output and fixed cwd."""
    try:
        run = subprocess.run(
            argv,
            cwd=root,
            env={
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(root),
                "LC_ALL": "C",
                "TZ": "UTC",
            },
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("native puzzle build or game selftest exceeded time budget") from exc
    if len(run.stdout) + len(run.stderr) > MAX_CAPTURE:
        raise RuntimeError("compiler/game selftest output exceeds bounded evidence budget")
    if run.returncode != 0:
        raise RuntimeError("native puzzle compiler/selftest failed: " + (
            run.stderr or run.stdout or str(run.returncode)
        )[:600])
    return run


def _selftest_stages(stdout: str, total: int) -> None:
    """Require EXACT one completion line per expected stage and final proof."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    expected = [
        re.compile(r"PUZZLE_STAGE_PASS level=" + str(number) +
                   r" moves=[1-9][0-9]* pushes=[0-9]+$")
        for number in range(1, total + 1)
    ]
    if (len(lines) != total + 1 or
            any(not expected[index].fullmatch(lines[index])
                for index in range(total)) or
            lines[-1] != f"DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages={total}"):
        raise ValueError("compiled puzzle game did not replay every expected stage")


def build_native_puzzle_executable(
    request: ProductionRequest, *, authorized: bool, timeout_seconds: int = 40,
) -> tuple[bytes, dict]:
    """Compile and selftest native C99 game; package actual Linux executable.

    Strictly local: it is intentionally NOT called by the creator API.
    The project input is always regenerated by the approved Dragon native
    emitter; this function does not accept arbitrary external source code.
    """
    if authorized is not True:
        raise PermissionError("explicit local executable build authorization required")
    _require_platform()
    if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 120:
        raise ValueError("invalid bounded native build timeout")
    request.validate()
    if (request.targets != ("pc_linux",) or
            request.style != "fixed_screen_puzzle" or
            request.compile_roms or request.require_compiled):
        raise ValueError("Linux native puzzle source request required; ROM options forbidden")
    compiler = shutil.which("cc")
    if compiler is None:
        raise EnvironmentError("native Linux C compiler cc is not installed")
    project = _render(request, "pc_linux")
    source, _ = make_source_release(project, request)
    original_receipt, source_inventory = _puzzle_proof(source)
    proof = json.loads(source_inventory["dragon-puzzle-proof.json"])
    if not all(name in project.files for name in REQUIRED_SOURCE_FILES):
        raise ValueError("missing original puzzle executable source inputs")
    with TemporaryDirectory(prefix="dragon-native-puzzle-") as directory:
        root = Path(directory)
        for member in REQUIRED_SOURCE_FILES:
            file = root / _path(member)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(project.files[member], encoding="utf-8")
        _invoke([compiler, *COMPILER_FLAGS], root=root, timeout=timeout_seconds)
        executable = root / "dragon_game"
        if executable.is_symlink() or not executable.is_file():
            raise RuntimeError("Linux native compiler did not produce an executable")
        if executable.stat().st_size > MAX_EXECUTABLE:
            raise RuntimeError("native executable exceeds release size budget")
        binary = executable.read_bytes()
        binary_format = _elf_format(binary)
        passed = _invoke([str(executable), "--selftest"], root=root,
                         timeout=timeout_seconds)
        _selftest_stages(passed.stdout, proof["stages"])
        # Exercise a separate real executable route beyond the selftest.
        listing = _invoke([str(executable), "--list"], root=root,
                          timeout=timeout_seconds)
        if len([x for x in listing.stdout.splitlines()
                if re.fullmatch(r"level=[1-8] solution_moves=[1-9][0-9]*", x)]) != proof["stages"]:
            raise ValueError("compiled game --list did not report each generated level")
    evidence = PuzzleBuildEvidence(
        schema=SCHEMA,
        source_sha256=_hash(source),
        source_fingerprint=original_receipt["source_fingerprint"],
        native_target="pc_linux", gameplay_mode="native_original_sokoban",
        executable_sha256=_hash(binary), executable_bytes=len(binary),
        executable_format=binary_format,
        compiler_executable="cc",
        compiler_flags=COMPILER_FLAGS,
        compiler_std="c99",
        runtime_selftest="native_executable_all_stages_passed",
        runtime_output_sha256=_hash(passed.stdout.encode("utf-8")),
        runtime_stages_verified=proof["stages"],
        abstract_levels_verified=proof["stages"],
        legal_claim="original-work operator attestation; no independent legal clearance",
        trust_boundary=(
            "local compiler and executable runtime observed; not externally "
            "signed origin, multi-host portability, GUI acceptance or distribution clearance"
        ),
    )
    receipt = _canonical(asdict(evidence))
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=9) as output:
        output.writestr(_zipinfo("source/native-source-release.zip"), source)
        output.writestr(_zipinfo("binary/dragon_game"), binary)
        output.writestr(_zipinfo("native-executable-evidence.json"), receipt)
    package = archive.getvalue()
    if len(package) > MAX_BUNDLE:
        raise ValueError("native playable package budget exceeded")
    verify_native_puzzle_executable(package)
    return package, asdict(evidence)


def verify_native_puzzle_executable(package: bytes) -> dict:
    """Audit binary/source/runtime receipt without executing untrusted ZIP code.

    A runtime selftest is a report from the compiling host, not proof that
    this executable is safe to reexecute. Re-execution requires explicit
    authorized operator action on a suitably sandboxed Linux runner.
    """
    if not isinstance(package, bytes) or not 80 <= len(package) <= MAX_BUNDLE:
        raise ValueError("native executable release is absent or over budget")
    with ZipFile(BytesIO(package)) as archive:
        members = archive.infolist()
        expected = {
            "source/native-source-release.zip", "binary/dragon_game",
            "native-executable-evidence.json",
        }
        names = [item.filename for item in members]
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError("native executable release has missing/extra members")
        if (any(item.flag_bits & 1 or
                ((item.external_attr >> 16) & 0o170000) == 0o120000
                for item in members) or
                sum(item.file_size for item in members) > MAX_BUNDLE or
                any(item.file_size > MAX_EXECUTABLE for item in members)):
            raise ValueError("unsafe native executable ZIP member")
        source = archive.read("source/native-source-release.zip")
        binary = archive.read("binary/dragon_game")
        evidence = json.loads(archive.read("native-executable-evidence.json"))
    receipt, source_inventory = _puzzle_proof(source)
    proof = json.loads(source_inventory["dragon-puzzle-proof.json"])
    if (evidence.get("schema") != SCHEMA or
            evidence.get("native_target") != "pc_linux" or
            evidence.get("gameplay_mode") != "native_original_sokoban" or
            evidence.get("source_sha256") != _hash(source) or
            evidence.get("source_fingerprint") != receipt["source_fingerprint"] or
            evidence.get("executable_sha256") != _hash(binary) or
            evidence.get("executable_bytes") != len(binary) or
            evidence.get("executable_format") != _elf_format(binary) or
            evidence.get("compiler_flags") != list(COMPILER_FLAGS) or
            evidence.get("compiler_executable") != "cc" or
            evidence.get("compiler_std") != "c99" or
            evidence.get("runtime_stages_verified") != proof["stages"] or
            evidence.get("abstract_levels_verified") != proof["stages"] or
            evidence.get("runtime_selftest") != "native_executable_all_stages_passed" or
            not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("runtime_output_sha256", ""))) or
            evidence.get("legal_claim") !=
                "original-work operator attestation; no independent legal clearance"):
        raise ValueError("native executable source/binary/runtime claim mismatch")
    return {
        "schema": SCHEMA,
        "status": "source_and_native_executable_structurally_verified",
        "source_sha256": evidence["source_sha256"],
        "executable_sha256": evidence["executable_sha256"],
        "source_level_proofs": proof["stages"],
        "runtime_stages_claimed_by_builder": evidence["runtime_stages_verified"],
        "scope": (
            "source and ELF structurally verified; builder-reported native "
            "selftest, not independent runtime attestation or secure executable"
        ),
    }


def publish_native_puzzle_executable(
    request: ProductionRequest, destination: Path, *,
    authorized: bool, timeout_seconds: int = 40,
) -> dict:
    """Write a confirmed real Linux build once, using immutable content names."""
    if authorized is not True:
        raise PermissionError("explicit native puzzle publication authorization required")
    destination = Path(destination).expanduser().absolute()
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("symlink path in executable release destination")
    if destination.exists() and not destination.is_dir():
        raise ValueError("release destination is not a directory")
    package, receipt = build_native_puzzle_executable(
        request, authorized=True, timeout_seconds=timeout_seconds,
    )
    name = "dragon-native-puzzle-" + _hash(package)[:20] + ".zip"
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_new(destination / name, package)
    return {
        "schema": SCHEMA,
        "status": "native_linux_executable_built_and_selftested",
        "filename": name,
        "archive_sha256": _hash(package),
        "size": len(package),
        "evidence": receipt,
    }


def main(argv: list[str] | None = None) -> int:
    from argparse import ArgumentParser
    parser = ArgumentParser(description="Build original native standalone Linux puzzle")
    sub = parser.add_subparsers(dest="operation", required=True)
    build = sub.add_parser("build", help="Compile and exercise the real native C game")
    build.add_argument("--title", default="Original Dragon Puzzle")
    build.add_argument("--seed", type=int, default=1)
    build.add_argument("--difficulty", type=int, default=4)
    build.add_argument("--stages", type=int, default=4)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--attest-original-rights", action="store_true")
    build.add_argument("--authorize-local-build", action="store_true")
    audit = sub.add_parser("verify", help="Offline structural/source/proof audit")
    audit.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.operation == "verify":
        output = verify_native_puzzle_executable(args.archive.read_bytes())
    else:
        design = PortableGameDesign(
            stages=args.stages, difficulty=args.difficulty,
            candidates=8, hero="explorer", quest_theme="ancient_ruins",
        )
        request = ProductionRequest(
            title=args.title, style="fixed_screen_puzzle",
            targets=("pc_linux",), seed=args.seed,
            original_work_attested=args.attest_original_rights,
            portable_design=design,
        )
        output = publish_native_puzzle_executable(
            request, args.out, authorized=args.authorize_local_build,
        )
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
