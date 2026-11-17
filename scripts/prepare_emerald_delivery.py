"""Create a self-contained offline Emerald delivery from exact retained assets.

Explicit local I/O only. Never publishes GitHub releases or executes archive code.
The destination parent must be trusted and writable solely by the operator.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from emerald_asset_preflight import ASSETS, PIN
from recover_emerald_assets import copy_exact
from rebuild_emerald_exact_binary import assemble
from qualify_emerald_retained_archives import qualify

RECEIPT = "delivery-receipt.json"
MODEL = "emerald_continuum.glb"


def receipt_for(result, pin):
    if not (result["all_exact_bytes_available"]
            and result["web_archive_qualified"]
            and result["native_source_archive_qualified"]
            and result["standalone_model_bytes_verified"]):
        raise ValueError("incomplete original custody")
    return {
        "schema": "skeleton.emerald.offline-delivery.v1",
        "asset_set": pin["assetSet"],
        "files": [
            {"name": filename, "bytes": pin[section][size], "sha256": pin[section][sha]}
            for _, filename, section, size, sha in ASSETS
        ],
        "web_archive_qualified": True,
        "native_source_archive_qualified": True,
        "native_staging_qualified": False,
        "engine_compiled": False,
        "physical_rtx_verified": False,
        "artist_approved": False,
        "release_qualified": False,
    }


def sync_directory(path):
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def publish(archives, parts, target, pin, *, model=None):
    archives, target = Path(archives).absolute(), Path(target).absolute()
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise ValueError("trusted existing destination parent required")
    if (parts is None) == (model is None):
        raise ValueError("provide exactly one of a complete model or transfer directory")
    lock = target.parent / ("." + target.name + ".emerald-delivery.lock")
    lock.mkdir(mode=0o700)
    temporary = None
    try:
        if os.path.lexists(target):
            raise FileExistsError(target)
        required = sum(pin[section][size] for _, _, section, size, _ in ASSETS)
        # Leave room for the assembler's private copies and installer snapshots.
        minimum = required + 2 * pin["native"]["modelBytes"] + 256 * 1024**2
        if shutil.disk_usage(target.parent).free < minimum:
            raise OSError("insufficient free storage for verified delivery")
        temporary = Path(tempfile.mkdtemp(prefix=".emerald-delivery-", dir=target.parent))
        for role, filename, section, size, sha in ASSETS:
            if role == "model":
                continue
            copy_exact(archives / filename, temporary / filename, pin[section][size], pin[section][sha])
        if model is None:
            assemble(Path(parts), temporary / MODEL, pin["native"])
        else:
            copy_exact(Path(model), temporary / MODEL, pin["native"]["modelBytes"], pin["native"]["modelSha256"])
        result = qualify(temporary, pin)
        receipt = receipt_for(result, pin)
        with (temporary / RECEIPT).open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(temporary)
        if os.path.lexists(target):
            raise FileExistsError(target)
        os.rename(temporary, target)
        temporary = None
        sync_directory(target.parent)
        return receipt
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
        lock.rmdir()


def verify(target, pin):
    target = Path(target)
    if target.is_symlink() or not target.is_dir():
        raise ValueError("invalid delivery directory")
    expected = {RECEIPT, *(filename for _, filename, *_ in ASSETS)}
    if {entry.name for entry in target.iterdir()} != expected:
        raise ValueError("unexpected or missing delivery member")
    receipt = target / RECEIPT
    if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 65536:
        raise ValueError("invalid delivery receipt")
    actual = json.loads(receipt.read_text(encoding="utf-8"))
    calculated = receipt_for(qualify(target, pin), pin)
    if actual != calculated:
        raise ValueError("delivery receipt mismatch")
    return calculated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    build = sub.add_parser("build")
    build.add_argument("--archives", type=Path, required=True)
    inputs = build.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--parts", type=Path)
    inputs.add_argument("--model", type=Path)
    build.add_argument("--target", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    result = publish(args.archives, args.parts, args.target, pin, model=args.model) if args.mode == "build" else verify(args.target, pin)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
