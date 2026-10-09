"""Standalone legal-first, cross-era game project authoring CLI.

Usage (repo root):
  python scripts/game/game_project.py --catalog
  python scripts/game/game_project.py --demo-project demo.json --targets nes-famicom,playstation-5
  python scripts/game/game_project.py --verify-capsule demo.json
  python scripts/game/game_project.py --plan target-requests.json
  python scripts/game/game_project.py --compose project-input.json --output new.json

No SDK/BIOS/firmware/ROM downloads, subprocesses, external assets,
model inference or training data are used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence

from skeleton.ai.runtime.game_platform_catalog import (
    GamePlatformError, catalog_summary, plan_game_targets,
)
from skeleton.ai.runtime.game_rights import GameRightsError, SCHEMA as RIGHTS_SCHEMA
from skeleton.ai.runtime.game_project_capsule import (
    GameCapsuleError, make_game_capsule, verify_game_capsule,
)
from skeleton.ai.runtime.gameplay_capabilities import (
    GameplayError, compile_level, generate_level,
)

MAX_INPUT_BYTES = 96 * 1024
MAX_RESULT_BYTES = 160 * 1024


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, value in items:
        if key in found:
            raise GameCapsuleError("duplicate game project JSON property")
        found[key] = value
    return found


def _nonfinite(_: str) -> None:
    raise GameCapsuleError("nonfinite game project numbers are inadmissible")


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GameCapsuleError("game input must be an existing regular local file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise GameCapsuleError("game project input exceeded local file budget")
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise GameCapsuleError("game project input exceeded local file budget")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise GameCapsuleError("game project JSON is malformed") from exc
    if not isinstance(value, dict):
        raise GameCapsuleError("game project JSON must be an object")
    return value


def _write_new(path: Path, result: dict[str, Any]) -> str:
    raw = (
        json.dumps(
            result, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ) + "\n"
    ).encode("ascii")
    if len(raw) > MAX_RESULT_BYTES:
        raise GameCapsuleError("game project output exceeds 160-KiB cap")
    target = path.expanduser().absolute()
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise GameCapsuleError("project output must be a new file in an existing directory")
    fd = os.open(
        target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return str(target)


def _demo(seed: int, target_ids: list[str], jurisdiction: str) -> dict[str, Any]:
    generated = generate_level({
        "seed": seed, "width": 12, "height": 9, "wall_percent": 30,
    })
    level = compile_level({"tiles": generated["tiles"]})
    rights = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": f"original-demo-{seed}",
        "title": "Original procedural Skeleton game prototype",
        "rights_contact": "local-operator-unverified",
        "assets": [{
            "asset_id": "tilemap",
            "sha256": level["tile_digest"],
            "source_kind": "original",
            "licensor": "local-operator-unverified",
            "license_reference": "original-procedural-generation-v1",
            "allowed_uses": ["embed", "modify", "distribute"],
            "contains_third_party_content": False,
            "contains_trademarks": False,
            "contains_technological_protection": False,
        }],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    return make_game_capsule(
        source_tiles=generated["tiles"], rights_manifest=rights,
        target_ids=target_ids, required_features=["tile2d", "input"],
        action="original_game", jurisdiction=jurisdiction,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Author legally reviewed game project specifications across eras. No ROM/SDK output.",
    )
    operations = parser.add_mutually_exclusive_group(required=True)
    operations.add_argument("--catalog", action="store_true",
                            help="catalog targets, not fictional native build support")
    operations.add_argument("--plan", type=Path,
                            help="JSON file: target_ids, required_features, optional sdk_authorizations")
    operations.add_argument("--compose", type=Path,
                            help="JSON project: source_tiles, rights_manifest, action, jurisdiction, targets, edits")
    operations.add_argument("--verify-capsule", type=Path,
                            help="verify portable project and recalculate scene digests")
    operations.add_argument("--demo-project", type=Path,
                            help="write a new small original portable game capsule")
    parser.add_argument("--output", type=Path,
                        help="exclusive new file for --compose")
    parser.add_argument("--seed", type=int, default=1729,
                        help="bounded seed for original procedural demo only")
    parser.add_argument("--targets", default="nes-famicom,game-boy,playstation-5,windows-11",
                        help="comma-separated era targets for demo only")
    parser.add_argument("--jurisdiction", default="NO",
                        help="legal review region for original demo; not legal clearance")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.output is not None and args.compose is None:
        print("--output is supported only for --compose", file=sys.stderr)
        return 2
    if args.compose is not None and args.output is None:
        print("--compose requires --output for a durable new project", file=sys.stderr)
        return 2
    if args.seed != 1729 and args.demo_project is None:
        print("--seed is only for --demo-project", file=sys.stderr)
        return 2
    if args.targets != "nes-famicom,game-boy,playstation-5,windows-11" and args.demo_project is None:
        print("--targets is only for --demo-project", file=sys.stderr)
        return 2
    try:
        if args.catalog:
            report = catalog_summary()
        elif args.plan:
            body = _read_json(args.plan)
            if set(body) - {"target_ids", "required_features", "sdk_authorizations"}:
                raise GamePlatformError("target planning inputs have extra fields")
            report = plan_game_targets(
                target_ids=body.get("target_ids"),
                required_features=body.get("required_features"),
                sdk_authorizations=body.get("sdk_authorizations"),
            )
        elif args.compose:
            body = _read_json(args.compose)
            if set(body) - {
                "source_tiles", "rights_manifest", "target_ids",
                "required_features", "action", "jurisdiction", "edits",
                "sdk_authorizations",
            }:
                raise GameCapsuleError("game project input contains unknown fields")
            project = make_game_capsule(
                source_tiles=body.get("source_tiles"),
                rights_manifest=body.get("rights_manifest"),
                target_ids=body.get("target_ids"),
                required_features=body.get("required_features"),
                action=body.get("action"),
                jurisdiction=body.get("jurisdiction"),
                edits=body.get("edits"),
                sdk_authorizations=body.get("sdk_authorizations"),
            )
            report = {
                **verify_game_capsule(project),
                "output_path": _write_new(args.output, project) if args.output else None,
                "output_type": "portable_original_game_project_json",
            }
        elif args.demo_project:
            selected = args.targets.split(",")
            project = _demo(args.seed, selected, args.jurisdiction)
            checked = verify_game_capsule(project)
            report = {
                **checked, "output_path": _write_new(args.demo_project, project),
                "requested_target_count": len(selected),
                "source_rights_self_attested": True,
                "no_native_console_binary_created": True,
            }
        else:
            report = verify_game_capsule(_read_json(args.verify_capsule))
        print(json.dumps(report, sort_keys=True, ensure_ascii=True))
        return 0
    except (GameCapsuleError, GamePlatformError, GameRightsError,
            GameplayError, ValueError, TypeError, KeyError, OSError) as exc:
        print(
            "cross-era game project rejected: " + type(exc).__name__ + ": " + str(exc),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
