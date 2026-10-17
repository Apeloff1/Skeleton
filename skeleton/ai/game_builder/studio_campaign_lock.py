"""Cross-platform process lifetime locking for local Jeeves studio campaigns.

The operating system releases the lock on process exit or crash. A persistent
lockfile prevents unsafe unlink/recreate inode races; no time-based lock
stealing is permitted during multi-week production.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Iterator


class StudioCampaignBusy(RuntimeError):
    """Another process currently owns this campaign's source publication."""


@contextmanager
def campaign_lock(destination: str | Path) -> Iterator[None]:
    root = Path(destination).absolute()
    if not root.parent.is_dir() or root.parent.is_symlink():
        raise StudioCampaignBusy("campaign requires a real parent directory")
    lockfile = root.parent / ("." + root.name + ".campaign.lock")
    if lockfile.is_symlink():
        raise StudioCampaignBusy("campaign lockfile must not be a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lockfile, flags, 0o600)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise StudioCampaignBusy("campaign already locked by another process") from exc
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StudioCampaignBusy("campaign already locked by another process") from exc
        locked = True
        yield
    finally:
        if locked:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


__all__ = ["StudioCampaignBusy", "campaign_lock"]
