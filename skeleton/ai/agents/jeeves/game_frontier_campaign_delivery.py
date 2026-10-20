"""Deterministic, source-bound delivery of original Jeeves game projects.

Seven real candidate-production operations: admission, inventory, packaging,
independent verification, disk recovery rehearsal/restoration, delta comparison,
and release-blocking provenance. No model authority or legal clearance is inferred.
All ZIP entries are STORED for cross-zlib byte reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Mapping
from unicodedata import normalize
from zipfile import BadZipFile, ZipFile, ZipInfo, ZIP_STORED

from .game_frontier_expedition import ExpeditionError

_SCHEMA = "skeleton.game.campaign_delivery.v1"
_EPOCH = (1980, 1, 1, 0, 0, 0)
_MODE = 0o100644 << 16
_BAD = set('<>:"|?*\\\x00')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + str(n) for prefix in ("COM", "LPT") for n in range(1, 10)
}


@dataclass(frozen=True, slots=True)
class DeliveryPolicy:
    max_files: int = 8192
    max_file_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 128 * 1024 * 1024
    max_path_chars: int = 220

    def __post_init__(self) -> None:
        limits = (
            (self.max_files, 1, 16384),
            (self.max_file_bytes, 1, 64 * 1024 * 1024),
            (self.max_total_bytes, 1, 256 * 1024 * 1024),
            (self.max_path_chars, 16, 255),
        )
        if any(type(value) is not int or not low <= value <= high
               for value, low, high in limits):
            raise ExpeditionError("delivery resource budget invalid")
        if self.max_total_bytes < self.max_file_bytes:
            raise ExpeditionError("delivery total budget below individual file budget")


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _seal(obj: object) -> str:
    return _sha(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("utf-8"))


def _digest(value: object, field: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ExpeditionError("delivery " + field + " digest invalid")
    return value


def _scope(project_id: str, gdd_digest: str, world_digest: str) -> None:
    if type(project_id) is not str or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", project_id):
        raise ExpeditionError("delivery project identifier invalid")
    _digest(gdd_digest, "GDD")
    _digest(world_digest, "world")


def _path(name: str, policy: DeliveryPolicy) -> str:
    if (type(name) is not str or not name or len(name) > policy.max_path_chars
            or normalize("NFC", name) != name or name.startswith("/")
            or any(ch in _BAD or ord(ch) < 32 for ch in name)
            or "//" in name or PurePosixPath(name).as_posix() != name):
        raise ExpeditionError("delivery unsafe project path")
    parts = name.split("/")
    if any(
        part in ("", ".", "..") or part.endswith((".", " "))
        or part.split(".")[0].upper() in _RESERVED or part.startswith(" ")
        for part in parts
    ):
        raise ExpeditionError("delivery unsafe project path")
    return name


def _admit(files: Mapping[str, str], policy: DeliveryPolicy) -> tuple[tuple[str, bytes], ...]:
    if (not isinstance(files, Mapping) or not files
            or len(files) > policy.max_files):
        raise ExpeditionError("delivery source file count invalid")
    result = []
    casefolded = set()
    total = 0
    for raw_name, content in files.items():
        name = _path(raw_name, policy)
        folded = name.casefold()
        if folded in casefolded:
            raise ExpeditionError("delivery case-fold path collision")
        casefolded.add(folded)
        if type(content) is not str:
            raise ExpeditionError("delivery requires UTF-8 authored source")
        try:
            data = content.encode("utf-8")
        except UnicodeError as exc:
            raise ExpeditionError("delivery source UTF-8 encoding invalid") from exc
        if len(data) > policy.max_file_bytes:
            raise ExpeditionError("delivery individual file byte budget exceeded")
        total += len(data)
        if total > policy.max_total_bytes:
            raise ExpeditionError("delivery total byte budget exceeded")
        result.append((name, data))
    return tuple(sorted(result, key=lambda item: item[0]))


def _inventory(files: tuple[tuple[str, bytes], ...]) -> list[dict]:
    return [{"path": name, "bytes": len(data), "sha256": _sha(data)}
            for name, data in files]


def _pack(files: tuple[tuple[str, bytes], ...]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED, allowZip64=False) as archive:
        for name, data in files:
            info = ZipInfo(name, date_time=_EPOCH)
            info.create_system = 3
            info.external_attr = _MODE
            info.compress_type = ZIP_STORED
            archive.writestr(info, data)
    return output.getvalue()


def _decode(archive: bytes, inventory: list[dict], policy: DeliveryPolicy) -> tuple[tuple[str, bytes], ...]:
    if type(archive) is not bytes or len(archive) > policy.max_total_bytes + 8192 * policy.max_files:
        raise ExpeditionError("delivery archive byte budget exceeded")
    expected = [row["path"] for row in inventory]
    if len(expected) != len(set(expected)) or len(expected) > policy.max_files:
        raise ExpeditionError("delivery inventory duplicate or over budget")
    result = []
    total = 0
    try:
        with ZipFile(BytesIO(archive), "r") as zipped:
            infos = zipped.infolist()
            if zipped.comment or len(infos) != len(expected) or [i.filename for i in infos] != expected:
                raise ExpeditionError("delivery ZIP membership/order mismatch")
            for info, row in zip(infos, inventory):
                _path(info.filename, policy)
                if (info.is_dir() or info.compress_type != ZIP_STORED or
                        info.flag_bits & 1 or info.date_time != _EPOCH or
                        info.create_system != 3 or info.external_attr != _MODE or
                        info.extra or info.comment or info.file_size != row["bytes"] or
                        info.file_size > policy.max_file_bytes):
                    raise ExpeditionError("delivery ZIP entry metadata mismatch")
                total += info.file_size
                if total > policy.max_total_bytes:
                    raise ExpeditionError("delivery ZIP expansion exceeds budget")
                with zipped.open(info, "r") as source:
                    data = source.read(policy.max_file_bytes + 1)
                if len(data) != info.file_size or _sha(data) != row["sha256"]:
                    raise ExpeditionError("delivery extracted byte digest mismatch")
                result.append((info.filename, data))
    except (BadZipFile, OSError, EOFError, ValueError, RuntimeError) as exc:
        raise ExpeditionError("delivery corrupt ZIP payload") from exc
    return tuple(result)


def _check_report(report: dict) -> None:
    if type(report) is not dict or report.get("schema") != _SCHEMA:
        raise ExpeditionError("delivery report schema invalid")
    sealed = report.get("report_sha256")
    if _digest(sealed, "report") != _seal({k: v for k, v in report.items()
                                          if k != "report_sha256"}):
        raise ExpeditionError("delivery report has been modified")
    _scope(report["project"], report["gdd_digest"], report["world_digest"])
    if (report.get("production_release_approved") is not False
            or report.get("copyright_cleared") is not False
            or report.get("native_gameplay_attested") is not False):
        raise ExpeditionError("delivery cannot forge release attestations")


def _rehearse(files: tuple[tuple[str, bytes], ...]) -> str:
    """Really write/read restored files in an isolated directory, not just in RAM."""
    with tempfile.TemporaryDirectory(prefix="skeleton-game-recovery-") as location:
        root = Path(location)
        for name, data in files:
            target = root.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data)
        recovered = []
        for name, expected in files:
            target = root.joinpath(*name.split("/"))
            if not target.is_file():
                raise ExpeditionError("delivery recovery rehearsal missing file")
            data = target.read_bytes()
            if data != expected:
                raise ExpeditionError("delivery recovery rehearsal diverged")
            recovered.append({"path": name, "sha256": _sha(data)})
        return _seal(recovered)


def _journal(project: str, world: str, sources: list[dict],
             archive_digest: str, recovery_digest: str) -> list[dict]:
    stages = (
        ("admission", _seal([row["path"] for row in sources])),
        ("inventory", _seal(sources)),
        ("deterministic_zip", archive_digest),
        ("independent_unpack", _seal(sources)),
        ("disk_recovery_rehearsal", recovery_digest),
        ("delta_comparison_ready", _seal({"project": project, "world": world})),
        ("release_fail_closed", _seal({"release": False, "native": False,
                                       "copyright": False})),
    )
    previous = _seal({"project": project, "world": world, "genesis": _SCHEMA})
    journal = []
    for sequence, (stage, result) in enumerate(stages, 1):
        row = {"sequence": sequence, "stage": stage,
               "input_head": previous, "result_sha256": result}
        row["receipt_sha256"] = _seal(row)
        journal.append(row)
        previous = row["receipt_sha256"]
    return journal


def prepare_campaign_bundle(
    files: Mapping[str, str], *, project_id: str, gdd_digest: str,
    world_digest: str, policy: DeliveryPolicy = DeliveryPolicy(),
) -> dict:
    """Execute all seven real checks and return replayable ZIP + evidence."""
    if not isinstance(policy, DeliveryPolicy):
        raise ExpeditionError("delivery policy type invalid")
    _scope(project_id, gdd_digest, world_digest)
    admitted = _admit(files, policy)
    source_records = _inventory(admitted)
    packed = _pack(admitted)
    unpacked = _decode(packed, source_records, policy)
    if unpacked != admitted:
        raise ExpeditionError("delivery reconstructed source differs")
    recovered = _rehearse(unpacked)
    report = {
        "schema": _SCHEMA, "project": project_id, "gdd_digest": gdd_digest,
        "world_digest": world_digest, "file_count": len(admitted),
        "source_bytes": sum(len(data) for _, data in admitted),
        "files": source_records, "inventory_sha256": _seal(source_records),
        "bundle_sha256": _sha(packed), "disk_recovery_sha256": recovered,
        "zip_algorithm": "ZIP_STORED_portable", "source_authenticated": False,
        "native_gameplay_attested": False, "copyright_cleared": False,
        "production_release_approved": False,
        "journal": _journal(project_id, world_digest, source_records,
                            _sha(packed), recovered),
    }
    report["report_sha256"] = _seal(report)
    return {"archive": packed, "report": report}


def verify_campaign_bundle(
    archive: bytes, report: dict, *, original_files: Mapping[str, str] | None = None,
    policy: DeliveryPolicy = DeliveryPolicy(),
) -> dict:
    """Independently decode, hash, and optionally compare every original source byte."""
    _check_report(report)
    if _sha(archive) != report["bundle_sha256"]:
        raise ExpeditionError("delivery archive fingerprint differs")
    rows = report["files"]
    if type(rows) is not list or len(rows) != report["file_count"]:
        raise ExpeditionError("delivery inventory count differs")
    if _seal(rows) != report["inventory_sha256"]:
        raise ExpeditionError("delivery inventory receipt differs")
    decoded = _decode(archive, rows, policy)
    if (sum(len(data) for _, data in decoded) != report["source_bytes"]
            or _inventory(decoded) != rows):
        raise ExpeditionError("delivery replay inventory differs")
    if original_files is not None and _admit(original_files, policy) != decoded:
        raise ExpeditionError("delivery archive differs from canonical source")
    if _journal(report["project"], report["world_digest"], rows,
                report["bundle_sha256"], report["disk_recovery_sha256"]) != report["journal"]:
        raise ExpeditionError("delivery seven-stage receipt chain differs")
    return {"verified": True, "files": len(decoded),
            "archive_sha256": report["bundle_sha256"],
            "release_approved": False}


def restore_campaign_bundle(
    archive: bytes, report: dict, destination: Path, *,
    policy: DeliveryPolicy = DeliveryPolicy(),
) -> dict:
    """Verify first; atomically publish new restored project without overwriting."""
    verify_campaign_bundle(archive, report, policy=policy)
    if not isinstance(destination, Path):
        raise ExpeditionError("delivery restore destination must be a path")
    if destination.exists() or destination.is_symlink():
        raise ExpeditionError("delivery restore refuses existing destination")
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ExpeditionError("delivery restore parent must exist and not be a symlink")
    decoded = _decode(archive, report["files"], policy)
    with tempfile.TemporaryDirectory(prefix=".skeleton-restore-", dir=parent) as scratch:
        staged = Path(scratch) / "project"
        staged.mkdir()
        for name, data in decoded:
            path = staged.joinpath(*name.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
        if _rehearse(tuple((name, staged.joinpath(*name.split("/")).read_bytes())
                          for name, _ in decoded)) != report["disk_recovery_sha256"]:
            raise ExpeditionError("delivery prepublication recovery differs")
        # Rename on the same filesystem; never replace an existing destination.
        if destination.exists() or destination.is_symlink():
            raise ExpeditionError("delivery restore destination raced")
        os.rename(staged, destination)
    return {"restored": True, "files": len(decoded),
            "archive_sha256": report["bundle_sha256"]}


def compare_campaign_bundles(previous: dict, current: dict) -> dict:
    """Content-aware candidate delta, never an implicit destructive migration."""
    _check_report(previous)
    _check_report(current)
    if (previous["project"], previous["gdd_digest"]) != (
            current["project"], current["gdd_digest"]):
        raise ExpeditionError("delivery compare mixes project or canonical GDD")
    before = {r["path"]: r["sha256"] for r in previous["files"]}
    after = {r["path"]: r["sha256"] for r in current["files"]}
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    modified = sorted(k for k in before.keys() & after.keys()
                      if before[k] != after[k])
    unchanged = len(before.keys() & after.keys()) - len(modified)
    result = {"schema": "skeleton.game.campaign_delivery_delta.v1",
              "previous": previous["report_sha256"],
              "current": current["report_sha256"],
              "added": added, "removed": removed, "modified": modified,
              "unchanged": unchanged, "requires_explicit_migration": bool(removed),
              "production_release_approved": False}
    result["delta_sha256"] = _seal(result)
    return result


def publish_campaign_bundle(archive: bytes, destination: Path) -> dict:
    """Create a ZIP only once; cross-filesystem overwrite is never permitted."""
    if not isinstance(destination, Path) or destination.suffix.lower() != ".zip":
        raise ExpeditionError("delivery output must be a .zip path")
    parent = destination.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ExpeditionError("delivery ZIP parent must exist and not be a symlink")
    if destination.exists() or destination.is_symlink():
        raise ExpeditionError("delivery ZIP refuses overwrite")
    with tempfile.NamedTemporaryFile(dir=parent, prefix=".skeleton-zip-",
                                     suffix=".tmp", delete=False) as staged:
        scratch = Path(staged.name)
        try:
            staged.write(archive)
            staged.flush()
            os.fsync(staged.fileno())
        except BaseException:
            scratch.unlink(missing_ok=True)
            raise
    try:
        # Hard-link creation fails instead of replacing existing destination.
        os.link(scratch, destination)
    except FileExistsError as exc:
        raise ExpeditionError("delivery ZIP destination raced") from exc
    finally:
        scratch.unlink(missing_ok=True)
    return {"published": True, "path": str(destination),
            "archive_sha256": _sha(archive), "bytes": len(archive)}
