"""Revalidate native staging against original archive bytes, not a self-issued receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import stat

from emerald_asset_preflight import PIN
from qualify_emerald_retained_archives import inspect_native
from recover_emerald_assets import ordinary
from stage_emerald_native import stage, verify_model
from prepare_emerald_delivery import verify as verify_delivery

import hashlib

RECEIPT = "skeleton_stage_receipt.json"
MODEL = "Models/emerald_continuum.glb"
TOP = {"Art", "Models", "PaintKit", "Unreal"}
EXCLUDED = {"__pycache__", "Saved", "Binaries", "Intermediate"}
EXTENSIONS = {".png", ".gif", ".json", ".md", ".npz", ".glb", ".ini", ".uproject", ".cs", ".h", ".cpp", ".py", ".ps1"}


def expected_inventory(source, pin):
    original = inspect_native(source, pin)
    rows = {}
    for row in original["inventory"]:
        relative = PurePosixPath(row["path"])
        if relative.parts[0] in TOP and not (EXCLUDED & set(relative.parts)) and relative.suffix.lower() in EXTENSIONS:
            rows[row["path"]] = {"path": row["path"], "bytes": row["bytes"], "sha256": row["sha256"]}
    if MODEL in rows:
        raise ValueError("unexpected model in source")
    rows[MODEL] = {"path": MODEL, "bytes": pin["modelBytes"], "sha256": pin["modelSha256"]}
    return rows


def scan(target, expected):
    target = Path(target)
    if target.is_symlink() or not target.is_dir():
        raise ValueError("native target must be an ordinary directory")
    present = {}
    queue = [(target, 0)]
    visited = 0
    while queue:
        directory, depth = queue.pop()
        if depth > 32:
            raise ValueError("native directory depth quota")
        for path in directory.iterdir():
            visited += 1
            if visited > 4096:
                raise ValueError("native directory entry quota")
            relative = path.relative_to(target).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("unsafe staged member")
            if stat.S_ISDIR(info.st_mode):
                queue.append((path, depth + 1))
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("unsafe staged file")
            if relative == RECEIPT:
                continue
            row = expected.get(relative)
            if row is None:
                raise ValueError("unexpected staged member: " + relative)
            with ordinary(path) as (stream, before):
                if before.st_size != row["bytes"]:
                    raise ValueError("staged size mismatch: " + relative)
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != row["sha256"]:
                    raise ValueError("staged digest mismatch: " + relative)
            present[relative] = row
    if set(present) != set(expected):
        raise ValueError("missing staged members")
    return [present[key] for key in sorted(present)]


def verify(target, source, pin):
    target = Path(target)
    expected = expected_inventory(source, pin)
    inventory = scan(target, expected)
    with ordinary(target / RECEIPT) as (stream, before):
        if not 0 < before.st_size <= 1024 * 1024:
            raise ValueError("staging receipt exceeds quota")
        reported = json.loads(stream.read())
    canonical = {"schema": 1, "files": inventory,
                 "model_sha256": pin["modelSha256"], "source_sha256": pin["sourceSha256"],
                 "equipment_enabled": False, "engine_compiled": False,
                 "physical_rtx_verified": False, "artist_approved": False}
    if reported != canonical:
        raise ValueError("staging receipt differs from original-derived inventory")
    verify_model(target / MODEL, pin)
    return {"schema": "skeleton.emerald.native-staging-revalidation.v1",
            "native_staging_qualified": True,
            "staged_files": len(inventory),
            "staged_bytes": sum(row["bytes"] for row in inventory),
            "model_sha256": pin["modelSha256"], "source_sha256": pin["sourceSha256"],
            "equipment_enabled": False, "engine_compiled": False,
            "physical_rtx_verified": False, "artist_approved": False,
            "release_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("stage", "verify"))
    parser.add_argument("--delivery", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    verify_delivery(args.delivery, pin)
    source = args.delivery / "emerald-atelier-fold-source.zip"
    model = args.delivery / "emerald_continuum.glb"
    if args.mode == "stage":
        stage(source, model, args.target, pin["native"])
    print(json.dumps(verify(args.target, source, pin["native"]), indent=2))


if __name__ == "__main__":
    main()
