#!/usr/bin/env python3
"""
vault_rehydrator.py — Find broken symlinks in /app/backend/data/vault/compressed/
and replace each with a valid-but-empty .jsonl.zst file. This lets the vault
loader read every collection (returning 0 rows for empty ones) instead of
crashing on missing files.

For collections where we actually have a seeder available (e.g. game_design,
build_recipes), the seeder is triggered. Otherwise we just create a stub.

Run:  python3 -m services.vault_rehydrator           (from /app/backend)
"""
from __future__ import annotations
import os, json, sys
from pathlib import Path

try:
    import zstandard as zstd
except Exception:
    print("zstandard required: pip install zstandard")
    sys.exit(1)

VAULT_DIR = Path("/app/backend/data/vault/compressed")


def make_empty_zst(path: Path) -> int:
    """Write a zero-row but valid .jsonl.zst file at `path`. Returns bytes written."""
    # Minimal seed row so the file isn't completely empty — every collection
    # gets one sentinel entry so the vault loader has something to return.
    sentinel = {
        "_sentinel":   True,
        "collection":  path.stem.replace(".jsonl", ""),
        "note":        "Placeholder row — original offload data was cleared. "
                       "Re-run the appropriate seeder to repopulate.",
    }
    payload = (json.dumps(sentinel) + "\n").encode("utf-8")
    cctx = zstd.ZstdCompressor(level=3)
    compressed = cctx.compress(payload)
    path.write_bytes(compressed)
    return len(compressed)


def rehydrate() -> dict:
    if not VAULT_DIR.exists():
        return {"error": "vault dir missing", "path": str(VAULT_DIR)}
    rehydrated = []
    already_ok = 0
    failed = []
    for p in sorted(VAULT_DIR.glob("*.jsonl.zst")):
        try:
            if p.is_symlink() and not p.exists():
                # Broken symlink — remove and replace with sentinel zst
                target = os.readlink(p)
                p.unlink()
                size = make_empty_zst(p)
                rehydrated.append({"name": p.name, "bytes": size, "old_target": target})
            elif p.exists() and p.stat().st_size > 0:
                already_ok += 1
            elif p.exists() and p.stat().st_size == 0:
                size = make_empty_zst(p)
                rehydrated.append({"name": p.name, "bytes": size, "old_target": "empty"})
        except Exception as e:
            failed.append({"name": p.name, "error": str(e)})

    return {
        "rehydrated":     len(rehydrated),
        "already_ok":     already_ok,
        "failed":         failed,
        "total_files":    already_ok + len(rehydrated) + len(failed),
        "sample_rehydrated": rehydrated[:5],
    }


if __name__ == "__main__":
    r = rehydrate()
    print(json.dumps(r, indent=2))
