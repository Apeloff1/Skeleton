"""Descriptor-anchored no-follow acquisition for untrusted operator documents.

No `Path.resolve()` + later file reopening; this closes the common time-of-
check/time-of-use replacement race for a document's data descriptor.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import os
import stat
from .contracts import KnowledgeError, KnowledgePolicy, source_path

_NOFOLLOW = getattr(os, 'O_NOFOLLOW', 0)
_DIRECTORY = getattr(os, 'O_DIRECTORY', 0)
_CLOEXEC = getattr(os, 'O_CLOEXEC', 0)


def _open_chain(path: Path) -> int:
    if os.name != 'posix' or not _NOFOLLOW or not _DIRECTORY:
        raise KnowledgeError('descriptor-anchored source custody requires POSIX O_NOFOLLOW')
    base = path.absolute()
    fd = os.open('/', os.O_RDONLY | _DIRECTORY | _CLOEXEC)
    try:
        for part in base.parts[1:]:
            if part in ('', '.'): continue
            if part == '..': raise KnowledgeError('noncanonical corpus root')
            next_fd = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=fd)
            os.close(fd); fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise KnowledgeError('source root must be user-owned and private mode 0700')
        return fd
    except BaseException:
        os.close(fd); raise


@contextmanager
def opened_source(root: str | Path, relative: str, *, policy: KnowledgePolicy) -> Iterator[int]:
    """A held file descriptor; symlinked parents, hardlinks and special files fail."""
    source_path(relative)
    base_fd = _open_chain(Path(root))
    current = base_fd
    try:
        segments = relative.split('/')
        for part in segments[:-1]:
            next_fd = os.open(part, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=current)
            if current != base_fd: os.close(current)
            current = next_fd
        fd = os.open(segments[-1], os.O_RDONLY | _NOFOLLOW | _CLOEXEC | getattr(os,'O_NONBLOCK',0), dir_fd=current)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o022 or info.st_size < 1
                or info.st_size > policy.max_document_bytes):
                raise KnowledgeError('source must be a bounded, owned, unique regular file')
            yield fd
        finally:
            os.close(fd)
    finally:
        if current != base_fd: os.close(current)
        os.close(base_fd)


def read_source(root: str | Path, relative: str, *, policy: KnowledgePolicy) -> bytes:
    with opened_source(root, relative, policy=policy) as fd:
        before = os.fstat(fd)
        chunks = []
        count = 0
        while count <= policy.max_document_bytes:
            block = os.read(fd, min(64 * 1024, policy.max_document_bytes + 1 - count))
            if not block: break
            chunks.append(block);count += len(block)
        after = os.fstat(fd)
        if (not 0 < count <= policy.max_document_bytes
            or before.st_size != count or after.st_size != count
            or before.st_mtime_ns != after.st_mtime_ns or before.st_ctime_ns != after.st_ctime_ns
            or before.st_ino != after.st_ino or before.st_dev != after.st_dev):
            raise KnowledgeError('source changed while ingested or exceeds byte ceiling')
        return b''.join(chunks)
