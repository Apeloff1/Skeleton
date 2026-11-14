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


def open_private_artifact_root(directory: Path, *, create: bool = False) -> int:
    """Open an owner-private artifact directory, optionally creating one leaf.

    Reuse trusted ancestor traversal; creation/open both anchor to the same
    parent descriptor. No path-based mkdir before custody validation.
    """
    if not isinstance(directory, Path) or not directory.is_absolute():
        raise GGUFManifestError("artifact directory must be an absolute path")
    if ".." in directory.parts or directory == directory.parent:
        raise GGUFManifestError("unsafe artifact directory")
    parent_fd = open_trusted_root(directory.parent)
    child_fd = None
    try:
        if create:
            try:
                os.mkdir(directory.name, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
        child_fd = os.open(
            directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
            getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd,
        )
        st = os.fstat(child_fd)
        if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
            raise GGUFManifestError("artifact directory must be owner-private")
        result, child_fd = child_fd, None
        return result
    finally:
        if child_fd is not None:
            os.close(child_fd)
        os.close(parent_fd)
