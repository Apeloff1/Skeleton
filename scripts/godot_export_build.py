#!/usr/bin/env python3
"""Forge a game through the ten-stage GameForge pipeline and export a real
Godot 4.3 build.

Steps per archetype: GameForgeRun (ingest..seal) -> write project ->
``godot --headless --import`` -> ``godot --headless --export-release`` ->
assert the exported executable + .pck exist -> boot the exported build
headless for a bounded number of frames and scan the log for errors.

Fails closed: missing binary, missing templates, failed stage, missing
artifact or a boot error all exit non-zero. A JSON manifest
(``export_manifest.json``) records sizes and SHA-256 digests for every
artifact so CI can upload a verifiable bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ARCHETYPES = ("extraction", "combat_loop", "pipeline")
PRESET = "Linux"
EXPORT_REL = Path("builds/linux/game.x86_64")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd: List[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    env = dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1")
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False, env=env)


def forge_project(archetype: str, vision: str, root: Path) -> Dict[str, Any]:
    from skeleton.context.pipeline import GameForgeRun

    out = GameForgeRun().execute(vision, archetype=archetype, target="godot", project_root=str(root), overwrite=True)
    stages = [s["name"] for s in out["run"]["stages"] if s["status"] == "SUCCEEDED"]
    if not out["succeeded"] or len(stages) != 10:
        raise SystemExit(f"[{archetype}] pipeline incomplete: {stages}")
    return {"stages": stages, "file_count": len(out.get("files") or {}), "era": out.get("era")}


def export_project(godot: str, root: Path, *, timeout: float, boot_frames: int) -> Dict[str, Any]:
    from skeleton.forge.playtest import scan_log

    imp = _run([godot, "--headless", "--editor", "--quit", "--path", str(root)], root, timeout)
    (root / "builds/linux").mkdir(parents=True, exist_ok=True)
    exp = _run([godot, "--headless", "--path", str(root), "--export-release", PRESET, str(EXPORT_REL)], root, timeout)
    exe = root / EXPORT_REL
    pck = exe.with_suffix(".pck")
    log = imp.stdout + imp.stderr + exp.stdout + exp.stderr
    if exp.returncode != 0 or not exe.is_file() or not pck.is_file():
        raise SystemExit(f"export failed (rc={exp.returncode}) for {root}:\n{log[-4000:]}")
    exe.chmod(0o755)
    boot = _run([str(exe), "--headless", "--quit-after", str(boot_frames)], exe.parent, timeout)
    boot_log = boot.stdout + boot.stderr
    errors = scan_log(boot_log)
    if boot.returncode != 0 or errors:
        raise SystemExit(f"exported build failed to boot (rc={boot.returncode}): {errors[:10]}\n{boot_log[-3000:]}")
    return {
        "executable": str(exe.relative_to(root)),
        "pck": str(pck.relative_to(root)),
        "executable_bytes": exe.stat().st_size,
        "pck_bytes": pck.stat().st_size,
        "executable_sha256": _sha256(exe),
        "pck_sha256": _sha256(pck),
        "boot_frames": boot_frames,
        "boot_errors": errors,
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="godot-export", help="output directory")
    ap.add_argument("--godot", default=os.environ.get("SKELETON_GODOT_BIN") or os.environ.get("GODOT_BINARY") or "godot")
    ap.add_argument("--archetype", action="append", dest="archetypes")
    ap.add_argument("--vision", default="a tense neon extraction raid through a collapsing arcology")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--boot-frames", type=int, default=120)
    ap.add_argument("--forge-only", action="store_true", help="forge projects without invoking Godot")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {"godot": args.godot, "preset": PRESET, "builds": {}}
    for archetype in args.archetypes or DEFAULT_ARCHETYPES:
        root = out / archetype
        entry = forge_project(archetype, args.vision, root)
        if not args.forge_only:
            entry["export"] = export_project(args.godot, root, timeout=args.timeout, boot_frames=args.boot_frames)
        manifest["builds"][archetype] = entry
        print(f"[{archetype}] OK {json.dumps(entry.get('export', {}).get('executable_sha256', 'forge-only'))}")
    (out / "export_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
