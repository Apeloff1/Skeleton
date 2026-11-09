"""Operator-only native libretro multi-file media first-boot and rewind gate.

Accepts explicit, lawfully held *local* media paths and SHA256. Builds the
same governed GameContentReference/GameContentBundle used by the real native
host (including CUE/BIN, GDI, M3U, CHD/ISO when accepted by the catalog).
Streams large files into sandbox-private content roots; never downloads
ROMs, bypasses BIOS approval, or reads any media into a giant memory buffer.

Hardware/media compatibility is proved ONLY by an executed approved native
core and exact independent first-frame/control/savestate replay receipts.
No automatic background CI triggers or production model promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skeleton.jeeves.game_emulator_catalog import (
    GameContentBundle, GameContentReference, GameEmulatorRegistry,
    MAX_STREAM_CHUNK_BYTES, MAX_REFERENCED_FILE_BYTES,
)
from skeleton.jeeves.game_emulator_host import create_emulator_environment
from scripts.audit_game_emulator_first_boot import FirstBootError, _read, _digest

SCHEMA = "skeleton.game.approved_native_disc_first_boot_matrix.v1"
REPORT_SCHEMA = "skeleton.game.approved_native_disc_first_boot_report.v1"
MAX_CASES = 8
MAX_FILES_PER_CASE = 16
MAX_MANIFEST_BYTES = 256 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
PREFIX_CAP = 65536
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


class DiscAcceptanceError(FirstBootError):
    pass


def _sha256_literal(value: object) -> str:
    if (
        type(value) is not str or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise DiscAcceptanceError("exact lowercase hex SHA256 for every media artifact required")
    return value


def _admitted_path(raw: str, size: int, sha: str) -> Path:
    if (
        type(raw) is not str or not 1 <= len(raw) <= 4096
        or not raw.startswith("/") or "\x00" in raw
        or type(size) is not int or not 1 <= size <= MAX_REFERENCED_FILE_BYTES
    ):
        raise DiscAcceptanceError("bounded absolute local file path and admitted size required")
    path = Path(raw)
    if path.is_symlink() or not path.is_absolute() or any(
        parent.is_symlink() for parent in path.parents
    ):
        raise DiscAcceptanceError("symlinked file or parent directory is not a safe local media source")
    info = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(info.st_mode) or info.st_size != size
        or info.st_mode & stat.S_IWOTH
    ):
        raise DiscAcceptanceError("media source is not a bounded regular non-world-writable file")
    _sha256_literal(sha)
    return path


def _validate_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply exactly the same case/rights bounds to CLI and programmatic calls."""
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise DiscAcceptanceError("disc media case count outside finite 1..8 budget")
    identities = set()
    for case in cases:
        if (
            not isinstance(case, dict)
            or set(case) != {"core_id", "target_id", "entrypoint", "files"}
            or any(
                type(case.get(key)) is not str or not 1 <= len(case[key]) <= 128
                for key in ("core_id", "target_id", "entrypoint")
            )
            or not isinstance(case["files"], list)
            or not 1 <= len(case["files"]) <= MAX_FILES_PER_CASE
        ):
            raise DiscAcceptanceError("exact core, target, entrypoint and 1..16 media files required")
        names = set()
        aggregate = 0
        for file in case["files"]:
            if (
                not isinstance(file, dict)
                or set(file) != {"name", "path", "size_bytes", "sha256"}
                or type(file["name"]) is not str
                or not 1 <= len(file["name"]) <= 256
            ):
                raise DiscAcceptanceError("media files must supply exact name, local path, byte size and SHA")
            # GameContentReference further applies the current canonical
            # relative filename checks, including aliases and traversal.
            _admitted_path(file["path"], file["size_bytes"], file["sha256"])
            if file["name"].casefold() in names:
                raise DiscAcceptanceError("normalized aliases cannot inflate media evidence")
            names.add(file["name"].casefold())
            aggregate += file["size_bytes"]
        if aggregate > MAX_TOTAL_BYTES:
            raise DiscAcceptanceError("disc media bytes exceed finite 4-GiB case budget")
        if case["entrypoint"].casefold() not in names:
            raise DiscAcceptanceError("disc entrypoint must identify supplied exact file")
        key = (
            case["core_id"], case["target_id"], case["entrypoint"],
            tuple(sorted((f["name"], f["sha256"]) for f in case["files"])),
        )
        if key in identities:
            raise DiscAcceptanceError("duplicate native disc media case cannot inflate core readiness")
        identities.add(key)
    return cases


