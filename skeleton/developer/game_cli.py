"""Local game-development workspace commands over the canonical GameForge pipeline.

This is a developer transport, not a second game engine or state authority.
Only a local operator may choose filesystem destinations. The existing forge
projector, source-manifest, and Godot playtest own execution and evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
from typing import Any

SCHEMA = "skeleton.game.workspace.v1"
MANIFEST = "skeleton.game.json"
MAX_CONFIG_BYTES = 64 * 1024
MAX_SOURCE_FILES = 2048
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_FORGE_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_ASSET_FILES = 4096
MAX_ASSET_BYTES = 128 * 1024 * 1024
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class GameCLIError(ValueError):
    """Operator error; no fallback or unrelated game generation."""


def _fail(reason: str) -> None:
    raise GameCLIError(reason)


def _project(root: str) -> Path:
    path = Path(root).expanduser().absolute()
    if path.is_symlink():
        _fail("project root may not be a symlink")
    return path


def _load(root: Path) -> dict[str, str]:
    path = root / MANIFEST
    if path.is_symlink() or not path.is_file():
        _fail("not a game workspace: missing regular skeleton.game.json")
    if path.stat().st_size > MAX_CONFIG_BYTES:
        _fail("game workspace manifest exceeds 64 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise GameCLIError("invalid game workspace JSON") from exc
    if not isinstance(data, dict) or set(data) != {"schema", "name", "vision", "era", "archetype"}:
        _fail("unsupported game workspace manifest fields")
    if data.get("schema") != SCHEMA:
        _fail("unsupported game workspace schema")
    if not isinstance(data["name"], str) or not _NAME.fullmatch(data["name"]) or data["name"] in {".", ".."}:
        _fail("invalid game workspace name")
    for key in ("vision", "era", "archetype"):
        value = data[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            _fail(f"invalid game workspace {key}")
        if any(ord(ch) < 32 for ch in value):
            _fail(f"control character in game workspace {key}")
    if len(data["era"]) > 128 or len(data["archetype"]) > 128:
        _fail("game era/archetype too long")
    return data


def _init(args: argparse.Namespace) -> dict[str, Any]:
    name = args.name
    if name in {".", ".."} or not _NAME.fullmatch(name):
        _fail("name must be one safe directory component (up to 100 characters)")
    vision = args.vision or name.replace("-", " ").replace("_", " ")
    if not vision.strip() or len(vision) > 4096 or any(ord(ch) < 32 for ch in vision):
        _fail("vision must be nonempty, at most 4096 characters, without control characters")
    from skeleton.forge.eras import list_eras
    if args.era not in set(list_eras()):
        _fail(f"unknown era: {args.era}")
    from skeleton.forge.archetypes import default_library
    if args.archetype not in {"auto", "vision", *default_library().names()}:
        _fail(f"unknown archetype: {args.archetype}")
    parent = Path(args.dir).expanduser().resolve()
    dest = parent / name
    if dest.is_symlink() or dest.exists():
        _fail(f"destination already exists: {dest}")
    data = {"schema": SCHEMA, "name": name, "vision": vision,
            "era": args.era, "archetype": args.archetype}
    paths = [MANIFEST, "README.md", ".gitignore", "assets/.gitkeep",
             "design/.gitkeep", "tests/.gitkeep"]
    result = {"ok": True, "action": "init", "project": str(dest),
              "files": paths, "dry_run": args.dry_run}
    if args.dry_run:
        return result
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".game-init-", dir=parent))
    try:
        (stage / MANIFEST).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "README.md").write_text(
            f"# {name}\n\n{vision}\n\n"
            "Build: python -m skeleton dev game build --project .\n"
            "Verify: python -m skeleton dev game verify --project .\n"
            "Playtest: python -m skeleton dev game playtest --project .\n"
            "Package sources: python -m skeleton dev game package --project .\n",
            encoding="utf-8",
        )
        (stage / ".gitignore").write_text("build/\ndist/\n.godot/\n.jeeves/\n", encoding="utf-8")
        for folder in ("assets", "design", "tests"):
            (stage / folder).mkdir()
            (stage / folder / ".gitkeep").write_text("", encoding="utf-8")
        if dest.exists() or dest.is_symlink():
            _fail("destination appeared during initialization")
        os.rename(stage, dest)
    finally:
        if stage.exists():
            import shutil
            shutil.rmtree(stage)
    return result


def _read_forge(root: Path) -> tuple[Path, dict[str, str], dict[str, Any]]:
    from skeleton.forge.source_manifest import source_manifest

    build = root / "build" / "godot"
    if (root / "build").is_symlink() or build.is_symlink():
        _fail("refusing symlinked build directory")
    manifest_file = build / "FORGE_MANIFEST.json"
    if manifest_file.is_symlink() or not manifest_file.is_file():
        _fail("no emitted Godot project: build the game first")
    if manifest_file.stat().st_size > MAX_FORGE_MANIFEST_BYTES:
        _fail("Forge manifest exceeds size limit")
    try:
        report = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise GameCLIError("invalid Forge manifest JSON") from exc
    expected = report.get("sha256") if isinstance(report, dict) else None
    if not isinstance(expected, dict) or not expected or len(expected) > MAX_SOURCE_FILES:
        _fail("invalid or oversized Forge file list")
    # Validate ALL paths using the canonical Godot projector before file I/O,
    # including Windows drive/device names and case-fold aliases.
    try:
        source_manifest({rel: "" for rel in expected})
    except (TypeError, ValueError) as exc:
        raise GameCLIError(f"unsafe Forge file list: {exc}") from exc
    files: dict[str, str] = {}
    total = 0
    for rel, digest in expected.items():
        if not isinstance(rel, str) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            _fail("invalid Forge source entry")
        # The canonical projector rejects traversal, reserved paths and aliases.
        # Check symlinks before reading; never follow untrusted manifest paths.
        from pathlib import PurePosixPath
        if not rel or "\\" in rel or PurePosixPath(rel).is_absolute() or any(
            part in {"", ".", ".."} for part in rel.split("/")
        ):
            _fail("unsafe Forge source path")
        candidate = build
        for part in rel.split("/"):
            candidate = candidate / part
            if candidate.is_symlink():
                _fail(f"symlinked Forge source: {rel}")
        if not candidate.is_file():
            _fail(f"missing Forge source: {rel}")
        size = candidate.stat().st_size
        total += size
        if total > MAX_SOURCE_BYTES:
            _fail("Forge sources exceed 64 MiB verification limit")
        try:
            body = candidate.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise GameCLIError(f"non-UTF8 Forge source: {rel}") from exc
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != digest:
            _fail(f"changed Forge source: {rel}")
        files[rel] = body
    try:
        receipt = source_manifest(files)
    except (TypeError, ValueError) as exc:
        raise GameCLIError(f"invalid emitted source manifest: {exc}") from exc
    if report.get("source_sha256") != receipt["sha256"]:
        _fail("Forge source-manifest identity mismatch")
    names = report.get("files")
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names) or sorted(names) != sorted(files):
        _fail("Forge file-list identity mismatch")
    return build, files, receipt


def _check_assets(root: Path) -> dict[str, Any]:
    assets = root / "assets"
    if assets.is_symlink() or not assets.is_dir():
        _fail("assets directory is missing or a symlink")
    digests: dict[str, str] = {}
    total = 0
    for node in sorted(assets.rglob("*")):
        if node.is_symlink():
            _fail(f"asset symlink refused: {node.relative_to(root)}")
        if node.is_dir():
            continue
        if not node.is_file():
            _fail("asset tree contains a non-regular file")
        if node.name == ".gitkeep":
            continue
        if len(digests) >= MAX_ASSET_FILES:
            _fail("asset inventory exceeds 4096 files")
        size = node.stat().st_size
        total += size
        if total > MAX_ASSET_BYTES:
            _fail("asset inventory exceeds 128 MiB")
        hasher = hashlib.sha256()
        with node.open("rb") as asset_stream:
            for chunk in iter(lambda: asset_stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digests[node.relative_to(assets).as_posix()] = hasher.hexdigest()
    return {"count": len(digests), "bytes": total, "sha256": digests}


def _doctor(root: Path, *, require_godot: bool) -> dict[str, Any]:
    from skeleton.forge.playtest import resolve_binary
    from skeleton.forge.eras import list_eras
    config = _load(root)
    problems: list[str] = []
    if config["era"] not in set(list_eras()):
        problems.append("configured era is unavailable")
    from skeleton.forge.archetypes import default_library
    if config["archetype"] not in {"auto", "vision", *default_library().names()}:
        problems.append("configured archetype is unavailable")
    if not root.is_dir():
        problems.append("project directory does not exist")
    if (root / "build").is_symlink():
        problems.append("build directory is a symlink")
    godot, source, verified = resolve_binary()
    if require_godot and godot is None:
        problems.append("Godot executable not found")
    return {"ok": not problems, "action": "doctor", "project": str(root),
            "era": config["era"], "godot": {"found": bool(godot), "source": source,
                                           "artifact_verified": verified},
            "can_build": not problems, "problems": problems}


def _build(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    checked = _doctor(root, require_godot=False)
    if not checked["ok"]:
        _fail(f"GameForge prerequisites invalid: {checked['problems']}")
    config = _load(root)
    if (root / "build").is_symlink() or (root / "build" / "godot").is_symlink():
        _fail("refusing symlinked build output")
    from skeleton.context.pipeline import GameForgeRun
    try:
        response = GameForgeRun.live().execute(
            config["vision"], era=config["era"], archetype=config["archetype"],
            project_root=str(root / "build" / "godot"), target="godot",
            overwrite=args.overwrite, playtest=args.playtest,
            repair_mode=args.repair_mode,
        )
    except (OSError, ValueError) as exc:
        raise GameCLIError(f"GameForge build rejected: {exc}") from exc
    return {"ok": bool(response.get("succeeded")), "action": "build", "project": str(root),
            "output": str(root / "build" / "godot"),
            "source_manifest": response.get("source_manifest"),
            "playtest": response.get("playtest"),
            "failed_stages": [s for s in (response.get("run") or {}).get("stages", [])
                              if s.get("status") == "FAILED"]}


def _verify(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    _load(root)
    build, files, receipt = _read_forge(root)
    result: dict[str, Any] = {"ok": True, "action": args.action, "project": str(root),
                              "build": str(build), "source_manifest": receipt}
    if args.action == "playtest" or args.playtest != "off":
        from skeleton.forge.playtest import playtest
        tested = playtest(files, frames=args.frames, timeout=args.timeout)
        result["playtest"] = tested
        result["ok"] = bool(tested.get("passed")) if args.action == "playtest" or args.playtest == "require" else tested.get("status") != "failed"
    return result


def _package(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    config = _load(root)
    build, files, receipt = _read_forge(root)
    extra: dict[str, bytes] = {}
    for name in ("FORGE_MANIFEST.json", "CONTEXT_LEDGER.json",
                 "CONTEXT_TENSOR.json", "build_report.md"):
        path = build / name
        if path.is_symlink():
            _fail("symlinked Forge receipt refused")
        if path.is_file():
            if path.stat().st_size > MAX_EVIDENCE_BYTES:
                _fail("Forge receipt too large to package")
            extra[name] = path.read_bytes()
    destination_dir = root / "dist"
    if destination_dir.is_symlink():
        _fail("refusing symlinked distribution directory")
    archive = destination_dir / f"{config['name']}-godot-source.zip"
    if archive.is_symlink() or (archive.exists() and not args.overwrite):
        _fail("source archive exists (use --overwrite explicitly)")
    result = {"ok": True, "action": "package", "format": "godot-source-zip",
              "archive": str(archive), "source_sha256": receipt["sha256"],
              "file_count": len(files) + len(extra), "dry_run": args.dry_run,
              "native_binary": False}
    if args.dry_run:
        return result
    destination_dir.mkdir(parents=True, exist_ok=True)
    temp: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".game-package-", suffix=".zip",
                                         dir=destination_dir, delete=False) as handle:
            temp = handle.name
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for rel in sorted(set(files) | set(extra)):
                data = files[rel].encode("utf-8") if rel in files else extra[rel]
                item = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                package.writestr(item, data)
        if args.overwrite:
            os.replace(temp, archive)
        else:
            os.link(temp, archive)  # atomic no-clobber publication
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    return result


def run_game_cli(argv: list[str]) -> dict[str, Any]:
    """Command transport for python -m skeleton dev game."""
    parser = argparse.ArgumentParser(prog="skeleton dev game",
        description="Local game creation and evidence tools. No remote filesystem access.")
    subs = parser.add_subparsers(dest="action", required=True)
    init = subs.add_parser("init", help="Create an original game workspace")
    init.add_argument("name")
    init.add_argument("--dir", default=".")
    init.add_argument("--vision")
    init.add_argument("--era", default="extraction_now")
    init.add_argument("--archetype", default="auto")
    init.add_argument("--dry-run", action="store_true")
    subs.add_parser("catalog", help="List supported GameForge eras and archetypes")
    jeeves = subs.add_parser("jeeves", help="Jeeves design planning, source audit and developer handoff")
    jeeves.add_argument("jeeves_action", choices=("plan", "audit", "next", "context", "handoff",
                                                   "propose", "review", "apply", "queue", "benchmark", "benchmark-matrix", "asset-gate",
                                                   "fidelity-plan", "fidelity-matrix", "display-plan", "upscale", "upscale-verify", "render-reference", "production-init",
                                                   "production-status", "production-cycle", "production-training"))
    jeeves.add_argument("--project", default=".")
    jeeves.add_argument("--kind", choices=("character", "dialogue", "quest", "world", "mechanic",
                                           "scene", "animation", "cutscene", "asset", "music"))
    jeeves.add_argument("--brief")
    jeeves.add_argument("--include-notes", action="store_true")
    jeeves.add_argument("--digest")
    jeeves.add_argument("--approve")
    jeeves.add_argument("--console")
    jeeves.add_argument("--genre")
    jeeves.add_argument("--period")
    jeeves.add_argument("--profile")
    jeeves.add_argument("--evidence")
    jeeves.add_argument("--target")
    jeeves.add_argument("--source")
    jeeves.add_argument("--output")
    jeeves.add_argument("--mode", choices=("nearest", "scale2x"))
    jeeves.add_argument("--factor", type=int)
    jeeves.add_argument("--dry-run", action="store_true")
    jeeves.add_argument("--passes", type=int)
    jeeves.add_argument("--gate")
    jeeves.add_argument("--page", type=int)
    jeeves.add_argument("--page-size", type=int)
    jeeves.add_argument("--repair-generated", action="store_true")
    for dimension in ("native-width", "native-height", "screen-width",
                      "screen-height", "pixel-aspect-num", "pixel-aspect-den"):
        jeeves.add_argument("--" + dimension, type=int)
    for action in ("info", "doctor", "build", "verify", "playtest", "assets", "package"):
        child = subs.add_parser(action)
        child.add_argument("--project", default=".")
        if action == "doctor":
            child.add_argument("--require-godot", action="store_true")
        elif action == "build":
            child.add_argument("--playtest", choices=("off", "auto", "require"), default="off")
            child.add_argument("--repair-mode", choices=("apply", "suggest"), default="apply")
            child.add_argument("--overwrite", action="store_true")
        elif action in {"verify", "playtest"}:
            child.add_argument("--playtest", choices=("off", "auto", "require"),
                               default="require" if action == "playtest" else "off")
            child.add_argument("--frames", type=int, default=300)
            child.add_argument("--timeout", type=float, default=120.0)
        elif action == "package":
            child.add_argument("--overwrite", action="store_true")
            child.add_argument("--dry-run", action="store_true")
    options = parser.parse_args(argv)
    try:
        if options.action == "init":
            return _init(options)
        if options.action == "jeeves":
            from skeleton.developer.jeeves_game_cli import run_jeeves_game_cli
            command = [options.jeeves_action]
            for flag, value in (("--kind", options.kind), ("--brief", options.brief),
                                ("--digest", options.digest), ("--approve", options.approve),
                                ("--console", options.console), ("--genre", options.genre),
                                ("--period", options.period), ("--profile", options.profile),
                                ("--evidence", options.evidence),
                                ("--target", options.target), ("--source", options.source),
                                ("--output", options.output), ("--mode", options.mode),
                                ("--factor", options.factor), ("--passes", options.passes),
                                ("--gate", options.gate),
                                ("--page", options.page),
                                ("--page-size", options.page_size),
                                ("--native-width", options.native_width),
                                ("--native-height", options.native_height),
                                ("--screen-width", options.screen_width),
                                ("--screen-height", options.screen_height),
                                ("--pixel-aspect-num", options.pixel_aspect_num),
                                ("--pixel-aspect-den", options.pixel_aspect_den)):
                if value is not None:
                    command.extend([flag, str(value)])
            if options.include_notes:
                command.append("--include-notes")
            if options.dry_run:
                command.append("--dry-run")
            if options.repair_generated:
                command.append("--repair-generated")
            return run_jeeves_game_cli(command, _project(options.project))
        if options.action == "catalog":
            from skeleton.forge.eras import list_eras
            from skeleton.forge.archetypes import default_library
            return {"ok": True, "action": "catalog", "eras": list_eras(),
                    "archetypes": sorted({"auto", "vision", *default_library().names()}),
                    "build_targets": ["godot"], "package_formats": ["godot-source-zip"]}
        root = _project(options.project)
        if options.action == "info":
            data = _load(root)
            return {"ok": True, "action": "info", "project": str(root), "config": data,
                    "build_present": (root / "build" / "godot" / "FORGE_MANIFEST.json").is_file()}
        if options.action == "doctor":
            return _doctor(root, require_godot=options.require_godot)
        if options.action == "build":
            return _build(root, options)
        if options.action in {"verify", "playtest"}:
            if not 1 <= options.frames <= 12000 or not 1 <= options.timeout <= 900:
                _fail("playtest limits: frames 1..12000, timeout 1..900 seconds")
            return _verify(root, options)
        if options.action == "assets":
            _load(root)
            return {"ok": True, "action": "assets", "project": str(root),
                    "inventory": _check_assets(root)}
        if options.action == "package":
            return _package(root, options)
    except (GameCLIError, OSError) as exc:
        return {"ok": False, "action": options.action, "error": str(exc)}
    return {"ok": False, "error": "unknown game command"}
