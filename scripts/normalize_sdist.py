#!/usr/bin/env python3
"""Normalize Python source distributions for byte-for-byte reproducibility."""

from __future__ import annotations

import argparse
import copy
import gzip
import io
import os
import tarfile
from pathlib import Path


_VOLATILE_PAX_KEYS = frozenset({"atime", "ctime", "mtime"})


def _normalize_member(member: tarfile.TarInfo, *, epoch: int) -> tarfile.TarInfo:
    normalized = copy.copy(member)
    normalized.mtime = epoch
    normalized.uid = 0
    normalized.gid = 0
    normalized.uname = ""
    normalized.gname = ""
    pax_headers = {
        key: value
        for key, value in normalized.pax_headers.items()
        if key not in _VOLATILE_PAX_KEYS
    }
    normalized.pax_headers = dict(sorted(pax_headers.items()))
    return normalized


def normalize_sdist(path: Path, *, source_date_epoch: int) -> None:
    if source_date_epoch < 0:
        raise ValueError("source_date_epoch cannot be negative")
    if not path.is_file():
        raise FileNotFoundError(path)

    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, mode="r:gz") as source:
        for member in source.getmembers():
            data: bytes | None = None
            if member.isfile():
                extracted = source.extractfile(member)
                if extracted is None:
                    raise ValueError(f"unable to read regular file from sdist: {member.name}")
                data = extracted.read()
            entries.append((_normalize_member(member, epoch=source_date_epoch), data))

    entries.sort(key=lambda item: item[0].name)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw,
                compresslevel=9,
                mtime=source_date_epoch,
            ) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as output:
                    for member, data in entries:
                        output.addfile(member, io.BytesIO(data) if data is not None else None)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("sdists", nargs="+", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for path in args.sdists:
        normalize_sdist(path, source_date_epoch=args.source_date_epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
