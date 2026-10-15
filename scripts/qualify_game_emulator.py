#!/usr/bin/env python3
"""Explicit operator-run, bounded real libretro replay qualification.

No source/core/firmware acquisition, no sample game, no mock execution,
no automatic learning, and no production model weight changes. Input is a
operator-owned ROM/homebrew file or explicitly selected local content directory.
Large/disc content uses the existing exact streamed content descriptors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read_operator_source(path: Path) -> tuple[bytes, str]:
    from skeleton.jeeves.game_emulator_catalog import MAX_CONTENT_BYTES

    if path.is_symlink():
        raise ValueError("Operator ROM source must not be a symlink")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        first = os.fstat(descriptor)
        if not stat.S_ISREG(first.st_mode) or not 1 <= first.st_size <= MAX_CONTENT_BYTES:
            raise ValueError("Operator source must be a nonempty bounded regular file")
        with os.fdopen(os.dup(descriptor), "rb") as source:
            data = source.read(MAX_CONTENT_BYTES + 1)
        second = os.fstat(descriptor)
        if len(data) != first.st_size or (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) != (
            second.st_dev,
            second.st_ino,
            second.st_size,
            second.st_mtime_ns,
        ):
            raise ValueError("ROM bytes changed during bounded operator source admission")
        return data, path.name
    finally:
        os.close(descriptor)


def _operator_directory_content(root: Path, entrypoint: str):
    """Pin an explicit local data tree; return its existing bundle and bounded reader.

    No path supplied to a native worker comes from content. The existing host
    materializes these exact references in its own private directory first.
    """
    from skeleton.jeeves.game_emulator_catalog import (
        MAX_CONTENT_FILES,
        MAX_REFERENCED_BUNDLE_BYTES,
        MAX_REFERENCED_FILE_BYTES,
        MAX_STREAM_CHUNK_BYTES,
        GameContentBundle,
        GameContentReference,
        _content_name,
        _safe_path,
    )

    root = _safe_path(str(root.absolute()))
    if not root.is_dir():
        raise ValueError("Explicit operator content root must be an existing nonsymlink directory")
    entrypoint = _content_name(entrypoint)
    rows, observed, pending, total, directory_count = [], {}, [(root, 0)], 0, 0

    def identity(details):
        return (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns, details.st_ctime_ns)

    while pending:
        folder, depth = pending.pop()
        directory_count += 1
        if depth > 8 or directory_count > 96:
            raise ValueError("Operator content directory exceeds its bounded depth or directory count")
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_symlink():
                    raise ValueError("Operator content directory cannot contain symbolic links")
                if entry.is_dir(follow_symlinks=False):
                    pending.append((Path(entry.path), depth + 1))
                    if len(pending) > 96:
                        raise ValueError("Operator content directory count exceeds 96")
                    continue
                if not entry.is_file(follow_symlinks=False) or len(rows) >= MAX_CONTENT_FILES:
                    raise ValueError("Operator content requires at most 96 bounded regular files")
                path = _safe_path(entry.path)
                name = _content_name(path.relative_to(root).as_posix())
                fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
                try:
                    before = os.fstat(fd)
                    if (
                        not stat.S_ISREG(before.st_mode)
                        or not 1 <= before.st_size <= MAX_REFERENCED_FILE_BYTES
                    ):
                        raise ValueError("Operator content file exceeds the 2 GiB regular-file bound")
                    total += before.st_size
                    if total > MAX_REFERENCED_BUNDLE_BYTES:
                        raise ValueError("Operator content bundle exceeds the 4 GiB bound")
                    hasher, prefix, size = hashlib.sha256(), bytearray(), 0
                    suffix = path.suffix.casefold()
                    head_bytes = (
                        65536
                        if suffix in {".cue", ".gdi", ".m3u", ".ccd", ".toc", ".mds"}
                        else 34816 if suffix == ".iso" else 124 if suffix == ".chd" else 0
                    )
                    with os.fdopen(os.dup(fd), "rb") as stream:
                        while chunk := stream.read(MAX_STREAM_CHUNK_BYTES):
                            size += len(chunk)
                            if size > before.st_size:
                                raise ValueError("Operator content file grew during identity capture")
                            hasher.update(chunk)
                            if len(prefix) < head_bytes:
                                prefix.extend(chunk[: head_bytes - len(prefix)])
                    after = os.fstat(fd)
                    final = path.stat(follow_symlinks=False)
                    if (
                        size != before.st_size
                        or identity(before) != identity(after)
                        or identity(after) != identity(final)
                    ):
                        raise ValueError("Operator content changed during its exact-byte identity capture")
                    rows.append({"name": name, "sha256": hasher.hexdigest(), "size_bytes": size})
                    observed[name] = (path, identity(after), bytes(prefix))
                finally:
                    os.close(fd)
    rows.sort(key=lambda row: row["name"])
    source_digest = hashlib.sha256(
        json.dumps(
            {"entrypoint": entrypoint, "files": rows},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    references = {
        row["name"]: GameContentReference(
            row["name"],
            row["size_bytes"],
            row["sha256"],
            f"operator-local://{source_digest}/{index}",
            observed[row["name"]][2],
        )
        for index, row in enumerate(rows)
    }
    bundle = GameContentBundle(entrypoint, references, source_digest)

    def reader(reference):
        if not isinstance(reference, GameContentReference) or references.get(reference.name) != reference:
            raise ValueError("Operator content reader accepts only this exact pinned bundle")
        path, expected, _ = observed[reference.name]
        _safe_path(str(path))
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        try:
            if identity(os.fstat(fd)) != expected:
                raise ValueError("Operator content identity changed before native materialization")
            with os.fdopen(os.dup(fd), "rb") as stream:
                while chunk := stream.read(MAX_STREAM_CHUNK_BYTES):
                    yield chunk
            if identity(os.fstat(fd)) != expected or identity(path.stat(follow_symlinks=False)) != expected:
                raise ValueError("Operator content identity changed during native materialization")
        finally:
            os.close(fd)

    return bundle, reader


def _read_controller_tape(path: Path) -> list:
    """Read an exact bounded JSON-only four-port input tape, rejecting duplicate keys."""
    if path.is_symlink():
        raise ValueError("Controller tape may not be a symlink")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= 128 * 1024:
            raise ValueError("Controller tape JSON exceeds its bounded file size")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(128 * 1024 + 1)
        after = os.fstat(fd)
        if len(raw) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("Controller tape changed while being read")
    finally:
        os.close(fd)

    def pairs(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError("Controller tape contains duplicate JSON keys")
            parsed[key] = value
        return parsed

    def invalid(value):
        raise ValueError("Nonfinite controller coordinates are forbidden")

    tape = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    if not isinstance(tape, list) or not 1 <= len(tape) <= 64:
        raise ValueError("Controller tape must be a JSON list of 1–64 input frames")
    from skeleton.jeeves.game_emulator_host import _controls

    return [_controls(frame) for frame in tape]


def main(argv: list[str] | None = None) -> int:
    from skeleton.jeeves.game_emulator_catalog import (
        REGISTRY_ENV,
        GameEmulatorRegistry,
    )
    from skeleton.jeeves.game_emulator_cross_core import compare_native_emulator_cores
    from skeleton.jeeves.game_emulator_exploration import run_emulator_exploration
    from skeleton.jeeves.game_emulator_host import _ACTIONS, _KEY_ACTIONS
    from skeleton.jeeves.game_emulator_qualification import run_emulator_qualification
    from skeleton.jeeves.game_emulator_savestate_audit import (
        run_native_savestate_roundtrip,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", type=Path, required=True, help="Approved local cores.json (no download)"
    )
    parser.add_argument("--target", required=True, help="Canonical hardware target ID")
    parser.add_argument("--core", required=True, help="Explicit approved libretro core ID")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", type=Path, help="Local 1–16 MiB lawful ROM/homebrew data")
    source_group.add_argument(
        "--content-root",
        type=Path,
        help="Explicit lawful local disc/data tree: at most 96 files, 2 GiB/file, 4 GiB total",
    )
    parser.add_argument(
        "--entrypoint", help="Exact relative entrypoint inside --content-root; no automatic file selection"
    )
    tape_group = parser.add_mutually_exclusive_group(required=True)
    tape_group.add_argument("--action", action="append", choices=sorted((*_ACTIONS, *_KEY_ACTIONS)))
    tape_group.add_argument(
        "--controller-tape-json",
        type=Path,
        help="Explicit 1–64 step JSON input tape for four-player button/axis/key/mouse/pointer controls",
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="2–10 independent isolated worker sessions per scenario"
    )
    advanced_group = parser.add_mutually_exclusive_group()
    advanced_group.add_argument(
        "--explore-scenarios", type=int, help="Explicit bounded boomerang exploration, 2–80 scenarios"
    )
    advanced_group.add_argument(
        "--compare-core",
        action="append",
        help="Additional approved core to compare against --core; 1–7 other cores",
    )
    advanced_group.add_argument(
        "--checkpoint-at",
        type=int,
        help="Save native state after this input step, then replay the suffix without restarting the core",
    )
    parser.add_argument(
        "--stagnation-window",
        type=int,
        default=10,
        help="Stop exploration after 3–20 scenarios with no new audiovisual outcome (default 10)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--frames-per-step", type=int, default=1)
    parser.add_argument(
        "--controller-device",
        action="append",
        choices=("none", "joypad", "mouse", "keyboard", "analog", "pointer"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--rights-evidence-digest", help="Optional operator-supplied SHA-256, not a legal certificate"
    )
    parser.add_argument(
        "--include-traces", action="store_true", help="Also output bounded raw native observations to stdout"
    )
    args = parser.parse_args(argv)
    try:
        if args.registry.is_symlink():
            raise ValueError("Approved operator registry cannot be a symlink")
        registry_path = args.registry.resolve(strict=True)
        registry = GameEmulatorRegistry(registry_path)
        core = registry.resolve_core(args.core)
        if args.target.removeprefix("emulator:") not in core.target_ids:
            raise ValueError("Approved core does not declare this exact canonical target")
        os.environ[REGISTRY_ENV] = str(registry_path)
        if args.content_root is not None:
            if args.entrypoint is None:
                raise ValueError("--content-root requires an exact relative --entrypoint")
            bundle, reader = _operator_directory_content(args.content_root, args.entrypoint)
            source, name = None, bundle.entrypoint
        else:
            if args.entrypoint is not None:
                raise ValueError("--entrypoint is only valid with --content-root")
            source_path = args.source.absolute()
            source, name = _read_operator_source(source_path)
            bundle, reader = None, None
        tape = (
            _read_controller_tape(args.controller_tape_json)
            if args.controller_tape_json is not None
            else None
        )
        if args.explore_scenarios is not None:
            if tape is not None:
                raise ValueError(
                    "Boomerang exploration currently requires policy actions; raw multi-port tapes use regular qualification"
                )
            if args.include_traces:
                raise ValueError(
                    "Boomerang exploration returns bounded receipts, not large raw trace exports"
                )
            result = run_emulator_exploration(
                args.target,
                core_id=args.core,
                expected_registry_digest=registry.registry_digest,
                rom_source=source,
                content=bundle,
                reader=reader,
                filename=name,
                actions=args.action,
                runs_per_scenario=args.runs,
                max_scenarios=args.explore_scenarios,
                stagnation_window=args.stagnation_window,
                seed=args.seed,
                frames_per_step=args.frames_per_step,
                controller_devices=args.controller_device,
                timeout_seconds=args.timeout_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
            )
        elif args.compare_core:
            if args.include_traces:
                raise ValueError(
                    "Cross-core differences report bounded receipt hashes, not raw trace exports"
                )
            result = compare_native_emulator_cores(
                args.target,
                core_ids=[args.core, *args.compare_core],
                expected_registry_digest=registry.registry_digest,
                rom_source=source,
                content=bundle,
                reader=reader,
                filename=name,
                actions=args.action,
                controller_tape=tape,
                runs_per_core=args.runs,
                seed=args.seed,
                frames_per_step=args.frames_per_step,
                controller_devices=args.controller_device,
                timeout_seconds=args.timeout_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
            )
        elif args.checkpoint_at is not None:
            if args.include_traces:
                raise ValueError(
                    "Checkpoint audit returns exact bounded comparison receipts, not a raw trace export"
                )
            result = run_native_savestate_roundtrip(
                args.target,
                core_id=args.core,
                expected_registry_digest=registry.registry_digest,
                rom_source=source,
                content=bundle,
                reader=reader,
                filename=name,
                actions=args.action,
                controller_tape=tape,
                checkpoint_at=args.checkpoint_at,
                seed=args.seed,
                frames_per_step=args.frames_per_step,
                controller_devices=args.controller_device,
                timeout_seconds=args.timeout_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
            )
        else:
            result = run_emulator_qualification(
                args.target,
                core_id=args.core,
                expected_registry_digest=registry.registry_digest,
                rom_source=source,
                content=bundle,
                reader=reader,
                filename=name,
                actions=args.action,
                controller_tape=tape,
                runs=args.runs,
                seed=args.seed,
                frames_per_step=args.frames_per_step,
                controller_devices=args.controller_device,
                timeout_seconds=args.timeout_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
                include_traces=args.include_traces,
            )
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(
            json.dumps({"status": "native_qualification_rejected", "reason": str(exc)[:512]}), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
