"""Fail-closed evidence for two native Sega 8-bit homebrew cartridge artifacts.

A deterministic build comparison verifies the *bytes of two separate local
files* and binds both to the original Z80 source, author-declaration digest,
hardware target and pre-rebuild intake. It does not prove that any particular
compiler was actually invoked twice: that assertion belongs to the trusted
CI process that runs the two builds. Neither matched bytes nor Git revisions
confer copyright ownership, legal release approval, or emulator boot.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .native_release_intake import _json, _open_directory, _read_bounded
from .sega_8bit_rom import validate_rom_file


_SHA = re.compile(r"^[0-9a-f]{64}$")
_REV = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_TARGETS = {"sega_master_system": ".sms", "sega_game_gear": ".gg"}
_SOURCE_FILES = ("game.c", "Makefile", "manifest.json")
_REVIEW_FALSE = (
    "native_rom_compiled", "emulator_playthrough_verified",
    "physical_hardware_verified", "release_approved",
    "rights_independently_verified", "distribution_licensed",
    "source_digest_independently_attested",
    "source_rights_independently_proven",
    "toolchain_source_authenticated",
)
_MANIFEST_FALSE = (
    "binary_compiled", "emulator_playthrough_verified",
    "physical_hardware_verified", "release_approved",
    "distribution_licensed", "third_party_game_or_firmware_redistributed",
)


class SegaBuildEvidenceError(ValueError):
    """The second cartridge cannot inherit reviewed first-build provenance."""


def _require(test: bool, message: str) -> None:
    if not test:
        raise SegaBuildEvidenceError(message)


def _canonical(data: dict[str, object]) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class SegaReproducibilityReceipt:
    """Byte-bound machine-specific double-artifact comparison result."""

    target: str
    source_sha256: str
    author_declaration_sha256: str
    world_sha256: str
    reference_replay_sha256: str
    toolchain_git_revision: str
    cartridge_sha256: str
    cartridge_bytes: int
    comparison_sha256: str
    checked_two_distinct_artifact_paths: bool = True
    exact_rom_bytes_match: bool = True
    source_and_authorship_digests_match: bool = True
    two_compiler_executions_independently_verified: bool = False
    source_rights_independently_verified: bool = False
    gameplay_execution_verified: bool = False
    real_console_hardware_verified: bool = False
    developer_toolchain_authenticity_proven: bool = False
    publication_licensed: bool = False

    def __post_init__(self) -> None:
        if self.target not in _TARGETS:
            raise SegaBuildEvidenceError("unknown native Sega homebrew target")
        if (not isinstance(self.toolchain_git_revision, str)
            or not _REV.fullmatch(self.toolchain_git_revision)):
            raise SegaBuildEvidenceError("untrusted or incomplete Git toolchain revision")
        for name in (
            "source_sha256", "author_declaration_sha256", "world_sha256",
            "reference_replay_sha256", "cartridge_sha256", "comparison_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA.fullmatch(value):
                raise SegaBuildEvidenceError("invalid content-addressed build evidence digest")
        if type(self.cartridge_bytes) is not int or self.cartridge_bytes != 32768:
            raise SegaBuildEvidenceError("only authentic 32 KiB SMS/GG native layouts admitted")
        if any(getattr(self, name) is not True for name in (
            "checked_two_distinct_artifact_paths",
            "exact_rom_bytes_match", "source_and_authorship_digests_match",
        )):
            raise SegaBuildEvidenceError("reproducibility evidence must verify two actual files")
        if any(getattr(self, name) is not False for name in (
            "two_compiler_executions_independently_verified",
            "source_rights_independently_verified",
            "gameplay_execution_verified", "real_console_hardware_verified",
            "developer_toolchain_authenticity_proven", "publication_licensed",
        )):
            raise SegaBuildEvidenceError("byte equality cannot certify tool execution, gameplay or rights")
        if self.comparison_sha256 != sha256(_canonical(self._core())).hexdigest():
            raise SegaBuildEvidenceError("reproducible cartridge receipt not content-bound")

    def _core(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.sega_reproducibility.v1",
            "target": self.target,
            "source_sha256": self.source_sha256,
            "author_declaration_sha256": self.author_declaration_sha256,
            "world_sha256": self.world_sha256,
            "reference_replay_sha256": self.reference_replay_sha256,
            "toolchain_git_revision": self.toolchain_git_revision,
            "cartridge_sha256": self.cartridge_sha256,
            "cartridge_bytes": self.cartridge_bytes,
            "checked_two_distinct_artifact_paths": True,
            "exact_rom_bytes_match": True,
            "source_and_authorship_digests_match": True,
            "two_compiler_executions_independently_verified": False,
            "source_rights_independently_verified": False,
            "gameplay_execution_verified": False,
            "real_console_hardware_verified": False,
            "developer_toolchain_authenticity_proven": False,
            "publication_licensed": False,
        }

    def public_receipt(self) -> dict[str, object]:
        return {**self._core(), "comparison_sha256": self.comparison_sha256}


def verify_separate_authoring_runs(
    first_source: str | Path, second_source: str | Path, *,
    target: str, expected_source_sha256: str,
) -> dict[str, object]:
    """Confirm two independent source directories hold byte-identical authored code.

    This compares a second actual game generation to the original authored
    output. It cannot prove that two generators were genuinely executed:
    only CI's trusted invocation transcript can establish that fact.
    """
    _require(target in _TARGETS, "unknown native homebrew source target")
    _require(isinstance(expected_source_sha256, str)
             and bool(_SHA.fullmatch(expected_source_sha256)),
             "expected independently measured source digest must be SHA-256")
    _require(Path(first_source) != Path(second_source),
             "the same source path cannot represent two generation runs")

    roots: list[tuple[str, list[bytes]]] = []
    for path,allow_build in ((first_source,True),(second_source,False)):
        rootfd = _open_directory(Path(path))
        try:
            found = set(os.listdir(rootfd))
            approved = set(_SOURCE_FILES)
            if allow_build and "build" in found:
                build_stat = os.stat("build", dir_fd=rootfd, follow_symlinks=False)
                _require(stat.S_ISDIR(build_stat.st_mode),
                         "native build output directory cannot be a link")
                approved.add("build")
            _require(found==approved,
                     "original source regeneration contains unreviewed files")
            content = [
                _read_bounded(Path(filename),max_bytes=1024*1024,root_fd=rootfd)
                for filename in _SOURCE_FILES
            ]
        finally:
            os.close(rootfd)
        digest=sha256(b"\0".join(content)).hexdigest()
        _require(digest==expected_source_sha256,
                 "independent source-generation runs differ from reviewed game bytes")
        roots.append((digest,content))
        manifest=_json(content[2],"originally generated Sega source")
        _require(
            manifest.get("schema")=="skeleton.game_builder.native_sega8_source.v1"
            and manifest.get("platform")==target
            and manifest.get("target_rom_suffix")==_TARGETS[target][1:],
            "the regenerated source is not for the same Sega console",
        )
        _require(all(manifest.get(k) is False for k in _MANIFEST_FALSE),
                 "authored game source contains pre-certified legal or hardware claims")
    _require(
        roots[0][0]==roots[1][0]==expected_source_sha256
        and roots[0][1]==roots[1][1],
        "independent source-generation runs differ from the reviewed game",
    )
    return {
        "schema":"skeleton.game_builder.sega_source_regeneration.v1",
        "target":target,
        "identical_authoring_source_sha256":expected_source_sha256,
        "actual_source_files_compared":list(_SOURCE_FILES),
        "identical_source_bytes":True,
        "generator_invocations_independently_attested":False,
        "author_copyright_title_independently_proven":False,
        "release_authorized":False,
    }


def verify_rebuilt_sega_cartridge(
    *, target: str, source_directory: str | Path,
    first_cartridge: str | Path, rebuilt_cartridge: str | Path,
    first_build_evidence: dict[str, object],
    expected_source_sha256: str, expected_author_declaration_sha256: str,
    toolchain_git_revision: str,
) -> SegaReproducibilityReceipt:
    """Verify two separately stored ROM files and the exact original source.

    Requires an externally provided pre-rebuild checksum of the *source* and
    author statement. This function cannot prove who supplied the checksum.
    A trustworthy CI runner must execute the builds and capture both outputs.
    """
    _require(target in _TARGETS, "unknown original Sega console")
    _require(isinstance(first_build_evidence, dict),
             "first-build receipt must be a parsed JSON object")
    _require(isinstance(expected_source_sha256, str)
             and bool(_SHA.fullmatch(expected_source_sha256)),
             "missing original pre-build source digest")
    _require(isinstance(expected_author_declaration_sha256, str)
             and bool(_SHA.fullmatch(expected_author_declaration_sha256)),
             "missing original author declaration digest")
    _require(isinstance(toolchain_git_revision, str)
             and bool(_REV.fullmatch(toolchain_git_revision)),
             "missing full pinned Git toolchain revision")
    first = Path(first_cartridge)
    rebuilt = Path(rebuilt_cartridge)
    _require(first != rebuilt, "two copies at distinct paths are required for comparison")
    _require(first.name.endswith(_TARGETS[target])
             and rebuilt.name.endswith(_TARGETS[target]),
             "Sega binary file extension does not match the selected hardware")

    rootfd = _open_directory(Path(source_directory))
    try:
        root_items = set(os.listdir(rootfd))
        _require(root_items == {*_SOURCE_FILES, "build"},
                 "Sega build source tree contains missing or unreviewed extra payloads")
        build_info = os.stat("build", dir_fd=rootfd, follow_symlinks=False)
        _require(stat.S_ISDIR(build_info.st_mode),
                 "native build folder cannot be a symlink or regular file")
        source_parts = [
            _read_bounded(Path(filename), max_bytes=1024 * 1024, root_fd=rootfd)
            for filename in _SOURCE_FILES
        ]
    finally:
        os.close(rootfd)
    source_sha = sha256(b"\0".join(source_parts)).hexdigest()
    _require(source_sha == expected_source_sha256,
             "source changed after first build and before reproducibility check")
    manifest = _json(source_parts[2], "Sega original source manifest")
    _require(
        manifest.get("schema") == "skeleton.game_builder.native_sega8_source.v1"
        and manifest.get("platform") == target
        and manifest.get("target_rom_suffix") == _TARGETS[target][1:],
        "native source manifest hardware identity changed",
    )
    for flag in _MANIFEST_FALSE:
        _require(manifest.get(flag) is False,
                 "original source manifest forged release or hardware acceptance")
    for name in ("world_digest", "reference_safe_replay_digest",
                 "source_rights_evidence_sha256"):
        _require(isinstance(manifest.get(name), str)
                 and bool(_SHA.fullmatch(manifest[name])),
                 "required original game provenance digest absent")
    _require(
        manifest["source_rights_evidence_sha256"] == expected_author_declaration_sha256,
        "author's original work evidence differs from the reviewed game",
    )

    evidence = first_build_evidence
    _require(
        evidence.get("schema") == "skeleton.game_builder.sega8_actual_compilation_evidence.v1"
        and evidence.get("target") == target
        and evidence.get("toolchain_revision") == toolchain_git_revision
        and evidence.get("source_sha256") == source_sha
        and evidence.get("source_rights_evidence_sha256") == expected_author_declaration_sha256
        and evidence.get("original_world_digest") == manifest["world_digest"]
        and evidence.get("reference_safe_replay_digest") == manifest["reference_safe_replay_digest"],
        "first-build receipt is not bound to this source, author, world or target",
    )
    for flag in _REVIEW_FALSE:
        _require(evidence.get(flag) is False,
                 "first-build receipt forged execution, rights or independent authority")
    _require(evidence.get("real_rom_structure_verified") is True
             and evidence.get("rom_header_checksum_verified") is True
             and evidence.get("source_digest_matches_expected") is True
             and evidence.get("source_authorship_hash_matches_expected") is True,
             "first build lacks actual structure and source/author byte checks")
    _require(
        evidence.get("toolchain_revision_hash_algorithm")
        == ("git-sha1" if len(toolchain_git_revision) == 40 else "git-sha256"),
        "toolchain Git revision algorithm does not match recorded commit",
    )
    first_verified = validate_rom_file(first, target)
    rebuilt_verified = validate_rom_file(rebuilt, target)
    _require(
        first_verified["sha256"] == evidence.get("rom_sha256")
        and rebuilt_verified["sha256"] == first_verified["sha256"],
        "separate Sega cartridge files differ from the reviewed original build",
    )
    _require(
        first_verified["bytes"] == rebuilt_verified["bytes"] == evidence.get("rom_size") == 32768,
        "first/rebuilt native cartridge file lengths are not identical",
    )
    # All 32 KiB must agree, not only the weak additive Sega header checksum.
    first_bytes = _read_bounded(first, max_bytes=32768)
    rebuilt_bytes = _read_bounded(rebuilt, max_bytes=32768)
    _require(
        first_bytes == rebuilt_bytes
        and sha256(first_bytes).hexdigest() == first_verified["sha256"]
        and sha256(rebuilt_bytes).hexdigest() == rebuilt_verified["sha256"],
        "native ROM bytes changed between structural intake and reproducibility comparison",
    )
    core = {
        "schema": "skeleton.game_builder.sega_reproducibility.v1",
        "target": target,
        "source_sha256": source_sha,
        "author_declaration_sha256": expected_author_declaration_sha256,
        "world_sha256": manifest["world_digest"],
        "reference_replay_sha256": manifest["reference_safe_replay_digest"],
        "toolchain_git_revision": toolchain_git_revision,
        "cartridge_sha256": first_verified["sha256"],
        "cartridge_bytes": 32768,
        "checked_two_distinct_artifact_paths": True,
        "exact_rom_bytes_match": True,
        "source_and_authorship_digests_match": True,
        "two_compiler_executions_independently_verified": False,
        "source_rights_independently_verified": False,
        "gameplay_execution_verified": False,
        "real_console_hardware_verified": False,
        "developer_toolchain_authenticity_proven": False,
        "publication_licensed": False,
    }
    return SegaReproducibilityReceipt(
        target=target,
        source_sha256=source_sha,
        author_declaration_sha256=expected_author_declaration_sha256,
        world_sha256=manifest["world_digest"],
        reference_replay_sha256=manifest["reference_safe_replay_digest"],
        toolchain_git_revision=toolchain_git_revision,
        cartridge_sha256=first_verified["sha256"],
        cartridge_bytes=32768,
        comparison_sha256=sha256(_canonical(core)).hexdigest(),
    )
