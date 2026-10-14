"""Bounded local authorship-document custody for original homebrew pipelines.

These are operator-supplied documentary bytes, NOT a rights determination.
The function uses an opened regular-file descriptor and both pathname and
descriptor identity checks; it never follows symlinks or contacts a network.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat

MAX_RIGHTS_EVIDENCE_BYTES = 8 * 1024 * 1024


class RightsEvidenceError(ValueError):
    """A proposed authorship document was not a stable bounded local file."""


@dataclass(frozen=True, slots=True)
class RightsEvidenceReceipt:
    document_sha256: str
    content_bytes: int
    bytes_read_from_local_regular_file: bool = True
    independent_ownership_verified: bool = False
    legal_clearance_issued: bool = False

    def __post_init__(self) -> None:
        if (not isinstance(self.document_sha256, str)
                or len(self.document_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.document_sha256)
                or type(self.content_bytes) is not int
                or not 1 <= self.content_bytes <= MAX_RIGHTS_EVIDENCE_BYTES
                or self.bytes_read_from_local_regular_file is not True
                or self.independent_ownership_verified is not False
                or self.legal_clearance_issued is not False):
            raise RightsEvidenceError("rights evidence receipt cannot grant clearance")


def read_rights_evidence(path: str | Path) -> RightsEvidenceReceipt:
    """Hash one stable original evidence file, without loading it into RAM.

    Never accept a changed path, FIFO, device, symlink, empty document or
    content over the 8 MiB custody budget. No content is copied into output.
    """
    if not isinstance(path, (str, Path)):
        raise RightsEvidenceError("rights evidence must be a local file path")
    try:
        location = Path(path).expanduser()
        before = location.lstat()
        if (not stat.S_ISREG(before.st_mode)
                or not 1 <= before.st_size <= MAX_RIGHTS_EVIDENCE_BYTES):
            raise RightsEvidenceError("rights evidence requires a bounded local regular file")
        flags = (
            os.O_RDONLY | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        fd = os.open(location, flags)
        digest = sha256()
        count = 0
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise RightsEvidenceError("rights evidence path changed during admission")
            while True:
                chunk = source.read(min(256 * 1024, MAX_RIGHTS_EVIDENCE_BYTES + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_RIGHTS_EVIDENCE_BYTES:
                    raise RightsEvidenceError("rights evidence size budget exceeded")
                digest.update(chunk)
            after = os.fstat(source.fileno())
        current = location.lstat()
        if (not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                or count != opened.st_size):
            raise RightsEvidenceError("rights evidence changed during review intake")
    except FileNotFoundError as exc:
        raise RightsEvidenceError("rights evidence requires an ordinary local regular file") from exc
    except (OSError, RuntimeError) as exc:
        raise RightsEvidenceError("unreadable or substituted rights evidence file") from exc
    return RightsEvidenceReceipt(digest.hexdigest(), count)
