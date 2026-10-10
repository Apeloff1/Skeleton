"""Deterministic, rights-attested production lane for Dragon native homebrew.

Uses the existing Dragon hardware catalog, native emitters, and local ROM
compiler. This is a local CLI/operator component, not an HTTP build service,
research promotion path, or authority to distribute third-party games.
Every claim is evidence-level scoped; source != binary != emulator-tested.
"""
from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import json
import os
import re
import shutil

from .dragon_game_mechanics import Mechanic
from .dragon_native_projects import EMITTERS, NativeProject, digest, render_native_project
from .dragon_native_targets import CATALOG, STYLES, target_catalog

SCHEMA = "skeleton.ai.dragon.native_production.v1"
RELEASE_SCHEMA = "skeleton.ai.dragon.native_source_release.v1"
INDEX_SCHEMA = "skeleton.ai.dragon.native_production_index.v1"
RIGHTS_BASES = frozenset({"original_homebrew", "verified_public_domain", "documented_license"})
COMPILABLE = frozenset({"game_boy", "game_boy_color", "nes"})
MAX_TARGETS = 16
MAX_SOURCE_FILES = 128
MAX_SOURCE_BYTES = 2_000_000
MAX_ARCHIVE_BYTES = 8_000_000
MAX_PORTFOLIO_BYTES = 64_000_000
HEX = re.compile(r"[a-f0-9]{64}\Z")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*\Z")


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def _hash(body: bytes) -> str:
    return sha256(body).hexdigest()


@dataclass(frozen=True)
class ProductionRequest:
    title: str
    style: str
    targets: tuple[str, ...]
    original_work_attested: bool
    rights_basis: str = "original_homebrew"
    rights_reference: str = ""
    seed: int = 1
    compile_roms: bool = False
    require_compiled: bool = False
    max_portfolio_bytes: int = MAX_PORTFOLIO_BYTES

    def validate(self) -> None:
        if not isinstance(self.title, str) or not 2 <= len(self.title.strip()) <= 80:
            raise ValueError("title must have 2-80 characters")
        if not isinstance(self.style, str) or self.style not in STYLES:
            raise ValueError("unsupported game style")
        if (not isinstance(self.targets, tuple) or
                not 1 <= len(self.targets) <= MAX_TARGETS or
                any(not isinstance(target, str) for target in self.targets) or
                len(set(self.targets)) != len(self.targets)):
            raise ValueError("targets must be 1-16 unique platform IDs")
        if not all(t in CATALOG for t in self.targets):
            raise ValueError("unknown hardware target")
        if self.original_work_attested is not True:
            raise PermissionError("operator must explicitly attest rights and original work")
        if self.rights_basis not in RIGHTS_BASES:
            raise ValueError("unknown rights basis; legal status cannot be inferred")
        if (not isinstance(self.rights_reference, str) or
                len(self.rights_reference) > 240 or
                any(ord(ch) < 32 or ord(ch) > 126 for ch in self.rights_reference)):
            raise ValueError("rights reference must be bounded printable text")
        if self.rights_basis != "original_homebrew" and not self.rights_reference.strip():
            raise PermissionError("external rights basis needs a documentary reference")
        if type(self.seed) is not int or not 0 <= self.seed <= 0xffffffff:
            raise ValueError("seed must be an unsigned 32-bit integer")
        if type(self.compile_roms) is not bool or type(self.require_compiled) is not bool:
            raise ValueError("compile flags must be booleans")
        if self.require_compiled and not self.compile_roms:
            raise ValueError("required native build needs compile_roms")
        if type(self.max_portfolio_bytes) is not int or not 1_024 <= self.max_portfolio_bytes <= MAX_PORTFOLIO_BYTES:
            raise ValueError("invalid bounded portfolio budget")

    @property
    def request_id(self) -> str:
        self.validate()
        return digest({
            "schema": SCHEMA, "title": self.title, "style": self.style,
            "targets": sorted(self.targets), "seed": self.seed,
            "rights_basis": self.rights_basis, "rights_reference": self.rights_reference,
            "attested": True, "compile_roms": self.compile_roms,
            "require_compiled": self.require_compiled,
        })


