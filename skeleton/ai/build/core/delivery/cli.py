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


def _read_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        raise DeliveryError(f"{root} is not a directory")
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise DeliveryError(f"symlinks are not packaged: {path}")
        if path.is_file():
            if path.stat().st_size > MAX_READ:
                raise DeliveryError(f"{path} exceeds 50 MB")
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


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
