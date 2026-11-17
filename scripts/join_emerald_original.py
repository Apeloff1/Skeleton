"""Reassemble the two recovered original GLB parts without weakening the pinned identity."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from recover_emerald_assets import ordinary
from dragon_atelier_admit import PIN

PARTS = PIN.parent / "atelier" / "emeraldOriginalParts.json"


def join(directory: Path, output: Path, manifest: dict, pin: dict):
    if os.path.lexists(output):
        raise FileExistsError(output)
    if output.name != "emerald_continuum.glb":
        raise ValueError("use the original GLB filename")
    if manifest["model_sha256"] != pin["modelSha256"]:
        raise ValueError("part manifest differs from repository pin")
    rows = manifest["parts"]
    if len(rows) != 2 or [r["name"] for r in rows] != ["emerald_continuum.glb.part01", "emerald_continuum.glb.part02"]:
        raise ValueError("unexpected part list")
    if sum(r["size"] for r in rows) != pin["modelBytes"]:
        raise ValueError("part sizes differ from model pin")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".emerald-join-", dir=output.parent, delete=False) as dst:
            temporary = Path(dst.name)
            whole = hashlib.sha256()
            for part in rows:
                with ordinary(directory / part["name"]) as (src, st):
                    if st.st_size != part["size"]:
                        raise ValueError("part size mismatch: " + part["name"])
                    remaining = st.st_size
                    h = hashlib.sha256()
                    while remaining:
                        block = src.read(min(remaining, 1024 * 1024))
                        if not block:
                            raise ValueError("truncated part")
                        whole.update(block)
                        h.update(block)
                        dst.write(block)
                        remaining -= len(block)
                    if src.read(1) or h.hexdigest() != part["sha256"]:
                        raise ValueError("part digest mismatch: " + part["name"])
            if whole.hexdigest() != pin["modelSha256"]:
                raise ValueError("assembled original SHA-256 mismatch")
            dst.flush()
            os.fsync(dst.fileno())
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    join(args.directory, args.output, json.loads(PARTS.read_text()), json.loads(PIN.read_text())["native"])
    print("Reassembled original SHA-256 verified; no hardware or release qualification.")


if __name__ == "__main__":
    main()