@dataclass(frozen=True)
class TargetPlan:
    target: str
    family: str
    toolchain: str
    output_extension: str
    state: str
    reason: str
    compiler_available: bool
    build_evidence: str


@dataclass(frozen=True)
class ArtifactReceipt:
    target: str
    source_fingerprint: str
    archive_sha256: str
    archive_name: str
    archive_bytes: int
    source_count: int
    source_bytes: int
    binary_sha256: str | None
    evidence: str
    compiler_state: str


@dataclass(frozen=True)
class ProductionIndex:
    schema: str
    request_id: str
    style: str
    target_count: int
    entries: tuple[ArtifactReceipt, ...]
    production_evidence: str
    legal_claim: str


def capability_matrix() -> tuple[dict, ...]:
    """Show emitter, compilable output and licensing independently, not inflated."""
    rows = {r["id"]: r for r in target_catalog()}
    result = []
    for target in CATALOG.values():
        item = rows[target.id]
        styles = tuple(item["supported_styles"])
        result.append({
            "id": target.id,
            "family": target.family,
            "status": target.status,
            "toolchain": target.toolchain,
            "native_source_emitter": target.id in EMITTERS,
            "supported_styles": styles if target.id in EMITTERS and target.status != "licensed_sdk" else (),
            "local_verified_rom_compiler": target.id in COMPILABLE,
            "claims": "source-only-until-independent-compilation-and-playtesting",
        })
    return tuple(result)


def _toolchain_ready(target: str) -> bool:
    if target not in COMPILABLE:
        return False
    from .dragon_native_compile import COMMANDS
    return all(shutil.which(argv[0]) is not None for argv in COMMANDS[target])


def plan_production(request: ProductionRequest) -> tuple[TargetPlan, ...]:
    """Preflight every target before performing *any* output writes."""
    request.validate()
    matrix = {r["id"]: r for r in capability_matrix()}
    decisions = []
    for target_id in sorted(request.targets):
        target = CATALOG[target_id]
        available = matrix[target_id]
        compiler = _toolchain_ready(target_id)
        if target.status == "licensed_sdk":
            state, reason = "blocked", "licensed SDK or partner authorization required"
        elif not available["native_source_emitter"]:
            state, reason = "blocked", "no implemented source emitter; catalog entry is not support"
        elif request.style not in available["supported_styles"]:
            state, reason = "blocked", "requested gameplay is not implemented on this target"
        elif request.compile_roms and target_id not in COMPILABLE:
            state, reason = "blocked", "local verified ROM adapter not implemented for target"
        elif request.require_compiled and not compiler:
            state, reason = "blocked", "required local compiler is not installed"
        else:
            state, reason = "source_ready", "original source generator available"
            if request.compile_roms and compiler:
                reason = "local ROM compiler installed; binary still unverified until built"
        decisions.append(TargetPlan(
            target=target_id, family=target.family, toolchain=target.toolchain,
            output_extension=target.output, state=state, reason=reason,
            compiler_available=compiler, build_evidence="none",
        ))
    return tuple(decisions)


def _path(name: str) -> str:
    if (not isinstance(name, str) or not 1 <= len(name) <= 180 or
            not SAFE_NAME.fullmatch(name) or "\\" in name):
        raise ValueError("untrusted generated filename")
    path = PurePosixPath(name)
    if (path.is_absolute() or any(piece in (".", "..", "") for piece in path.parts) or
            len(path.parts) > 8):
        raise ValueError("generated path traversal or excessive nesting")
    return str(path)


