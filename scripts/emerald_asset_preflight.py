"""Read-only, exact-byte inventory of the separately retained Emerald assets.
Never downloads, executes, creates receipts for missing files or qualifies hardware.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "frontend/src/features/Jeeves/companion/emeraldAssetPin.json"
ASSETS = (
    ("web", "emerald-skeleton-web-assets.zip", "web", "bytes", "sha256"),
    ("source", "emerald-atelier-fold-source.zip", "native", "sourceBytes", "sourceSha256"),
    ("model", "emerald_continuum.glb", "native", "modelBytes", "modelSha256"),
)


def witness(path: Path, expected_size: int, expected_sha: str) -> dict:
    result = {"state": "missing", "expected_bytes": expected_size, "expected_sha256": expected_sha}
    if path.is_symlink():
        return {**result, "state": "unsafe"}
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return result
    except OSError:
        return {**result, "state": "unreadable"}
    try:
        with os.fdopen(fd, "rb") as file:
            first = os.fstat(file.fileno())
            if not stat.S_ISREG(first.st_mode):
                return {**result, "state": "unsafe"}
            if first.st_size != expected_size:
                return {**result, "actual_bytes": first.st_size, "state": "size-mismatch"}
            sha = hashlib.file_digest(file, "sha256").hexdigest()
            last = os.fstat(file.fileno())
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(first) != identity(last):
                return {**result, "state": "changed-during-read"}
            return {**result, "state": "verified" if sha == expected_sha else "digest-mismatch",
                    "actual_bytes": first.st_size, "actual_sha256": sha}
    except OSError:
        return {**result, "state": "unreadable"}


def assess(paths: dict, pin: dict) -> dict:
    assets = {}
    for role, filename, section, size_key, sha_key in ASSETS:
        assets[role] = {"filename": filename, **witness(paths[role], pin[section][size_key], pin[section][sha_key])}
    return {
        "schema": "skeleton.emerald.offline-preflight.v1",
        "asset_set": pin["assetSet"],
        "assets": assets,
        "all_exact_bytes_available": all(a["state"] == "verified" for a in assets.values()),
        "engine_compiled": False,
        "physical_rtx_verified": False,
        "artist_approved": False,
        "release_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--web", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    paths = {role: getattr(args, role) or args.directory / filename for role, filename, *_ in ASSETS}
    receipt = assess(paths, json.loads(PIN.read_text(encoding="utf-8")))
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["all_exact_bytes_available"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
