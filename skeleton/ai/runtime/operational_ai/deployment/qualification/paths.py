"""Fail-closed evidence publication outside the repo and model directories."""
from __future__ import annotations
import json, os, stat
from pathlib import Path
from .contracts import QualificationError
# Report paths and model shard paths have different trust requirements:
# a sticky, root-owned /tmp is acceptable for a private report subtree, but
# model source/shard custody remains governed by the stricter GGUF guard.


def _open_private_report_root(root: Path) -> int:
    """Open an owner-private directory through no-follow path descriptors.

    Only OS-root-owned sticky intermediates (such as /tmp) may be publicly
    writable. All other writable ancestors fail closed; the leaf must be
    owned by the current process and mode-private.
    """
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise QualificationError("private report custody requires POSIX no-follow")
    target = Path(root).absolute()
    if ".." in target.parts:
        raise QualificationError("report parent traversal denied")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in target.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            if st.st_mode & 0o022:
                if st.st_uid != 0 or not (st.st_mode & stat.S_ISVTX):
                    raise QualificationError("untrusted writable report ancestor")
        final = os.fstat(fd)
        if final.st_uid != os.geteuid() or final.st_mode & 0o077:
            raise QualificationError("qualification report directory must be private")
        return fd
    except BaseException:
        os.close(fd)
        raise


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
    fdroot = _open_private_report_root(root)
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
        # A renamed ancestor must never become a successful publication
        # receipt merely because the original directory fd remains open.
        reopened = _open_private_report_root(root)
        try:
            before, after = os.fstat(fdroot), os.fstat(reopened)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise QualificationError("report parent changed during publication")
        finally:
            os.close(reopened)
    finally:
        os.close(fdroot)