def validate_native_source(project: NativeProject) -> dict[str, str]:
    """Admit only stable, safe, resource-bounded files from the native owner."""
    if project.status != "source_generated" or project.target_id not in EMITTERS:
        raise ValueError("native project is not an implemented source emitter")
    if len(project.files) < 2 or len(project.files) > MAX_SOURCE_FILES:
        raise ValueError("source inventory out of bounds")
    file_hashes: dict[str, str] = {}
    total = 0
    for name, content in sorted(project.files.items()):
        normalized = _path(name)
        if normalized in file_hashes or not isinstance(content, str):
            raise ValueError("duplicate or non-text native source")
        raw = content.encode("utf-8")
        total += len(raw)
        if len(raw) > 400_000 or total > MAX_SOURCE_BYTES or b"\x00" in raw:
            raise ValueError("unsafe source payload or resource budget")
        file_hashes[normalized] = _hash(raw)
    if project.digest != digest(project.files):
        raise ValueError("native project source fingerprint drift")
    if "dragon-native-manifest.json" not in project.files:
        raise ValueError("missing canonical native manifest")
    native = json.loads(project.files["dragon-native-manifest.json"])
    if native.get("target") != project.target_id or native.get("status") != "source_generated":
        raise ValueError("native project manifest and target disagree")
    return file_hashes


def _render(request: ProductionRequest, target_id: str) -> NativeProject:
    identity = digest([request.request_id, target_id, request.style, request.seed])
    return render_native_project(
        title=request.title,
        target_id=target_id,
        style=request.style,
        candidate_id=identity,
        mechanics=(Mechanic.MOVEMENT, Mechanic.EXPLORATION),
        authorized=True,
    )


def _compile_rom(project: NativeProject) -> tuple[bytes | None, str]:
    """Invoke the existing bounded local compiler, never an arbitrary build script."""
    from .dragon_native_compile import OUTPUTS, compile_local
    with TemporaryDirectory(prefix="dragon-production-") as temporary:
        root = Path(temporary)
        for name, content in project.files.items():
            target = root / _path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        result = compile_local(project, root, authorized=True)
        if result.state != "compiled_native":
            return None, result.state
        binary = root / OUTPUTS[project.target_id]
        if binary.is_symlink() or not binary.is_file():
            raise RuntimeError("compiled native artifact missing")
        payload = binary.read_bytes()
        if _hash(payload) != result.binary_sha256 or len(payload) != result.bytes_written:
            raise RuntimeError("compiled ROM digest mismatch")
        return payload, result.state


def _zipinfo(name: str) -> ZipInfo:
    info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    return info


