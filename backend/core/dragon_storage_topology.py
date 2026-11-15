"""Bounded operator-owned topology files for many-volume archives."""
from __future__ import annotations

import os
from pathlib import Path
import stat

from core.dragon_hoarder_bulk import StorageHeld

MAX_CONFIG_BYTES=4*1024*1024


def topology_config(variable):
    inline=os.environ.get(variable,"").strip()
    named=os.environ.get(variable+"_FILE","").strip()
    if inline and named:
        raise StorageHeld("choose one topology configuration source")
    if not named:
        if len(inline.encode("utf-8"))>MAX_CONFIG_BYTES:
            raise StorageHeld("topology configuration too large")
        return inline
    path=Path(named)
    if not path.is_absolute() or path.parent.resolve(strict=True)!=path.parent or path.is_symlink():
        raise StorageHeld("private canonical topology file required")
    parent=path.parent.stat()
    if os.name=="posix" and (parent.st_uid!=os.getuid() or parent.st_mode&0o077):
        raise StorageHeld("topology directory must be private")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>MAX_CONFIG_BYTES:
            raise StorageHeld("invalid topology file")
        if os.name=="posix" and (before.st_uid!=os.getuid() or before.st_mode&0o077):
            raise StorageHeld("topology file permissions")
        with os.fdopen(fd,"rb",closefd=False) as f:
            raw=f.read(MAX_CONFIG_BYTES+1)
        after=os.fstat(fd)
        current=path.lstat()
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(raw)>MAX_CONFIG_BYTES or len(raw)!=before.st_size or identity(before)!=identity(after) or identity(after)!=identity(current):
            raise StorageHeld("topology changed during read")
        return raw.decode("utf-8").strip()
    finally:
        os.close(fd)
