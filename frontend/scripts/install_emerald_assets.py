"""Install the exact offline Emerald visual asset distribution; never download or execute it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
import stat

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "src/features/Jeeves/companion/emeraldAssetPin.json"
TARGET = ROOT / "public/emerald/v1"
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")
HASH = re.compile(r"[0-9a-f]{64}")
MANIFEST = "manifest.integration.json"
MAX_ENTRY = 64 * 1024 * 1024
MAX_TOTAL = 96 * 1024 * 1024

def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def checked_manifest(raw: bytes, pin: dict) -> dict:
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != pin["web"]["manifestSha256"]:
        raise ValueError("manifest digest mismatch")
    manifest = json.loads(raw)
    if manifest.get("schema") != 1 or manifest.get("assetSet") != pin["assetSet"]:
        raise ValueError("asset identity mismatch")
    files = manifest["files"]
    if len(files) != pin["web"]["entries"]:
        raise ValueError("file count mismatch")
    seen = set()
    total = 0
    for entry in files:
        name, size, sha = entry["path"], entry["bytes"], entry["sha256"]
        if not isinstance(name, str) or not NAME.fullmatch(name) or name == MANIFEST or name in seen:
            raise ValueError("invalid or duplicate asset path")
        if type(size) is not int or not 0 < size <= MAX_ENTRY or not HASH.fullmatch(sha):
            raise ValueError("invalid asset metadata")
        seen.add(name)
        total += size
    if total > MAX_TOTAL or len(set(manifest["scripts"])) != len(manifest["scripts"]) or not set(manifest["scripts"]) <= seen:
        raise ValueError("invalid script set or total")
    return manifest

def verify_directory(target: Path, pin: dict) -> None:
    if not target.is_dir() or target.is_symlink():
        raise ValueError("asset directory is not an ordinary directory")
    manifest_file = target / MANIFEST
    if manifest_file.is_symlink() or not manifest_file.is_file() or manifest_file.stat().st_size > 65536:
        raise ValueError("invalid installed manifest")
    manifest = checked_manifest(manifest_file.read_bytes(), pin)
    expected = {MANIFEST, *(item["path"] for item in manifest["files"])}
    if {p.name for p in target.iterdir()} != expected:
        raise ValueError("unexpected installed file")
    for entry in manifest["files"]:
        path = target / entry["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("installed asset mismatch: " + entry["path"])

def exact_snapshot(archive: Path, destination: Path, pin: dict) -> None:
    initial=archive.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError("offline archive is not an ordinary file")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)|getattr(os,"O_BINARY",0)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    with os.fdopen(os.open(archive,flags),"rb") as src:
        first=os.fstat(src.fileno())
        if not stat.S_ISREG(first.st_mode) or identity(first)!=identity(initial) or first.st_size!=pin["web"]["bytes"]:
            raise ValueError("offline archive identity mismatch")
        sha=hashlib.sha256()
        remaining=first.st_size
        with destination.open("xb") as out:
            while remaining:
                block=src.read(min(remaining,1024*1024))
                if not block:raise ValueError("archive truncated")
                sha.update(block);out.write(block);remaining-=len(block)
            if src.read(1) or sha.hexdigest()!=pin["web"]["sha256"] or identity(first)!=identity(os.fstat(src.fileno())):
                raise ValueError("offline archive identity mismatch")


def install(archive: Path, target: Path, pin: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".emerald-stage-", dir=target.parent))
    staging = work/"payload"
    staging.mkdir()
    try:
        snapshot=work/"verified.zip"
        exact_snapshot(archive,snapshot,pin)
        if os.path.lexists(target):
            verify_directory(target,pin)
            return
        with zipfile.ZipFile(snapshot) as bundle:
            entries = bundle.infolist()
            names = [item.filename for item in entries]
            if len(entries) != pin["web"]["entries"] + 1 or len({name.casefold() for name in names}) != len(entries):
                raise ValueError("unexpected archive entries")
            for item in entries:
                mode = (item.external_attr >> 16) & 0o170000
                if not NAME.fullmatch(item.filename) or item.is_dir() or mode not in (0, 0o100000) or item.flag_bits & 1 or item.file_size > MAX_ENTRY:
                    raise ValueError("unsafe archive entry")
            info = bundle.getinfo(MANIFEST)
            if info.file_size > 65536:
                raise ValueError("manifest too large")
            raw = bundle.read(info)
            manifest = checked_manifest(raw, pin)
            if set(names) != {MANIFEST, *(item["path"] for item in manifest["files"])}:
                raise ValueError("archive manifest mismatch")
            (staging / MANIFEST).write_bytes(raw)
            for entry in manifest["files"]:
                name = entry["path"]
                if bundle.getinfo(name).file_size != entry["bytes"]:
                    raise ValueError("archive size mismatch")
                with bundle.open(name) as source, (staging / name).open("xb") as destination:
                    remaining = entry["bytes"]
                    while remaining:
                        block = source.read(min(remaining, 1024 * 1024))
                        if not block:
                            raise ValueError("truncated archive entry")
                        destination.write(block)
                        remaining -= len(block)
                    if source.read(1):
                        raise ValueError("excess archive bytes")
            verify_directory(staging, pin)
        if os.path.lexists(target):
            raise ValueError("concurrent installation; retry verification")
        os.rename(staging, target)
    finally:
        shutil.rmtree(work, ignore_errors=True)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    if args.verify:
        verify_directory(TARGET, pin)
    elif args.archive:
        install(args.archive, TARGET, pin)
    else:
        parser.error("supply the pinned local ZIP or --verify")
    print("Emerald offline assets verified:", pin["assetSet"])

if __name__ == "__main__":
    main()
