"""Openat descriptor custody for model shards: symlinks/parent swaps fail closed."""
from __future__ import annotations
import os
from pathlib import Path
import stat
from contextlib import contextmanager
from typing import Iterator
from .manifest import _path,GGUFManifestError


def open_trusted_root(root:Path|str)->int:
    if os.name!='posix' or not all(hasattr(os,x) for x in ('O_DIRECTORY','O_NOFOLLOW')):
        raise GGUFManifestError("model custody requires POSIX nofollow directory descriptors")
    p=Path(root).absolute()
    if '..' in p.parts:
        raise GGUFManifestError("parent traversal in model root")
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd); fd=nxt
            mode=os.fstat(fd).st_mode
            if mode & 0o022:
                raise GGUFManifestError("model directory writable by group/others")
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def regular_beneath(root_fd:int, relative:str, expected_size:int)->Iterator[int]:
    parts=_path(relative).split('/')
    fd=os.dup(root_fd)
    file_fd=None
    try:
        for part in parts[:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_NOFOLLOW|os.O_DIRECTORY,dir_fd=fd)
            os.close(fd);fd=nxt
            if os.fstat(fd).st_mode & 0o022:
                raise GGUFManifestError("untrusted writable shard parent")
        file_fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_NONBLOCK',0),dir_fd=fd)
        st=os.fstat(file_fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size!=expected_size:
            raise GGUFManifestError("shard is not regular or declared size has changed")
        if st.st_mode&0o022:
            raise GGUFManifestError("shard is writable by group or others")
        if st.st_nlink!=1:
            raise GGUFManifestError("shard must not have alias hardlinks")
        yield file_fd
        if os.fstat(file_fd).st_size!=expected_size:
            raise GGUFManifestError("shard size changed while reading")
    finally:
        if file_fd is not None:os.close(file_fd)
        os.close(fd)
