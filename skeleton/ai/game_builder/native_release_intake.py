"""Byte-level intake of an original game's actual native desktop artifact.

The existing signed-review plane validates statements and detached signatures.
This plane checks that on-disk game source, manifest, credits, packaged binary,
build evidence and gameplay evidence actually match those statements. It does
NOT run the game, verify the compiler, certify legal rights or authorize release.

Use only locally created files and trusted private workspaces. No copyrighted
commercial executable, firmware or game asset is downloaded by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from .asset_credits import CreditsBundle
from .legal_paths import HomebrewLegalAssessment
from .plagiarism_guard import OriginalityReport
from .release_assurance import ReleaseCandidate, ReleaseReviewError

_MAX_SOURCE = 10 * 1024 * 1024
_MAX_BINARY = 256 * 1024 * 1024
_MAX_EVIDENCE = 2 * 1024 * 1024
_EXPECTED_RIGHTS = ("CREDITS.md", "THIRD_PARTY_NOTICES.txt", "material_inventory.json")
_EXPECTED_SOURCE = ("game.c", "CMakeLists.txt", "manifest.json", "legal_review.json")
_EXPECTED_ROOT = frozenset((*_EXPECTED_SOURCE, "rights"))
_NATIVE_PREFIX = {
    "windows_modern": b"MZ",
    "linux_desktop": b"\x7fELF",
}
_MACHO_HEADERS = (
    bytes.fromhex("feedface"), bytes.fromhex("cefaedfe"),
    bytes.fromhex("feedfacf"), bytes.fromhex("cffaedfe"),
    bytes.fromhex("cafebabe"), bytes.fromhex("bebafeca"),
)


class NativeIntakeError(ReleaseReviewError):
    """Missing, substituted or unsafe local native homebrew release artifacts."""


@dataclass(frozen=True, slots=True)
class NativeIntakeReceipt:
    candidate_sha256: str
    native_binary_sha256: str
    native_source_sha256: str
    rights_notices_sha256: str
    bound_world_sha256: str
    byte_verified_files: tuple[str, ...]
    intake_sha256: str
    bin_bytes: int
    file_bytes_verified: bool = True
    exhaustive_payload_inventory_verified: bool = True
    executable_structure_validated: bool = False
    compiler_execution_verified: bool = False
    emulator_or_hardware_execution_verified: bool = False
    copyrights_independently_verified: bool = False
    release_authorized: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in (
            "compiler_execution_verified", "emulator_or_hardware_execution_verified",
            "copyrights_independently_verified", "release_authorized",
        )):
            raise NativeIntakeError("artifact intake cannot certify compiler, runtime, law or release")
        if self.file_bytes_verified is not True or self.exhaustive_payload_inventory_verified is not True:
            raise NativeIntakeError("native intake receipt requires complete byte and source inventory verification")
        if self.executable_structure_validated is not False:
            raise NativeIntakeError("header checks are not executable format validation")
        if type(self.bin_bytes) is not int or self.bin_bytes < 256 or self.bin_bytes > _MAX_BINARY:
            raise NativeIntakeError("invalid native executable length")
        if not isinstance(self.byte_verified_files, tuple) or self.byte_verified_files != tuple(
            sorted((*_EXPECTED_SOURCE, *("rights/" + x for x in _EXPECTED_RIGHTS),
                    "compiled_binary", "build_evidence", "gameplay_evidence"))
        ):
            raise NativeIntakeError("native receipt has incomplete file coverage")
        for name in ("candidate_sha256", "native_binary_sha256", "native_source_sha256",
                     "rights_notices_sha256", "bound_world_sha256", "intake_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise NativeIntakeError("invalid signed artifact SHA-256 identity")

    def to_json(self) -> str:
        return json.dumps({
            "schema": "skeleton.game_builder.native_byte_intake.v1",
            "candidate_sha256": self.candidate_sha256,
            "native_binary_sha256": self.native_binary_sha256,
            "native_source_sha256": self.native_source_sha256,
            "rights_notices_sha256": self.rights_notices_sha256,
            "bound_world_sha256": self.bound_world_sha256,
            "byte_verified_files": list(self.byte_verified_files),
            "intake_sha256": self.intake_sha256,
            "bin_bytes": self.bin_bytes,
            "file_bytes_verified": True,
            "exhaustive_payload_inventory_verified": True,
            "executable_structure_validated": False,
            "compiler_execution_verified": False,
            "emulator_or_hardware_execution_verified": False,
            "copyrights_independently_verified": False,
            "release_authorized": False,
        }, sort_keys=True, indent=2) + "\n"


def _no_follow() -> int:
    value = getattr(os, "O_NOFOLLOW", 0)
    if not value:
        raise NativeIntakeError("local platform lacks race-resistant no-follow file opening")
    return value


def _open_directory(path: Path) -> int:
    """Open every ancestor through a no-follow directory descriptor."""
    path = Path(path)
    if any(part == ".." for part in path.parts) or len(path.parts) > 40:
        raise NativeIntakeError("untrusted ancestor traversal in native evidence path")
    initial = "/" if path.is_absolute() else "."
    try:
        handle = os.open(initial, os.O_RDONLY | os.O_DIRECTORY | _no_follow())
    except OSError as exc:
        raise NativeIntakeError("cannot open authorized evidence workspace") from exc
    try:
        for part in path.parts:
            if part in ("/", ".", ""):
                continue
            next_handle = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | _no_follow(), dir_fd=handle
            )
            os.close(handle)
            handle = next_handle
        return handle
    except OSError as exc:
        os.close(handle)
        raise NativeIntakeError("symlinked or missing evidence ancestor directory") from exc


def _read_bounded(path: Path, *, max_bytes: int, root_fd: int | None = None) -> bytes:
    """Open through no-follow directory handles, excluding nonregular files."""
    path = Path(path)
    if root_fd is None:
        parent_handle = _open_directory(path.parent)
        try:
            return _read_bounded(Path(path.name), max_bytes=max_bytes,
                                 root_fd=parent_handle)
        finally:
            os.close(parent_handle)
    if root_fd is not None and (
        path.is_absolute() or len(path.parts) != 1 or path.name in {"", ".", ".."}
    ):
        raise NativeIntakeError("only anchored direct child paths are accepted")
    flags = os.O_RDONLY | _no_follow() | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path if root_fd is None else path.name, flags,
                     **({} if root_fd is None else {"dir_fd": root_fd}))
    except OSError as exc:
        raise NativeIntakeError("missing, linked or inaccessible local release evidence") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > max_bytes
            or info.st_nlink != 1):
            raise NativeIntakeError("release evidence is not a private bounded regular file")
        out = bytearray()
        while len(out) <= max_bytes:
            data = os.read(fd, min(128 * 1024, max_bytes + 1 - len(out)))
            if not data:
                break
            out.extend(data)
        after = os.fstat(fd)
        if (len(out) > max_bytes or len(out) != info.st_size
            or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise NativeIntakeError("release evidence changed while being read or exceeded byte budget")
        return bytes(out)
    except OSError as exc:
        raise NativeIntakeError("release evidence failed byte-level verification") from exc
    finally:
        os.close(fd)


def _json(data: bytes, label: str) -> dict[str, object]:
    def pairs_no_dupes(pairs: list[tuple[str, object]]) -> dict[str, object]:
        mapping: dict[str, object] = {}
        for key, value in pairs:
            if key in mapping:
                raise NativeIntakeError("duplicate JSON key in " + label)
            mapping[key] = value
        return mapping

    def reject_constant(value: str) -> None:
        raise NativeIntakeError("non-finite number " + value + " in " + label)

    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=pairs_no_dupes,
                         parse_constant=reject_constant)
    except (UnicodeError, ValueError) as exc:
        raise NativeIntakeError("invalid " + label + " JSON") from exc
    if not isinstance(obj, dict):
        raise NativeIntakeError("invalid " + label + " root object")
    return obj


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _require_binary_format(data: bytes, target_platform_id: str) -> None:
    if len(data) < 256:
        raise NativeIntakeError("empty or stub binary cannot be an admitted release candidate")
    if target_platform_id in _NATIVE_PREFIX:
        if not data.startswith(_NATIVE_PREFIX[target_platform_id]):
            raise NativeIntakeError("native binary header mismatches target platform")
    elif target_platform_id == "macos_modern":
        if not any(data.startswith(header) for header in _MACHO_HEADERS):
            raise NativeIntakeError("not a Mach-O native binary for macOS")
    else:
        raise NativeIntakeError("unsupported native desktop release target")


def verify_native_release_intake(
    *, source_directory: str | Path, compiled_binary: str | Path,
    build_evidence: str | Path, gameplay_evidence: str | Path,
    candidate: ReleaseCandidate, legal: HomebrewLegalAssessment,
    originality: OriginalityReport, credits: CreditsBundle,
) -> NativeIntakeReceipt:
    """Verify real file bytes behind each cryptographically reviewed claim.

    A file that begins with MZ/ELF/Mach-O and matches the supplied hash is not
    proof that it boots. The external technical reviewer must independently
    inspect actual compilation and hardware/gameplay testing.
    """
    if (not isinstance(candidate, ReleaseCandidate)
        or not isinstance(legal, HomebrewLegalAssessment)
        or not isinstance(originality, OriginalityReport)
        or not isinstance(credits, CreditsBundle)):
        raise NativeIntakeError("typed signed-release and original-rights context required")
    if (candidate.project_id != legal.project_id
        or candidate.project_id != originality.project_id
        or candidate.project_id != credits.project_id
        or candidate.target_platform_id != legal.target_platform_id
        or candidate.target_platform_id != credits.target_platform_id
        or candidate.jurisdictions != legal.jurisdictions
        or candidate.legal_assessment_sha256 != legal.assessment_digest
        or candidate.originality_screen_sha256 != originality.screen_digest
        or candidate.world_sha256 != originality.artifact_sha256
        or candidate.rights_evidence_sha256 != legal.rights_packet_sha256
        or candidate.credits_bundle_sha256 != credits.bundle_sha256):
        raise NativeIntakeError("release candidate provenance references differ from reviewed game")
    if (not legal.design_admissible or not originality.design_admissible
        or credits.review_issues):
        raise NativeIntakeError("unresolved intellectual property rights cannot enter native intake")

    rootfd = _open_directory(Path(source_directory))
    try:
        # A correct hash of game.c says nothing about an unreviewed ROM, extra
        # object file, DLL or script planted beside it. Admit an exact manifest
        # of files, not a partial enumeration.
        if set(os.listdir(rootfd)) != _EXPECTED_ROOT:
            raise NativeIntakeError("unreviewed extra or missing native source payload")
        source = _read_bounded(Path("game.c"), max_bytes=_MAX_SOURCE, root_fd=rootfd)
        cmake = _read_bounded(Path("CMakeLists.txt"), max_bytes=_MAX_SOURCE, root_fd=rootfd)
        manifest_data = _read_bounded(Path("manifest.json"), max_bytes=_MAX_EVIDENCE, root_fd=rootfd)
        policy_data = _read_bounded(Path("legal_review.json"), max_bytes=_MAX_EVIDENCE, root_fd=rootfd)
        rights_fd = os.open("rights", os.O_RDONLY | os.O_DIRECTORY | _no_follow(),
                            dir_fd=rootfd)
        try:
            if set(os.listdir(rights_fd)) != set(_EXPECTED_RIGHTS):
                raise NativeIntakeError("unreviewed extra or missing third-party rights payload")
            rights_files = [
                _read_bounded(Path(name), max_bytes=_MAX_EVIDENCE, root_fd=rights_fd)
                for name in _EXPECTED_RIGHTS
            ]
        finally:
            os.close(rights_fd)
    except OSError as exc:
        raise NativeIntakeError("missing or symlinked reviewed credits directory") from exc
    finally:
        os.close(rootfd)

    if not (
        rights_files[0] == credits.credits_md.encode("utf-8")
        and rights_files[1] == credits.third_party_notices_txt.encode("utf-8")
        and rights_files[2] == credits.inventory_json.encode("utf-8")
    ):
        raise NativeIntakeError("on-disk credit notices are not the reviewed rights bundle")
    project_digest = _sha(source + b"\0" + cmake + b"\0" + manifest_data)
    if project_digest != candidate.native_source_sha256:
        raise NativeIntakeError("game source has been substituted after independent review")
    manifest = _json(manifest_data, "native-source")
    policy = _json(policy_data, "legal-review")
    if manifest.get("schema") != "skeleton.game_builder.native_desktop_source.v1":
        raise NativeIntakeError("unknown native game manifest schema")
    if policy.get("schema") != "skeleton.game_builder.legal_native_source.v1":
        raise NativeIntakeError("unknown legal review receipt schema")
    for field, value in (
        ("source_project_id", candidate.project_id),
        ("target_platform_id", candidate.target_platform_id),
        ("world_digest", candidate.world_sha256),
        ("source_rights_evidence_sha256", candidate.rights_evidence_sha256),
    ):
        if manifest.get(field) != value:
            raise NativeIntakeError("native source manifest differs in " + field)
    for key in ("executable_built", "releasable", "third_party_game_assets_embedded"):
        if manifest.get(key) is not False:
            raise NativeIntakeError("native source manifest asserts unsupported release state")
    for field, value in (
        ("source_project_id", candidate.project_id),
        ("target_platform_id", candidate.target_platform_id),
        ("native_source_sha256", candidate.native_source_sha256),
        ("source_rights_reference", candidate.rights_evidence_sha256),
        ("legal_assessment_digest", candidate.legal_assessment_sha256),
        ("originality_screen_digest", candidate.originality_screen_sha256),
        ("attribution_bundle_sha256", candidate.credits_bundle_sha256),
    ):
        if policy.get(field) != value:
            raise NativeIntakeError("native legal manifest differs in " + field)
    if (policy.get("plagiarism_screened") is not True
        or policy.get("originality_artifact_bound") is not True
        or policy.get("attribution_notices_embedded") is not True):
        raise NativeIntakeError("missing mandatory original-work and credits review")
    for key in ("full_release_legality_certified", "release_authorized",
                "real_toolchain_run_verified", "false_claim_of_plagiarism_free",
                "game_content_and_assets_independently_verified"):
        if policy.get(key) is not False:
            raise NativeIntakeError("native review receipt falsely asserts legal release")
    combined = _sha((
        project_digest + ":" + candidate.legal_assessment_sha256 + ":" +
        candidate.credits_bundle_sha256
    ).encode("ascii"))
    if policy.get("combined_sha256") != combined:
        raise NativeIntakeError("legal-review envelope not bound to real source and credits")

    binary = _read_bounded(Path(compiled_binary), max_bytes=_MAX_BINARY)
    _require_binary_format(binary, candidate.target_platform_id)
    if _sha(binary) != candidate.native_binary_sha256:
        raise NativeIntakeError("reviewed native executable bytes differ from actual file")
    build = _read_bounded(Path(build_evidence), max_bytes=_MAX_EVIDENCE)
    gameplay = _read_bounded(Path(gameplay_evidence), max_bytes=_MAX_EVIDENCE)
    if _sha(build) != candidate.native_build_evidence_sha256:
        raise NativeIntakeError("native build receipt is not the one submitted for review")
    if _sha(gameplay) != candidate.native_gameplay_evidence_sha256:
        raise NativeIntakeError("gameplay receipt is not the one submitted for review")
    file_ids = {
        "game.c": _sha(source),
        "CMakeLists.txt": _sha(cmake),
        "manifest.json": _sha(manifest_data),
        "legal_review.json": _sha(policy_data),
        "rights/CREDITS.md": _sha(rights_files[0]),
        "rights/THIRD_PARTY_NOTICES.txt": _sha(rights_files[1]),
        "rights/material_inventory.json": _sha(rights_files[2]),
        "compiled_binary": _sha(binary),
        "build_evidence": _sha(build),
        "gameplay_evidence": _sha(gameplay),
    }
    canonical = json.dumps({
        "schema": "skeleton.game_builder.native_byte_intake.v1",
        "candidate_sha256": candidate.digest, "files": file_ids,
        "rights_notices_sha256": credits.bundle_sha256,
    }, sort_keys=True, separators=(",", ":")).encode()
    return NativeIntakeReceipt(
        candidate_sha256=candidate.digest,
        native_binary_sha256=_sha(binary),
        native_source_sha256=project_digest,
        rights_notices_sha256=credits.bundle_sha256,
        bound_world_sha256=candidate.world_sha256,
        byte_verified_files=tuple(sorted(file_ids)),
        intake_sha256=_sha(canonical),
        bin_bytes=len(binary),
    )
