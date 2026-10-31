"""Produce a bounded original offline PCM sound effect with no overwrite.

python -m scripts.game.synthesize_original_sound patch.json --out sound.wav
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from skeleton.audio.pipeline import AudioError
from skeleton.audio.original_synthesis import SoundPatch, synthesize

MAX_PATCH_BYTES = 8192


def _load_patch(path: Path) -> object:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PATCH_BYTES:
            raise AudioError("patch must be a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_PATCH_BYTES + 1)
        if len(raw) > MAX_PATCH_BYTES:
            raise AudioError("patch exceeds byte budget")
        return json.loads(raw)
    finally:
        os.close(fd)


def _write_new(path: Path, payload: bytes) -> None:
    """No-clobber write. The operator controls the destination parent directory."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short audio write")
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        info = os.fstat(fd)
        os.close(fd)
        try:
            if path.stat(follow_symlinks=False).st_ino == info.st_ino:
                path.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.inspect and args.out is None:
            raise AudioError("--out required unless --inspect")
        patch = SoundPatch.from_mapping(_load_patch(args.patch))
        sound = synthesize(patch)
        if not args.inspect:
            _write_new(args.out, sound.wav_bytes)
        print(json.dumps({"ok": True, "written": not args.inspect, **sound.receipt()}, sort_keys=True))
        return 0
    except (AudioError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"original-sound: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
