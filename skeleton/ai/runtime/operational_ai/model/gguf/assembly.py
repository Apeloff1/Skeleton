"""Assemble immutable sharded GGUF weights in a sealed Linux anonymous descriptor.

Not a packaging shortcut: every source shard is streamed, digested, validated,
and the composite digest must match the independently approved manifest. The
model is loaded from /proc/self/fd while the custody descriptor stays open.
"""
from __future__ import annotations
import fcntl
import hashlib
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Protocol,Callable
from .manifest import GGUFModelManifest,GGUFManifestError
from .file_guard import open_trusted_root,regular_beneath

_BLOCK=1<<20


@dataclass(slots=True)
class ModelAssembly:
    fd:int
    bytes:int
    sha256:str
    manifest_digest:str
    sealed:bool
    _closed:bool=False

    @property
    def path(self)->str:
        if self._closed:raise GGUFManifestError("assembly already closed")
        return f"/proc/self/fd/{self.fd}"

    def close(self)->None:
        if not self._closed:
            os.close(self.fd)
            self._closed=True

    def __enter__(self)->"ModelAssembly":return self
    def __exit__(self,*_:object)->None:self.close()


def _write_all(fd:int,data:bytes)->None:
    view=memoryview(data)
    while view:
        written=os.write(fd,view)
        if written<=0:raise GGUFManifestError("anonymous weight assembly write failed")
        view=view[written:]


def assemble_model(root:Path|str, manifest:GGUFModelManifest,
                   *,max_bytes:int=1_940_000_000,check_cancel:Callable[[],bool]|None=None)->ModelAssembly:
    if type(max_bytes) is not int or not manifest.total_bytes<=max_bytes<=1_940_000_000:
        raise GGUFManifestError("assembly memory budget unavailable")
    if not hasattr(os,'memfd_create') or not Path('/proc/self/fd').is_dir():
        raise GGUFManifestError("sealed anonymous GGUF assembly requires Linux memfd and procfs")
    root_fd=open_trusted_root(root)
    mem_fd=None
    try:
        mem_fd=os.memfd_create('skeleton-verified-gguf', getattr(os,'MFD_CLOEXEC',0)|getattr(os,'MFD_ALLOW_SEALING',0))
        combined=hashlib.sha256()
        count=0
        for shard in manifest.shards:
            if check_cancel is not None and check_cancel():raise GGUFManifestError("assembly cancelled")
            with regular_beneath(root_fd,shard.path,shard.bytes) as sf:
                local=hashlib.sha256()
                remaining=shard.bytes
                while remaining:
                    if check_cancel is not None and check_cancel():raise GGUFManifestError("assembly cancelled")
                    buf=os.read(sf,min(_BLOCK,remaining))
                    if not buf:raise GGUFManifestError("shard truncated during streaming")
                    local.update(buf); combined.update(buf)
                    _write_all(mem_fd,buf)
                    remaining-=len(buf);count+=len(buf)
                if os.read(sf,1):raise GGUFManifestError("shard grew during streaming")
                if local.hexdigest()!=shard.sha256:
                    raise GGUFManifestError("shard sha256 does not match manifest")
        if count!=manifest.total_bytes or combined.hexdigest()!=manifest.model_sha256:
            raise GGUFManifestError("complete GGUF identity does not match manifest")
        if os.fstat(mem_fd).st_size!=count:
            raise GGUFManifestError("anonymous image size drift")
        try:
            fcntl.fcntl(mem_fd,fcntl.F_ADD_SEALS,
                        fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SEAL)
        except (AttributeError,OSError) as exc:
            raise GGUFManifestError("cannot seal immutable model image") from exc
        result=ModelAssembly(mem_fd,count,combined.hexdigest(),manifest.manifest_digest,True)
        mem_fd=None
        return result
    finally:
        os.close(root_fd)
        if mem_fd is not None:os.close(mem_fd)
