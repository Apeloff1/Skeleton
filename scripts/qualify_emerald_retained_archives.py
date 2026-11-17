"""Independently qualify retained Emerald archives without a standalone GLB.

Never executes archives, publishes assets, rewrites pins, or confers release approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

from recover_emerald_assets import copy_exact
from stage_emerald_native import member, PREFIX, MAX_FILE, MAX_TOTAL
from emerald_asset_preflight import PIN, assess

# Resolve frontend/scripts relative to repository root, not caller cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "frontend/scripts"))
from install_emerald_assets import install, verify_directory

CHUNK = 1024 * 1024
REQUIRED = {
    "Models/manifest.json", "Models/artisan_geometry.npz",
    "Art/basecolor.png", "Art/normal.png", "Art/orm.png",
    "Unreal/EmeraldCrawler.uproject", "Unreal/Tools/qualify.ps1",
    "Unreal/Tools/build_unreal.ps1", "Unreal/Tools/import_reference_volume.py",
}
MODEL = "Models/emerald_continuum.glb"


def inspect_native(archive: Path, pin: dict) -> dict:
    inventory = []
    seen = set()
    files = set()
    directories = set()
    manifest = None
    total = 0
    with tempfile.TemporaryDirectory(prefix="emerald-source-audit-") as work:
        snapshot = Path(work) / "source.zip"
        copy_exact(archive, snapshot, pin["sourceBytes"], pin["sourceSha256"])
        with zipfile.ZipFile(snapshot) as bundle:
            entries = bundle.infolist()
            if not 0 < len(entries) <= 512:
                raise ValueError("native archive entry count")
            for entry in entries:
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if entry.flag_bits & 1:
                    raise ValueError("encrypted native member")
                if entry.filename == PREFIX and entry.is_dir():
                    if mode not in (0, stat.S_IFDIR) or entry.file_size:
                        raise ValueError("unsafe native root")
                    if "" in seen:
                        raise ValueError("duplicate native root")
                    seen.add("")
                    continue
                relative = member(entry.filename.rstrip("/") if entry.is_dir() else entry.filename)
                name = relative.as_posix()
                key = name.casefold()
                if key in seen:
                    raise ValueError("duplicate native member")
                seen.add(key)
                if entry.is_dir():
                    if mode not in (0, stat.S_IFDIR) or entry.file_size:
                        raise ValueError("unsafe native directory")
                    directories.add(key)
                    continue
                if mode not in (0, stat.S_IFREG):
                    raise ValueError("unsafe native member type")
                if key == MODEL.casefold():
                    raise ValueError("unexpected standalone model in source archive")
                total += entry.file_size
                if not 0 <= entry.file_size <= MAX_FILE or total > MAX_TOTAL:
                    raise ValueError("native archive size quota")
                files.add(key)
                digest = hashlib.sha256()
                captured = bytearray() if name == "Models/manifest.json" else None
                if captured is not None and not 0 < entry.file_size <= CHUNK:
                    raise ValueError("native model manifest size")
                size = 0
                with bundle.open(entry) as source:
                    while block := source.read(CHUNK):
                        size += len(block)
                        if size > entry.file_size:
                            raise ValueError("native member overflow")
                        digest.update(block)
                        if captured is not None:
                            captured.extend(block)
                if size != entry.file_size:
                    raise ValueError("native member truncated")
                if captured is not None:
                    manifest = json.loads(captured)
                inventory.append({"path": name, "bytes": size, "sha256": digest.hexdigest()})
    for name in files | directories:
        parts = name.split("/")
        if any("/".join(parts[:n]) in files for n in range(1, len(parts))):
            raise ValueError("native file obstructs directory")
    if not REQUIRED <= {row["path"] for row in inventory}:
        raise ValueError("native archive missing required source dependencies")
    if not isinstance(manifest, dict) or (
        manifest.get("sha256") != pin["modelSha256"]
        or manifest.get("file_size") != pin["modelBytes"]
        or manifest.get("animations") != 380
        or manifest.get("joints") != 108
    ):
        raise ValueError("native manifest and standalone model pin mismatch")
    return {
        "archive_sha256": pin["sourceSha256"], "archive_bytes": pin["sourceBytes"],
        "entries": len(inventory), "uncompressed_bytes": total,
        "inventory": sorted(inventory, key=lambda row: row["path"]),
        "declared_model_sha256": manifest["sha256"],
        "declared_model_bytes": manifest["file_size"],
        "declared_animations": manifest["animations"], "declared_joints": manifest["joints"],
        "standalone_model_in_source_archive": False,
    }


def qualify(directory: Path, pin: dict) -> dict:
    paths = {role: directory / name for role, name in (
        ("web", "emerald-skeleton-web-assets.zip"),
        ("source", "emerald-atelier-fold-source.zip"),
        ("model", "emerald_continuum.glb"),
    )}
    receipt = assess(paths, pin)
    receipt["schema"] = "skeleton.emerald.retained-archives.v1"
    receipt["web_archive_qualified"] = False
    receipt["native_source_archive_qualified"] = False
    if receipt["assets"]["web"]["state"] == "verified":
        with tempfile.TemporaryDirectory(prefix="emerald-web-audit-") as work:
            target = Path(work) / "payload"
            install(paths["web"], target, pin)
            verify_directory(target, pin)
        receipt["web_archive_qualified"] = True
    if receipt["assets"]["source"]["state"] == "verified":
        receipt["native_source"] = inspect_native(paths["source"], pin["native"])
        receipt["native_source_archive_qualified"] = True
    receipt["standalone_model_bytes_verified"] = receipt["assets"]["model"]["state"] == "verified"
    receipt["native_staging_qualified"] = False
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    receipt = qualify(args.directory, json.loads(PIN.read_text(encoding="utf-8")))
    print(json.dumps(receipt, indent=2))
    if not (receipt["web_archive_qualified"] and receipt["native_source_archive_qualified"]):
        return 2
    return 0 if receipt["standalone_model_bytes_verified"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
