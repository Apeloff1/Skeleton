"""Recover only exact repository-pinned Emerald assets from explicit local roots.
Read-only by default. No network, archive extraction, execution or replacement artwork.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from emerald_asset_preflight import ASSETS, PIN

CHUNK = 1024 * 1024
MAX_ENTRIES = 100_000
MAX_CANDIDATES = 1024
MAX_DEPTH = 16
MAX_HASH_BYTES = 32 * 1024**3


def fingerprint(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


@contextmanager
def ordinary(path):
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError("not an ordinary source file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or fingerprint(initial) != fingerprint(before):
            raise ValueError("source replaced before open")
        yield stream, before
        if fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
            raise ValueError("source changed during read")


def spec(pin):
    return {role: (name, pin[section][size], pin[section][sha])
            for role, name, section, size, sha in ASSETS}


def discover(roots, pin, *, max_entries=MAX_ENTRIES, max_candidates=MAX_CANDIDATES,
             max_depth=MAX_DEPTH, max_hash_bytes=MAX_HASH_BYTES):
    expected = spec(pin)
    by_size = {}
    for role, (_, size, _) in expected.items():
        by_size.setdefault(size, []).append(role)
    found = {role: [] for role in expected}
    seen_dirs = set()
    seen_files = set()
    stack = [(Path(root).absolute(), 0) for root in reversed(tuple(roots))]
    entries = candidates = hashed = errors = 0
    truncated = False
    while stack:
        path, depth = stack.pop()
        if entries >= max_entries:
            truncated = True
            break
        entries += 1
        try:
            st = path.lstat()
            mode = st.st_mode
            if stat.S_ISLNK(mode) or getattr(st, "st_file_attributes", 0) & 0x400:
                continue
            key = st.st_dev, st.st_ino
            if stat.S_ISDIR(mode):
                if key in seen_dirs:
                    continue
                seen_dirs.add(key)
                if depth >= max_depth:
                    truncated = True
                    continue
                # Bound directory enumeration as well as visited entries.
                with os.scandir(path) as directory:
                    children = []
                    for child in directory:
                        if entries + len(stack) + len(children) >= max_entries:
                            truncated = True
                            break
                        children.append(Path(child.path))
                stack.extend((child, depth + 1) for child in sorted(children, reverse=True))
                continue
            if not stat.S_ISREG(mode) or st.st_size not in by_size or key in seen_files:
                continue
            if candidates >= max_candidates or hashed + st.st_size > max_hash_bytes:
                truncated = True
                continue
            candidates += 1
            hashed += st.st_size
            with ordinary(path) as (stream, exact):
                if fingerprint(st) != fingerprint(exact):
                    raise ValueError("candidate changed before hash")
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            seen_files.add(key)
            for role in by_size[st.st_size]:
                if digest == expected[role][2]:
                    found[role].append(str(path))
        except (OSError, ValueError):
            errors += 1
    return {"schema": "skeleton.emerald.local-recovery.v1", "asset_set": pin["assetSet"],
            "matches": found, "entries_examined": entries, "hash_candidates": candidates,
            "hash_bytes_budgeted": hashed, "unreadable_entries": errors, "search_truncated": truncated,
            "all_exact_assets_located": all(found.values()), "hardware_qualified": False}


def copy_exact(source, destination, size, expected):
    # Publish through an exclusive hardlink, never replace existing data.
    destination = Path(destination)
    temporary = None
    try:
        with ordinary(Path(source)) as (stream, before):
            if before.st_size != size:
                raise ValueError("source size differs from pin")
            with tempfile.NamedTemporaryFile(prefix=".emerald-", dir=destination.parent, delete=False) as out:
                temporary = Path(out.name)
                sha = hashlib.sha256()
                remaining = size
                while remaining:
                    block = stream.read(min(CHUNK, remaining))
                    if not block:
                        raise ValueError("source truncated")
                    sha.update(block)
                    out.write(block)
                    remaining -= len(block)
                if stream.read(1) or sha.hexdigest() != expected:
                    raise ValueError("source digest differs from pin")
                out.flush()
                os.fsync(out.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def recover(report, pin, directory):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("recovery destination must be an existing ordinary directory")
    # Do not publish a partial set if discovery is incomplete.
    if not report["all_exact_assets_located"]:
        raise ValueError("not all exact assets located")
    expected = spec(pin)
    targets = {role: directory / name for role, (name, _, _) in expected.items()}
    for target in targets.values():
        if os.path.lexists(target):
            raise FileExistsError(target)
    published = []
    try:
        for role, (_, size, sha) in expected.items():
            copy_exact(Path(report["matches"][role][0]), targets[role], size, sha)
            published.append((targets[role], targets[role].lstat()))
    except (OSError, ValueError):
        for path, previous in reversed(published):
            try:
                if fingerprint(path.lstat()) == fingerprint(previous):
                    path.unlink()
            except OSError:
                pass
        raise
    return {role: str(path) for role, path in targets.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--recover-to", type=Path, help="optional explicit existing output directory")
    args = parser.parse_args()
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    result = discover(args.root, pin)
    if args.recover_to is not None:
        result["recovered_paths"] = recover(result, pin, args.recover_to)
    print(json.dumps(result, indent=2))
    return 0 if result["all_exact_assets_located"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
