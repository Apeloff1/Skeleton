"""``python -m skeleton.build.delivery.cli`` — offline delivery tooling.

Subcommands read and write local JSON files only; none of them deploy.

  manifest   hash files under a directory into an artifact manifest
  verify     check files on disk against a manifest
  env        resolve and print an environment config
  plan       compile a deploy plan from a manifest and an environment
  rollback   compute a rollback plan from a release-history file
  secrets    scan files for secret-looking content
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Sequence

from skeleton.build.delivery._util import DeliveryError, canonical_json, sha256_bytes
from skeleton.build.delivery.artifact_manifest import ArtifactManifest, build_manifest, verify_files
from skeleton.build.delivery.deploy_plan import compile_plan
from skeleton.build.delivery.env_config import load_layers, resolve
from skeleton.build.delivery.release_history import ReleaseHistory
from skeleton.build.delivery.rollback import plan_rollback
from skeleton.build.delivery.secrets_guard import scan_text

MAX_READ = 50 * 1024 * 1024
MAX_READ_FILES = 2048
MAX_READ_ENTRIES = 16384
MAX_READ_DEPTH = 32


def _read_tree(root: Path) -> dict[str, bytes]:
    """Read a bounded, descriptor-held snapshot without pathname reopen races."""
    if not (hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
            and hasattr(os, "O_NONBLOCK") and os.open in os.supports_dir_fd):
        raise DeliveryError("secure delivery tree reading unavailable")
    raw = os.fspath(root)
    if (not isinstance(raw, str) or not raw or len(raw) > 4096
            or "\x00" in raw or ".." in Path(raw).parts):
        raise DeliveryError("unsafe delivery tree root")
    absolute = os.path.abspath(raw)
    components = [part for part in absolute.split(os.sep) if part]
    if len(components) > 128:
        raise DeliveryError("delivery root depth exceeds bound")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_NOCTTY", 0)
    current = os.open(os.sep, dir_flags)
    try:
        for part in components:
            child = os.open(part, dir_flags, dir_fd=current)
            os.close(current)
            current = child
        out: dict[str, bytes] = {}
        total = 0
        entries = 0

        def walk(directory_fd: int, prefix: str, depth: int) -> None:
            nonlocal total, entries
            if depth > MAX_READ_DEPTH:
                raise DeliveryError("delivery tree depth exceeds bound")
            with os.scandir(directory_fd) as iterator:
                for entry in iterator:
                    entries += 1
                    if entries > MAX_READ_ENTRIES:
                        raise DeliveryError("delivery tree entry count exceeds bound")
                    path = prefix + entry.name
                    observed = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(observed.st_mode):
                        child_fd = os.open(entry.name, dir_flags, dir_fd=directory_fd)
                        try:
                            opened = os.fstat(child_fd)
                            if (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino):
                                raise DeliveryError("delivery directory changed during scan")
                            walk(child_fd, path + "/", depth + 1)
                        finally:
                            os.close(child_fd)
                    elif stat.S_ISREG(observed.st_mode):
                        if len(out) >= MAX_READ_FILES:
                            raise DeliveryError("delivery file count exceeds bound")
                        leaf_fd = os.open(entry.name, file_flags, dir_fd=directory_fd)
                        try:
                            before = os.fstat(leaf_fd)
                            def identity(s):
                                return (s.st_dev, s.st_ino, s.st_size,
                                        s.st_mtime_ns, s.st_ctime_ns)
                            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                                    or identity(before) != identity(observed)):
                                raise DeliveryError("delivery file changed or aliases external inode")
                            if before.st_size > MAX_READ - total:
                                raise DeliveryError("delivery tree exceeds byte limit")
                            blocks: list[bytes] = []
                            read = 0
                            while read <= before.st_size:
                                block = os.read(leaf_fd, min(1024 * 1024, before.st_size + 1 - read))
                                if not block:
                                    break
                                read += len(block)
                                blocks.append(block)
                            if read != before.st_size or identity(os.fstat(leaf_fd)) != identity(before):
                                raise DeliveryError("delivery file changed during descriptor read")
                            out[path] = b"".join(blocks)
                            total += read
                        finally:
                            os.close(leaf_fd)
                    else:
                        raise DeliveryError("delivery tree contains nonregular member")
        walk(current, "", 0)
        return out
    except OSError as exc:
        raise DeliveryError("delivery tree descriptor traversal failed") from exc
    finally:
        os.close(current)


def _kind(path: str) -> str:
    for suffix, kind in ((".whl", "wheel"), (".tar.gz", "tarball"), (".zip", "zip"), (".json", "config")):
        if path.endswith(suffix):
            return kind
    return "other"


def _load_env_dir(directory: Path) -> dict:
    texts = {p.stem: p.read_text(encoding="utf-8") for p in sorted(directory.glob("*.json"))}
    return load_layers(texts)


def cmd_manifest(args: argparse.Namespace) -> int:
    files = _read_tree(Path(args.root))
    manifest = build_manifest(
        release_id=args.release_id,
        version=args.version,
        source_commit=args.commit,
        artifacts=[
            {"path": p, "kind": _kind(p), "size": len(d), "sha256": sha256_bytes(d)} for p, d in files.items()
        ],
    )
    print(manifest.serialize())
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    manifest = ArtifactManifest.from_dict(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
    problems = verify_files(manifest, _read_tree(Path(args.root)))
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def cmd_env(args: argparse.Namespace) -> int:
    env = resolve(args.name, _load_env_dir(Path(args.dir)))
    print(canonical_json({"name": env.name, "lineage": list(env.lineage), "digest": env.digest, "values": env.values}))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    manifest = ArtifactManifest.from_dict(json.loads(Path(args.manifest).read_text(encoding="utf-8")))
    env = resolve(args.env, _load_env_dir(Path(args.dir)))
    print(compile_plan(manifest, env).serialize())
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    items = json.loads(Path(args.history).read_text(encoding="utf-8"))
    history = ReleaseHistory.from_list(args.env, items)
    plan = plan_rollback(history, trigger=args.trigger)
    print(canonical_json({
        "environment": plan.environment, "from": plan.from_release, "to": plan.to_release,
        "trigger": plan.trigger, "steps": list(plan.steps),
    }))
    return 0


def cmd_secrets(args: argparse.Namespace) -> int:
    found = 0
    for name in args.paths:
        text = Path(name).read_text(encoding="utf-8", errors="replace")
        for finding in scan_text(name, text):
            print(f"{finding.location}: {finding.rule}")
            found += 1
    return 1 if found else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skeleton-delivery", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("manifest")
    p.add_argument("root")
    p.add_argument("--release-id", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--commit", required=True)
    p.set_defaults(func=cmd_manifest)
    p = sub.add_parser("verify")
    p.add_argument("manifest")
    p.add_argument("root")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("env")
    p.add_argument("name")
    p.add_argument("--dir", required=True)
    p.set_defaults(func=cmd_env)
    p = sub.add_parser("plan")
    p.add_argument("manifest")
    p.add_argument("--env", required=True)
    p.add_argument("--dir", required=True)
    p.set_defaults(func=cmd_plan)
    p = sub.add_parser("rollback")
    p.add_argument("history")
    p.add_argument("--env", required=True)
    p.add_argument("--trigger", default="manual")
    p.set_defaults(func=cmd_rollback)
    p = sub.add_parser("secrets")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_secrets)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DeliveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
