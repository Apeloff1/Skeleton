"""Read a private local API bearer without command-line or environment exposure."""
from __future__ import annotations
from pathlib import Path
import os,stat
from ...model.gguf.file_guard import open_trusted_root
from ...authority.canonical import ContractViolation


def read_bearer(path:str|Path)->str:
    source=Path(path).absolute()
    if source.name in ('','.','..') or not source.name.isascii():
        raise ContractViolation('unsafe bearer basename')
    root=open_trusted_root(source.parent)
    fd=None
    try:
        fd=os.open(source.name,os.O_RDONLY|os.O_NOFOLLOW|
                   getattr(os,'O_NONBLOCK',0)|getattr(os,'O_CLOEXEC',0),dir_fd=root)
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
             or info.st_mode&0o077 or info.st_uid!=os.getuid()
             or not 32<=info.st_size<=513):
            raise ContractViolation('bearer must be one private 0600 regular file')
        data=os.read(fd,514)
        after=os.fstat(fd)
        if (len(data)!=info.st_size or info.st_size!=after.st_size
            or after.st_mtime_ns!=info.st_mtime_ns or
            after.st_ctime_ns!=info.st_ctime_ns):
            raise ContractViolation('bearer modified while opening')
        if data.endswith(b'\n'):
            data=data[:-1]
        if not 32<=len(data)<=512 or any(not 33<=c<=126 for c in data):
            raise ContractViolation('noncanonical private bearer content')
        return data.decode('ascii')
    finally:
        if fd is not None:os.close(fd)
        os.close(root)
