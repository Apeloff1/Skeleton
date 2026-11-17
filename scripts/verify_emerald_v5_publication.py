"""Exact raw binary custody for measured, unadopted Scholar wingfold candidate.

Never invents missing payloads, silently repairs checksums, or authorizes release.
Operator needs an existing trusted filesystem parent and exact original bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "assets/emerald/evolution-v5/scholar-wingfold-r1/publication-manifest.json"
EXPECTED = {
    "schema": "skeleton.emerald.scholar-wingfold-publication.v1",
    "stage": "scholar",
    "candidate": "scholar-wingfold-r1",
    "sha256": "3bf57f602c905c1c6864c2fdddcc7df3bd79699bcbccab0c5c2d83480fa7b877",
    "bytes": 113305100,
    "source_sha256": "db15c598fe3c6ef71384ca5f834c7eb2271014819ff0603207d454a87c03fdb9",
    "donor_sha256": "c9807afdffd61640cb2d8e1ed6d17250d4a9613965269f0e0bf12c0c979a9a6a",
    "radians": .18,
}
PART_BYTES = 32*1024**2
BUFFER = 1024**2


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contract():
    m = json.loads(MANIFEST.read_bytes())
    require(all(m.get(key) == value for key, value in EXPECTED.items()),
            "manifest no longer matches reviewed Scholar candidate")
    require(len(m["parts"]) == 4 and
            all(m.get(flag) is False for flag in (
                "automatic_adoption","artist_approved",
                "continuous_clearance_qualified","physical_rtx_verified","release_qualified")),
            "missing slices or falsely approved asset")
    offset = 0
    for i, row in enumerate(m["parts"]):
        length = min(PART_BYTES, m["bytes"]-offset)
        require(length > 0 and row == {
            "path": "assets/emerald/evolution-v5/scholar-wingfold-r1/scholar.glb.part"+str(i+1).zfill(3),
            "offset": offset,
            "bytes": length,
            "sha256": row.get("sha256"),
        } and isinstance(row["sha256"],str) and len(row["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in row["sha256"]),
            "noncontiguous or invalid binary slice")
        offset += length
    require(offset == m["bytes"], "incomplete binary manifest")
    return m


def verify_part(path, row):
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size == row["bytes"] and sha(path) == row["sha256"],
            "missing or mismatched original binary slice: "+row["path"])


def verify_tree(root):
    m = contract()
    root = Path(root)
    digest = hashlib.sha256()
    for row in m["parts"]:
        part = root/row["path"]
        verify_part(part, row)
        with part.open("rb") as source:
            while block := source.read(BUFFER):
                digest.update(block)
    require(digest.hexdigest() == m["sha256"], "whole asset SHA-256 differs")
    return {"candidate_sha256": m["sha256"], "parts": len(m["parts"]),
            "bytes": m["bytes"], "verified_tree": True,
            "automatic_adoption": False, "release_qualified": False}


def assemble(parts_directory, output):
    m = contract()
    parts_directory = Path(parts_directory)
    target = Path(output)
    require(target.name == "scholar.glb" and target.parent.is_dir()
            and not target.parent.is_symlink() and not os.path.lexists(target),
            "trusted unused scholar.glb output required")
    require(shutil.disk_usage(target.parent).free >= m["bytes"]+PART_BYTES,
            "insufficient free disk space")
    for row in m["parts"]:
        verify_part(parts_directory/Path(row["path"]).name, row)
    with tempfile.TemporaryDirectory(prefix=".scholar-wingfold-", dir=target.parent) as work:
        temporary = Path(work)/"scholar.glb"
        digest = hashlib.sha256()
        size = 0
        with temporary.open("xb") as stream:
            for row in m["parts"]:
                with (parts_directory/Path(row["path"]).name).open("rb") as source:
                    while block := source.read(BUFFER):
                        stream.write(block)
                        digest.update(block)
                        size += len(block)
            stream.flush()
            os.fsync(stream.fileno())
        require(size == m["bytes"] and digest.hexdigest() == m["sha256"],
                "assembled asset does not match original candidate")
        require(not os.path.lexists(target), "output changed concurrently")
        os.rename(temporary, target)
    return {"sha256": m["sha256"], "bytes": m["bytes"],
            "assembled_exact_bytes": True, "release_qualified": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("verify-tree","assemble"))
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--parts",type=Path)
    p.add_argument("--output",type=Path)
    args = p.parse_args()
    if args.mode == "verify-tree":
        result = verify_tree(args.root)
    else:
        require(args.parts is not None and args.output is not None,
                "--parts and --output required")
        result = assemble(args.parts,args.output)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
