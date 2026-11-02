"""Read-only installed model inspection: actual shards, manifest, content digest.

This is an integrity/rights inventory check. It does not invoke llama.cpp,
modify local state, assert model quality or implicitly trust the source signer.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any

from ...model.gguf.manifest import GGUFManifestError,MAX_MODEL
from ...model.gguf.file_guard import open_trusted_root,regular_beneath
from ...model.gguf.service import load_approved_manifest
from .installer import InstallError,BLOCK


@dataclass(frozen=True,slots=True)
class InstalledModelReport:
    model_id:str
    model_sha256:str
    manifest_sha256:str
    shard_count:int
    model_bytes:int
    rights_approved:bool
    content_verified:bool
    native_inference_tested:bool=False
    release_certified:bool=False

    def to_record(self)->dict[str,Any]:
        return {key:getattr(self,key) for key in self.__dataclass_fields__}


def inspect_installed_model(root:Path|str)->InstalledModelReport:
    """Hash all model bytes once against manifest, without inference or mutation."""
    fd=open_trusted_root(root)
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise InstallError('installed model root must be private')
        manifest=load_approved_manifest(root)
        if manifest.total_bytes>MAX_MODEL:
            raise InstallError('model exceeds bounded capacity')
        combined=hashlib.sha256()
        size=0
        for shard in manifest.shards:
            with regular_beneath(fd,shard.path,shard.bytes) as source:
                h=hashlib.sha256()
                remaining=shard.bytes
                while remaining:
                    chunk=os.read(source,min(BLOCK,remaining))
                    if not chunk:
                        raise InstallError('installed model shard disappeared')
                    h.update(chunk);combined.update(chunk)
                    remaining-=len(chunk);size+=len(chunk)
                if os.read(source,1):
                    raise InstallError('model shard changed during verification')
                if h.hexdigest()!=shard.sha256:
                    raise InstallError('model shard digest mismatch')
        if size!=manifest.total_bytes or combined.hexdigest()!=manifest.model_sha256:
            raise InstallError('model composite digest mismatch')
        return InstalledModelReport(manifest.model_id,manifest.model_sha256,
            manifest.manifest_digest,len(manifest.shards),size,
            manifest.rights_approved,True)
    finally:
        os.close(fd)