def _manifest(path: Path) -> list[dict[str, Any]]:
    source = json.loads(_read(path, MAX_MANIFEST_BYTES))
    if not isinstance(source, dict) or set(source) != {"schema_version", "cases"}:
        raise DiscAcceptanceError("disc first boot requires exact typed manifest root")
    if source["schema_version"] != SCHEMA:
        raise DiscAcceptanceError("unsupported approved disc media manifest schema")
    return _validate_cases(source["cases"])


def _prefix(path: Path, size: int, sha: str) -> bytes:
    # Opening with O_NOFOLLOW and fstat prevents trusting a renamed symlink
    # or accidentally ingesting special devices. Full content is verified
    # when the worker later streams it through GameContentBundle.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as reader:
        before = os.fstat(reader.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != size:
            raise DiscAcceptanceError("local disc media size changed before prefix admission")
        part = reader.read(min(size, PREFIX_CAP))
        after = os.fstat(reader.fileno())
        if (
            len(part) != min(size, PREFIX_CAP)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise DiscAcceptanceError("media source changed during prefix admission")
        if len(part) == size and hashlib.sha256(part).hexdigest() != sha:
            raise DiscAcceptanceError("small media descriptor digest differs before source admission")
        return part


def _media_bundle(
    case: dict[str, Any],
) -> tuple[GameContentBundle, Any, dict[str, str]]:
    local = {}
    referenced = {}
    for index, row in enumerate(case["files"]):
        path = _admitted_path(row["path"], row["size_bytes"], row["sha256"])
        identity = f"media-{index:02d}"
        if identity in local:
            raise DiscAcceptanceError("reused physical artifact reader identity")
        local[identity] = (path, row["size_bytes"], row["sha256"])
        referenced[row["name"]] = GameContentReference(
            row["name"], row["size_bytes"], row["sha256"], identity,
            _prefix(path, row["size_bytes"], row["sha256"]),
        )
    contents = {
        "operator_media_entrypoint": case["entrypoint"],
        "files": sorted(
            ({"name": r["name"], "size_bytes": r["size_bytes"], "sha256": r["sha256"]}
             for r in case["files"]),
            key=lambda row: row["name"],
        ),
    }
    bundle = GameContentBundle(case["entrypoint"], referenced, _digest(contents))

    def reader(source: GameContentReference):
        if source.artifact_ref not in local:
            raise DiscAcceptanceError("streamed native media artifact lacks declared local authority")
        path, size, sha = local[source.artifact_ref]
        if (
            source.size_bytes != size or source.sha256 != sha
            or source.name not in referenced
            or referenced[source.name] != source
        ):
            raise DiscAcceptanceError("media reader source does not match exact case authority")
        fd = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(fd, "rb") as stream:
            first = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(first.st_mode)
                or first.st_size != size or first.st_mode & stat.S_IWOTH
            ):
                raise DiscAcceptanceError("streamed media has changed its local file identity")
            length, digest = 0, hashlib.sha256()
            while length < size:
                block = stream.read(min(MAX_STREAM_CHUNK_BYTES, size - length))
                if not block:
                    break
                length += len(block)
                digest.update(block)
                yield block
            last = os.fstat(stream.fileno())
            listed = os.stat(path, follow_symlinks=False)
            ident = lambda info: (
                info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns,
            )
            if (
                length != size or digest.hexdigest() != sha
                or ident(first) != ident(last) or ident(last) != ident(listed)
                or not stat.S_ISREG(listed.st_mode)
            ):
                raise DiscAcceptanceError("actual streamed media differs from source SHA or safe file metadata")

    return bundle, reader, {name: ref.sha256 for name, ref in referenced.items()}


def _run_case(case: dict[str, Any], registry_digest: str, timeout: float) -> dict[str, Any]:
    bundle, reader, source_hashes = _media_bundle(case)
    environment = create_emulator_environment(
        "emulator:" + case["target_id"],
        core_id=case["core_id"],
        expected_registry_digest=registry_digest,
        content=bundle, reader=reader,
        max_steps=8, frames_per_step=1,
        timeout_seconds=timeout,
    )
    try:
        reset = environment.reset(seed=0)
        frame = environment.preview()
        if (
            not isinstance(frame, dict)
            or frame.get("render_kind") != "actual_native_frame_preview"
            or type(frame.get("source_pixel_digest")) is not str
            or len(frame["source_pixel_digest"]) != 64
        ):
            raise DiscAcceptanceError("approved native disc core did not emit actual first frame")
        neutral = environment.step("idle")
        snapshot = environment.snapshot()
        acted = environment.step("a")
        ahead = environment.snapshot()
        rewound = environment.restore(snapshot)
        if rewound != neutral.observation:
            raise DiscAcceptanceError("actual native disc source observation changed after core rewind")
        repeated = environment.step("a")
        again = environment.snapshot()
        if (
            acted.observation != repeated.observation
            or acted.reward_components != repeated.reward_components
            or acted.transition_digest != repeated.transition_digest
            or ahead["snapshot_digest"] != again["snapshot_digest"]
        ):
            raise DiscAcceptanceError("native disc core failed exact gameplay and audio savestate replay")
        result = {
            "core_id": case["core_id"],
            "target_id": case["target_id"],
            "entrypoint": bundle.entrypoint,
            "actual_content_bundle_digest": bundle.bundle_digest,
            "actual_source_manifest_digest": bundle.source_digest,
            "source_file_shas": source_hashes,
            "actual_emulator_environment_digest": environment.spec.environment_digest,
            "approved_core_library_sha256": environment.core.library_sha256,
            "approved_core_firmware_digest": environment.core.firmware_digest,
            "registry_digest": registry_digest,
            "first_frame_sha256": frame["source_pixel_digest"],
            "source_neutral_observation": reset,
            "actual_controller_steps": 3,
            "replayed_real_action_digest": repeated.transition_digest,
            "before_rewind_snapshot_digest": ahead["snapshot_digest"],
            "after_rewind_snapshot_digest": again["snapshot_digest"],
            "actual_native_multi_file_disc_boot": True,
            "actual_savestate_replay_passed": True,
            "independent_disc_hardware_accuracy_certified": False,
            "lawful_source_rights_independently_audited": False,
            "production_jeeves_weights_updated": 0,
        }
        result["receipt_digest"] = _digest(result)
        return result
    finally:
        environment.close()


def run_matrix(cases: list[dict[str, Any]], *, rights_acknowledged: bool, timeout: float = 5.0) -> dict[str, Any]:
    if (
        rights_acknowledged is not True
        or not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES
        or type(timeout) not in (int, float) or not 0.1 <= timeout <= 30
    ):
        raise DiscAcceptanceError("explicit legal rights and bounded native media work are required")
    cases = _validate_cases(cases)
    registry = GameEmulatorRegistry.from_environment()
    checked, passed = [], 0
    for case in cases:
        try:
            result = _run_case(case, registry.registry_digest, timeout)
            checked.append({"status": "actual_native_disc_replay_pass", "result": result})
            passed += 1
        except (ValueError, OSError, RuntimeError, TypeError) as exc:
            checked.append({
                "status": "native_disc_boot_failed",
                "core_id": case["core_id"],
                "target_id": case["target_id"],
                "entrypoint": case["entrypoint"],
                "error_type": type(exc).__name__,
                "error": str(exc)[:400],
                "native_disc_operational_acceptance": False,
            })
    report = {
        "schema_version": REPORT_SCHEMA,
        "operator_explicit_media_rights_acknowledged": True,
        "approved_registry_digest": registry.registry_digest,
        "requested_cases": len(cases),
        "real_multi_file_native_boots_verified": passed,
        "unverified_cases": len(cases) - passed,
        "all_cases_passed": passed == len(cases),
        "native_disc_cases": checked,
        "independent_hardware_accuracy_certified": False,
        "production_jeeves_weights_modified": False,
    }
    report["report_digest"] = _digest(report)
    if len(json.dumps(report, allow_nan=False).encode()) > MAX_REPORT_BYTES:
        raise DiscAcceptanceError("bounded native disc acceptance report capacity exceeded")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-file", required=True, type=Path)
    parser.add_argument("--evidence-file", required=True, type=Path)
    parser.add_argument("--rights-acknowledged", action="store_true")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        if not args.rights_acknowledged:
            raise DiscAcceptanceError("operator must explicitly acknowledge lawful media rights")
        if args.evidence_file.exists() or args.evidence_file.is_symlink():
            raise DiscAcceptanceError("native disc acceptance must create a new private evidence report")
        if args.manifest_file.resolve(strict=False) == args.evidence_file.resolve(strict=False):
            raise DiscAcceptanceError("native source manifest and output report must differ")
        if not args.evidence_file.parent.is_dir():
            raise DiscAcceptanceError("native disc evidence parent directory must already exist")
        cases = _manifest(args.manifest_file)
        report = run_matrix(cases, rights_acknowledged=True, timeout=args.timeout)
        payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        fd = os.open(args.evidence_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps({
            "status": "native_disc_proofs_complete" if report["all_cases_passed"] else "native_disc_proofs_incomplete",
            "real_multi_file_native_boots_verified": report["real_multi_file_native_boots_verified"],
            "unverified_cases": report["unverified_cases"],
            "evidence_file": str(args.evidence_file),
            "hardware_accuracy_certified": False,
        }, sort_keys=True))
        return 0 if report["all_cases_passed"] else 2
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "native_disc_media_rejected",
            "error": str(exc)[:600],
            "hardware_accuracy_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
