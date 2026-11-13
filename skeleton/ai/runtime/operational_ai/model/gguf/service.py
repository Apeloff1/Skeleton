"""Operator-approved model activation with strict capacity, bytes and runtime proof."""
from __future__ import annotations
from pathlib import Path
import os
from .manifest import GGUFModelManifest,GGUFManifestError,load_manifest
from .file_guard import open_trusted_root,regular_beneath
from .assembly import assemble_model
from .memory import assess_memory
from .runtime import GGUFBackend


def load_approved_manifest(root:Path|str,filename:str='model.manifest.json')->GGUFModelManifest:
    if '/' in filename or '\\' in filename or not filename.endswith('.json') or len(filename)>128:
        raise GGUFManifestError('model manifest must be a bounded direct-child file')
    rootfd=open_trusted_root(root)
    try:
        with regular_beneath(rootfd,filename,os.stat(filename,dir_fd=rootfd,follow_symlinks=False).st_size) as fd:
            if os.fstat(fd).st_size>128_000:
                raise GGUFManifestError('model manifest too large')
            raw=os.read(fd,128001)
        return load_manifest(raw)
    finally:os.close(rootfd)


def activate_model(root:Path|str,manifest:GGUFModelManifest,*,
                   n_ctx:int=2048,n_gpu_layers:int=0,n_threads:int=4,
                   min_free_memory_bytes:int=512_000_000)->GGUFBackend:
    assessment=assess_memory(manifest,reserve_bytes=min_free_memory_bytes)
    if not assessment.accepted:
        raise GGUFManifestError('model activation memory admission refused')
    assembly=assemble_model(root,manifest)
    try:
        return GGUFBackend(manifest,assembly,n_ctx=n_ctx,n_gpu_layers=n_gpu_layers,n_threads=n_threads)
    except BaseException:
        assembly.close()
        raise
