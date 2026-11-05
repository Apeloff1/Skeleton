"""Descriptor-rooted private runtime path admission (POSIX only)."""
from __future__ import annotations
import os,stat
from pathlib import Path
from contextlib import contextmanager
from .contracts import SpineError

def _flags():
    if os.name!='posix' or not hasattr(os,'O_NOFOLLOW') or not hasattr(os,'O_DIRECTORY'):
        raise SpineError('private runtime requires POSIX O_NOFOLLOW and O_DIRECTORY')
    return os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY | getattr(os,'O_CLOEXEC',0)

def open_private_root(path:str|Path)->int:
    """Anchor every component; reject symlinks, other users and group access."""
    flags=_flags();raw=Path(path).absolute()
    if '..' in raw.parts: raise SpineError('invalid private root')
    fd=os.open('/', flags)
    try:
        for component in raw.parts[1:]:
            nxt=os.open(component,flags,dir_fd=fd);os.close(fd);fd=nxt
        info=os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or (info.st_mode&0o077):
            raise SpineError('private directory must be mode 0700')
        if hasattr(os,'getuid') and info.st_uid != os.getuid():
            raise SpineError('private directory ownership mismatch')
        return fd
    except BaseException:
        os.close(fd);raise

def private_file_at(root_fd:int,name:str,*,create:bool=False)->int:
    if not name or '/' in name or name in ('.','..') or any(ord(x)<32 for x in name):
        raise SpineError('unsafe private basename')
    flags=os.O_RDWR|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
    if create:flags|=os.O_CREAT|os.O_EXCL
    fd=os.open(name,flags,0o600,dir_fd=root_fd)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_mode&0o077:
            raise SpineError('private regular file required, no hardlinks')
        if hasattr(os,'getuid') and info.st_uid!=os.getuid():
            raise SpineError('private file owner mismatch')
        return fd
    except BaseException:
        os.close(fd);raise

def validate_private_sidecars(root_fd:int,name:str)->None:
    for suffix in ('','-wal','-shm','-journal'):
        try:fd=private_file_at(root_fd,name+suffix)
        except FileNotFoundError: continue
        else:os.close(fd)
