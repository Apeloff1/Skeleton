"""Offline CLI: compare two genuine Sega homebrew ROMs without publishing either.

Designed for CI after a clean SDCC rebuild. An external CI runner, not this
byte reader, witnesses separate compiler invocations. Never uploads firmware
or third-party game data; only a bounded, content-addressed evidence JSON.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from skeleton.ai.game_builder.native_release_intake import (
    _json, _no_follow, _open_directory, _read_bounded,
)
from skeleton.ai.game_builder.sega_reproducibility import (
    verify_rebuilt_sega_cartridge,
)


def emit_receipt(destination: str | Path, receipt: dict[str, object]) -> None:
    """Create-only, no-follow, atomic-name exclusive output: never overwrite."""
    destination = Path(destination)
    if destination.name in {"", ".", ".."}:
        raise ValueError("invalid native provenance output basename")
    rootfd = _open_directory(destination.parent)
    fd = -1
    try:
        fd = os.open(
            destination.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow()
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=rootfd,
        )
        data = json.dumps(
            receipt, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
        ).encode("utf-8") + b"\n"
        if len(data) > 16384:
            raise ValueError("Sega reproducibility receipt exceeded expected size")
        with os.fdopen(fd, "wb") as out:
            fd = -1
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        if fd >= 0:
            os.close(fd)
        # In the event of an exception after creation, do not leave a
        # truncated/trustworthy-looking JSON artifact in CI output.
        try:
            os.unlink(destination.name, dir_fd=rootfd)
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(rootfd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",choices=("sega_master_system","sega_game_gear"),required=True)
    parser.add_argument("--source-dir",type=Path,required=True)
    parser.add_argument("--first-rom",type=Path,required=True)
    parser.add_argument("--rebuilt-rom",type=Path,required=True)
    parser.add_argument("--first-evidence",type=Path,required=True)
    parser.add_argument("--source-sha256",required=True)
    parser.add_argument("--author-sha256",required=True)
    parser.add_argument("--toolchain-revision",required=True)
    parser.add_argument("--receipt-out",type=Path,required=True)
    args = parser.parse_args()
    prior = _json(
        _read_bounded(args.first_evidence, max_bytes=16384),
        "original Sega first-build report",
    )
    result = verify_rebuilt_sega_cartridge(
        target=args.target,
        source_directory=args.source_dir,
        first_cartridge=args.first_rom,
        rebuilt_cartridge=args.rebuilt_rom,
        first_build_evidence=prior,
        expected_source_sha256=args.source_sha256,
        expected_author_declaration_sha256=args.author_sha256,
        toolchain_git_revision=args.toolchain_revision,
    )
    emit_receipt(args.receipt_out,result.public_receipt())
    print(json.dumps(result.public_receipt(),sort_keys=True))


if __name__ == "__main__":
    main()