def make_source_release(
    project: NativeProject, request: ProductionRequest,
    *, binary: bytes | None = None, compiler_state: str = "not_requested",
) -> tuple[bytes, ArtifactReceipt]:
    request.validate()
    if project.target_id not in request.targets or project.style != request.style:
        raise ValueError("native project does not match approved production request")
    hashes = validate_native_source(project)
    if binary is not None:
        if project.target_id not in COMPILABLE or compiler_state != "compiled_native":
            raise ValueError("binary may be admitted only from verified compiler")
        from .dragon_native_compile import _verify
        if not _verify(project.target_id, binary):
            raise ValueError("compiled ROM failed structural verification")
    if request.require_compiled and binary is None:
        raise RuntimeError("compiled ROM required; refusing source-only release")
    source_total = sum(len(v.encode("utf-8")) for v in project.files.values())
    evidence = "rom_structural_verified" if binary is not None else "source_generated"
    binary_name = ("binary/dragon." + CATALOG[project.target_id].output) if binary else None
    receipt = {
        "schema": RELEASE_SCHEMA,
        "request_id": request.request_id,
        "project_id": project.project_id,
        "target": project.target_id,
        "style": project.style,
        "source_fingerprint": project.digest,
        "source_files": hashes,
        "source_count": len(hashes),
        "source_bytes": source_total,
        "compiler_state": compiler_state,
        "binary_member": binary_name,
        "binary_sha256": _hash(binary) if binary is not None else None,
        "binary_bytes": len(binary) if binary is not None else 0,
        "evidence": evidence,
        "rights_basis": request.rights_basis,
        "rights_reference": request.rights_reference,
        "rights_attestation": "operator_attested_unverified",
        "legal_claim": "attestation is not a legal clearance or license grant",
        "verification_limit": "ROM header and size do not prove emulator, hardware, or gameplay function",
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as zip_file:
        for name in sorted(hashes):
            zip_file.writestr(_zipinfo("source/" + name), project.files[name].encode("utf-8"))
        if binary_name is not None and binary is not None:
            zip_file.writestr(_zipinfo(binary_name), binary)
        zip_file.writestr(_zipinfo("release-receipt.json"), _canonical(receipt))
    payload = buffer.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("release archive budget exceeded")
    archive_name = "dragon-" + project.target_id + "-" + _hash(payload)[:20] + ".zip"
    return payload, ArtifactReceipt(
        target=project.target_id, source_fingerprint=project.digest,
        archive_sha256=_hash(payload), archive_name=archive_name,
        archive_bytes=len(payload), source_count=len(hashes),
        source_bytes=source_total, binary_sha256=receipt["binary_sha256"],
        evidence=evidence, compiler_state=compiler_state,
    )


def verify_source_release(payload: bytes) -> dict:
    """Recompute every member digest, reject duplicates, extra members and symlinks."""
    if not isinstance(payload, bytes) or not 50 <= len(payload) <= MAX_ARCHIVE_BYTES:
        raise ValueError("invalid release size")
    with ZipFile(BytesIO(payload)) as archive:
        members = archive.infolist()
        names = [info.filename for info in members]
        if len(names) != len(set(names)) or len(names) > MAX_SOURCE_FILES + 2:
            raise ValueError("duplicate or excessive archive members")
        if "release-receipt.json" not in names:
            raise ValueError("release receipt missing")
        if any(info.flag_bits & 1 or (info.external_attr >> 16) & 0o170000 == 0o120000
               or info.file_size > MAX_SOURCE_BYTES for info in members):
            raise ValueError("encrypted, symlinked or overlarge archive member")
        if sum(x.file_size for x in members) > MAX_SOURCE_BYTES + 2_100_000:
            raise ValueError("release uncompressed size budget exceeded")
        receipt = json.loads(archive.read("release-receipt.json"))
        if receipt.get("schema") != RELEASE_SCHEMA or not HEX.fullmatch(str(receipt.get("request_id", ""))):
            raise ValueError("unrecognized or invalid release receipt")
        source_files = receipt.get("source_files")
        if not isinstance(source_files, dict) or not 2 <= len(source_files) <= MAX_SOURCE_FILES:
            raise ValueError("invalid source inventory")
        expected = {"release-receipt.json"}
        counted = 0
        for name, checksum in source_files.items():
            _path(name)
            if not isinstance(checksum, str) or not HEX.fullmatch(checksum):
                raise ValueError("invalid source digest")
            member = "source/" + name
            expected.add(member)
            body = archive.read(member)
            counted += len(body)
            if _hash(body) != checksum or b"\x00" in body:
                raise ValueError("modified or invalid source file")
        if counted != receipt.get("source_bytes") or len(source_files) != receipt.get("source_count"):
            raise ValueError("source quantity or byte count mismatch")
        binary_name = receipt.get("binary_member")
        if binary_name is not None:
            if (not isinstance(binary_name, str) or
                    binary_name != "binary/dragon." + CATALOG[receipt["target"]].output or
                    receipt.get("target") not in COMPILABLE):
                raise ValueError("invalid native output path")
            expected.add(binary_name)
            binary = archive.read(binary_name)
            from .dragon_native_compile import _verify
            if (_hash(binary) != receipt.get("binary_sha256") or
                    len(binary) != receipt.get("binary_bytes") or
                    not _verify(receipt["target"], binary)):
                raise ValueError("native binary verification failed")
            if receipt.get("evidence") != "rom_structural_verified":
                raise ValueError("binary evidence state inconsistent")
        elif (receipt.get("binary_sha256") is not None or
              receipt.get("evidence") != "source_generated"):
            raise ValueError("source-only release falsely claims compiled evidence")
        if set(names) != expected or names != sorted(source_files, key=lambda x: "source/" + x) and False:
            # Exact membership matters; zip ordering is not an authority condition.
            raise ValueError("unexpected member in release")
        if receipt.get("target") not in CATALOG or receipt.get("style") not in STYLES:
            raise ValueError("unknown packaged target/style")
        return receipt


def _atomic_new(path: Path, payload: bytes) -> None:
    """Create immutably; existing exact bytes are idempotent, never overwritten."""
    if path.exists() or path.is_symlink():
        if not path.is_symlink() and path.is_file() and path.read_bytes() == payload:
            return
        raise FileExistsError("conflicting release artifact: " + path.name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def publish_production(
    request: ProductionRequest, destination: Path, *,
    authorized: bool, dry_run: bool = False,
) -> dict:
    """Release an approved original-homebrew multi-target *source* portfolio.

    Unavailable targets fail the whole preflight. No fake ROM output. Optional
    compilation is limited to established local RGBDS/cc65 adapters. The
    immutable index is published last; incomplete batches are safely resumable.
    """
    if authorized is not True:
        raise PermissionError("operator publication authorization required")
    decisions = plan_production(request)
    refused = [x for x in decisions if x.state != "source_ready"]
    if refused:
        return {"schema": SCHEMA, "status": "blocked", "request_id": request.request_id,
                "targets": [asdict(x) for x in decisions], "artifacts": []}
    if dry_run:
        return {"schema": SCHEMA, "status": "planned", "request_id": request.request_id,
                "targets": [asdict(x) for x in decisions], "artifacts": []}
    destination = Path(destination).expanduser()
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("unsafe destination directory")
    if destination.exists() and any(p.is_symlink() for p in destination.iterdir()):
        raise ValueError("destination contains symlink; refusing mutable output")
    # Generate and validate entire portfolio in memory BEFORE any writes.
    artifacts: list[tuple[bytes, ArtifactReceipt]] = []
    total_bytes = 0
    for decision in decisions:
        project = _render(request, decision.target)
        validate_native_source(project)
        binary = None
        state = "not_requested"
        if request.compile_roms:
            if decision.compiler_available:
                binary, state = _compile_rom(project)
            else:
                state = "toolchain_missing"
        payload, receipt = make_source_release(project, request, binary=binary,
                                               compiler_state=state)
        verify_source_release(payload)
        total_bytes += len(payload)
        if total_bytes > request.max_portfolio_bytes:
            raise ValueError("portfolio exceeds approved memory/output budget")
        artifacts.append((payload, receipt))
    index = ProductionIndex(
        schema=INDEX_SCHEMA, request_id=request.request_id,
        style=request.style, target_count=len(artifacts),
        entries=tuple(receipt for _, receipt in artifacts),
        production_evidence=(
            "source_and_rom_structure_only" if any(r.binary_sha256 for _, r in artifacts)
            else "source_only"
        ),
        legal_claim="attested original/authorized material; external legal verification not asserted",
    )
    listing = _canonical(asdict(index))
    if total_bytes + len(listing) > request.max_portfolio_bytes:
        raise ValueError("portfolio and manifest exceed approved budget")
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("destination changed into symlink")
    for payload, receipt in artifacts:
        _atomic_new(destination / receipt.archive_name, payload)
    index_name = "dragon-production-" + request.request_id[:20] + ".json"
    _atomic_new(destination / index_name, listing)
    return {"schema": SCHEMA, "status": "published",
            "request_id": request.request_id,
            "index": index_name, "index_sha256": _hash(listing),
            "targets": [asdict(x) for x in decisions],
            "artifacts": [asdict(r) for _, r in artifacts],
            "portfolio_bytes": total_bytes + len(listing)}


def verify_published_production(destination: Path, index_name: str) -> dict:
    """Offline release audit against immutable index; no network or provider AI."""
    _path(index_name)
    root = Path(destination)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("unsafe portfolio directory")
    index_path = root / index_name
    if index_path.is_symlink():
        raise ValueError("index may not be a symlink")
    data = index_path.read_bytes()
    if len(data) > 128_000:
        raise ValueError("portfolio index over budget")
    index = json.loads(data)
    entries = index.get("entries")
    if (index.get("schema") != INDEX_SCHEMA or
            not HEX.fullmatch(str(index.get("request_id", ""))) or
            not isinstance(entries, list) or
            not 1 <= len(entries) <= MAX_TARGETS or
            index.get("target_count") != len(entries)):
        raise ValueError("portfolio index invalid")
    hashes: list[str] = []
    targets: set[str] = set()
    for item in entries:
        name = _path(item["archive_name"])
        artifact = root / name
        if artifact.is_symlink() or not artifact.is_file():
            raise ValueError("missing or unsafe portfolio archive")
        payload = artifact.read_bytes()
        if _hash(payload) != item["archive_sha256"] or len(payload) != item["archive_bytes"]:
            raise ValueError("portfolio archive changed after publishing")
        receipt = verify_source_release(payload)
        target = receipt["target"]
        if (target in targets or target != item["target"] or
                receipt["request_id"] != index["request_id"] or
                receipt["source_fingerprint"] != item["source_fingerprint"] or
                receipt["binary_sha256"] != item["binary_sha256"]):
            raise ValueError("portfolio index and archive receipts disagree")
        targets.add(target)
        hashes.append(item["archive_sha256"])
    return {"schema": INDEX_SCHEMA, "status": "verified",
            "request_id": index["request_id"],
            "archives_verified": len(entries),
            "archive_hashes": hashes,
            "scope": "sources-and-optional-ROM-structure; not hardware or legal certification"}


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Dragon offline original native production lane")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("capabilities", help="List truthful platform source/compiler coverage")
    for command in ("plan", "build"):
        sub = subs.add_parser(command)
        sub.add_argument("--title", required=True)
        sub.add_argument("--style", required=True)
        sub.add_argument("--targets", required=True, help="comma-separated target IDs")
        sub.add_argument("--seed", type=int, default=1)
        sub.add_argument("--rights-basis", choices=sorted(RIGHTS_BASES),
                         default="original_homebrew")
        sub.add_argument("--rights-reference", default="")
        sub.add_argument("--attest-original-rights", action="store_true")
        sub.add_argument("--compile-roms", action="store_true")
        sub.add_argument("--require-compiled", action="store_true")
        if command == "build":
            sub.add_argument("--out", type=Path, required=True)
            sub.add_argument("--authorize-publication", action="store_true")
    audit = subs.add_parser("verify")
    audit.add_argument("--out", type=Path, required=True)
    audit.add_argument("--index", required=True)
    args = parser.parse_args(argv)
    if args.command == "capabilities":
        output = {"schema": SCHEMA, "targets": capability_matrix()}
    elif args.command == "verify":
        output = verify_published_production(args.out, args.index)
    else:
        request = ProductionRequest(
            title=args.title, style=args.style,
            targets=tuple(t.strip() for t in args.targets.split(",")),
            original_work_attested=args.attest_original_rights,
            rights_basis=args.rights_basis, rights_reference=args.rights_reference,
            seed=args.seed, compile_roms=args.compile_roms,
            require_compiled=args.require_compiled,
        )
        if args.command == "plan":
            output = {"schema": SCHEMA, "request_id": request.request_id,
                      "targets": [asdict(x) for x in plan_production(request)]}
        else:
            output = publish_production(
                request, args.out, authorized=args.authorize_publication)
    print(json.dumps(output, sort_keys=True, indent=2))
    return 0 if output.get("status") not in ("blocked",) else 2


if __name__ == "__main__":
    raise SystemExit(main())
