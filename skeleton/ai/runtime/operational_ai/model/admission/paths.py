"""Directory descriptor custody for private cross-process model coordination."""
from __future__ import annotations
import os
import pwd
import stat
from pathlib import Path
from .contracts import AdmissionError, AdmissionUnsupported, AdmissionCorrupt

_DIR_FLAGS = (os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
              | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0))
_FILE_FLAGS = (os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
               | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NONBLOCK', 0))


def require_linux() -> None:
    if (os.name != 'posix' or not hasattr(os, 'getuid')
        or not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY')):
        raise AdmissionUnsupported('model capacity requires descriptor custody on POSIX')


def verified_dir(path: Path | str) -> int:
    require_linux()
    raw = os.fspath(path)
    if not raw.startswith('/') or any(x == '..' for x in raw.split('/')):
        raise AdmissionError('model capacity root must be an absolute canonical path')
    fd = os.open('/', _DIR_FLAGS)
    try:
        for part in raw.split('/')[1:]:
            if not part or part == '.':
                raise AdmissionError('noncanonical capacity directory')
            next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise AdmissionError('capacity root must be owner-only 0700')
        return fd
    except BaseException:
        os.close(fd)
        raise


def default_root() -> Path:
    require_linux()
    # Neither HOME nor XDG_RUNTIME_DIR is an authority for a private registry.
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if not home.is_absolute() or '..' in home.parts:
        raise AdmissionError('kernel principal home cannot anchor model capacity')
    return home / '.skeleton-ai-model-capacity'


def create_default_root() -> Path:
    root = default_root()
    # Open the user's real home through descriptors; do not follow symlink homes.
    home_fd = os.open('/', _DIR_FLAGS)
    try:
        for part in root.parent.parts[1:]:
            nxt = os.open(part, _DIR_FLAGS, dir_fd=home_fd)
            os.close(home_fd)
            home_fd = nxt
        if os.fstat(home_fd).st_uid != os.getuid():
            raise AdmissionError('home directory ownership differs')
        try:
            os.mkdir(root.name, mode=0o700, dir_fd=home_fd)
        except FileExistsError:
            pass
    finally:
        os.close(home_fd)
    root_fd = verified_dir(root)
    os.close(root_fd)
    return root


def open_file(root_fd: int, name: str, *, create: bool = False) -> int:
    if (not isinstance(name, str) or not name or len(name) > 128 or '/' in name
        or '\\' in name or name in ('.', '..') or any(ord(c) < 33 for c in name)):
        raise AdmissionError('invalid private coordination file name')
    flags = _FILE_FLAGS | (os.O_CREAT if create else 0)
    fd = os.open(name, flags, 0o600, dir_fd=root_fd)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
            or st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise AdmissionCorrupt('capacity coordination file is unsafe')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_file(fd: int, ceiling: int = 16384) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    size = 0
    while True:
        part = os.read(fd, min(ceiling + 1 - size, 8192))
        if not part:
            break
        size += len(part)
        if size > ceiling:
            raise AdmissionCorrupt('capacity coordination record oversized')
        chunks.append(part)
    return b''.join(chunks)


def write_file(fd: int, data: bytes) -> None:
    if type(data) is not bytes or not 1 <= len(data) <= 16384:
        raise AdmissionCorrupt('invalid bounded capacity record')
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    remaining = memoryview(data)
    while remaining:
        count = os.write(fd, remaining)
        if count <= 0:
            raise AdmissionCorrupt('incomplete capacity ledger write')
        remaining = remaining[count:]
    os.fsync(fd)
