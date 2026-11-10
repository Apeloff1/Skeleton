"""Fail-closed evidence publication outside the repo and model directories."""
from __future__ import annotations
import json, os, stat
from pathlib import Path
from .contracts import QualificationError
from ...model.gguf.file_guard import open_trusted_root
from ...model.gguf.manifest import GGUFManifestError


def publish_private_report(root: Path, filename: str, payload: dict) -> None:
    """Write a canonical report exclusively; no overwrite, links or partial names."""
    if (not isinstance(filename,str) or not filename.endswith('.json') or
        not 1 <= len(filename) <= 100 or '/' in filename or chr(92) in filename or
        filename in ('.json', '..json') or filename.startswith('.')):
        raise QualificationError('invalid qualification report name')
    encoded = (json.dumps(payload,sort_keys=True,separators=(',',':'),
                         allow_nan=False,ensure_ascii=True)+chr(10)).encode('utf8')
    if len(encoded) > 16_384:
        raise QualificationError('qualification receipt oversized')
    try:
        fdroot = open_trusted_root(root)
    except GGUFManifestError as exc:
        # Preserve the fail-closed permission check at the source boundary;
        # callers of the qualification API receive its documented error type.
        raise QualificationError("qualification report directory is unsafe") from exc
    try:
        if os.fstat(fdroot).st_mode & 0o077:
            raise QualificationError('qualification report directory must be private')
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=fdroot)
        try:
            offset = 0
            while offset < len(encoded):
                written = os.write(fd,encoded[offset:])
                if written <= 0:
                    raise QualificationError('cannot write qualification report')
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(fdroot)
    finally:
        os.close(fdroot)
