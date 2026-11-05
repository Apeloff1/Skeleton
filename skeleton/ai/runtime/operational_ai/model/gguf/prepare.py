"""Split a REAL operator-installed GGUF into <99MB immutable, verified shards.

This is explicit operator action and writes only outside Git. Never downloads
weights, creates padding, or grants publication rights based on model text.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os,json,stat,tempfile,shutil,ctypes
from .manifest import Shard,GGUFModelManifest,GGUFManifestError,MAX_SHARD,MAX_MODEL
from .file_guard import open_trusted_root,regular_beneath

CHUNK=1<<20

@dataclass(frozen=True,slots=True)
class PrepareReceipt:
    model_id:str
    model_sha:str
    total_bytes:int
    shards:int
    destination:str
    manifest_sha:str


def prepare_gguf(input_path:str|Path,output_dir:str|Path,*,model_id:str,
                 license:str,source:str,rights_approved:bool,
                 shard_bytes:int=95_000_000,context_ceiling:int=8192,
                 memory_bytes:int=4_000_000_000,
                 gpu_layers_ceiling:int=0)->PrepareReceipt:
    if type(shard_bytes) is not int or not 1_000_000<=shard_bytes<=MAX_SHARD:
        raise GGUFManifestError('shard target outside permitted bytes')
    p=Path(input_path).absolute(); out=Path(output_dir).absolute()
    if not p.is_file() or p.is_symlink():raise GGUFManifestError('source model must be a real regular file')
    if out.exists() or out.is_symlink():raise GGUFManifestError('output inventory already exists')
    if out in p.parents or p==out:
        raise GGUFManifestError('model split output must be separate from the original source')
    source_st=p.lstat()
    if (not stat.S_ISREG(source_st.st_mode) or source_st.st_size>MAX_MODEL
        or source_st.st_size<25 or source_st.st_mode&0o022):
        raise GGUFManifestError('invalid or mutable oversized model file')
    if not out.parent.is_dir() or out.parent.is_symlink() or out.parent.stat().st_mode&0o022:
        raise GGUFManifestError('output parent must be private and pre-existing')
    fd_root=open_trusted_root(p.parent)
    staging=Path(tempfile.mkdtemp(prefix='.gguf-stage-',dir=out.parent))
    staging.chmod(0o700)
    complete=sha256();shards=[];total=0
    try:
        with regular_beneath(fd_root,p.name,source_st.st_size) as source_fd:
            if os.pread(source_fd,4,0)!=b'GGUF':
                raise GGUFManifestError('input is not GGUF')
            index=0
            while True:
                block=os.read(source_fd,min(shard_bytes,source_st.st_size-total))
                if not block:break
                if len(block)<min(shard_bytes,source_st.st_size-total):
                    # Short reads are legal; coalesce until declared shard chunk size.
                    parts=[block];remaining=min(shard_bytes,source_st.st_size-total)-len(block)
                    while remaining:
                        part=os.read(source_fd,min(remaining,CHUNK))
                        if not part:raise GGUFManifestError('source model truncated mid-split')
                        parts.append(part);remaining-=len(part)
                    block=b''.join(parts)
                if index>=64:raise GGUFManifestError('too many model shards')
                part_name=f'weights/{model_id}_part_{index:03}.ggufpart'
                destination=staging/part_name
                destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                f=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
                try:
                    view=memoryview(block)
                    while view:
                        n=os.write(f,view)
                        if n<=0:raise GGUFManifestError('split output write failed')
                        view=view[n:]
                    os.fsync(f)
                finally:os.close(f)
                local=sha256(block).hexdigest();complete.update(block);total+=len(block)
                shards.append(Shard(part_name,len(block),local));index+=1
            if os.read(source_fd,1):raise GGUFManifestError('unexpected model source extension')
        if total!=source_st.st_size:raise GGUFManifestError('source model total bytes changed')
        manifest=GGUFModelManifest(model_id,tuple(shards),complete.hexdigest(),total,
            license,source,rights_approved,context_ceiling,gpu_layers_ceiling,memory_bytes)
        manifest_bytes=json.dumps(manifest.to_record(),sort_keys=True,indent=2).encode()+b'\n'
        (staging/'model.manifest.json').write_bytes(manifest_bytes)
        # This ledger feeds the existing 1.9 GB ordered package builder.
        # The package builder uses `file` relative to the payload root and
        # `destination` relative to `bundle/stages/MBW-02/payload`. Preserve the
        # model ID namespace and include the manifest itself: without this the
        # bundle cannot be converted back into a bootable GGUF deployment.
        artifacts = [{'file': s.path,
            'destination': f'models/{model_id}/{s.path}', 'wave': 'MBW-02',
            'bytes': s.bytes, 'sha256': s.sha256, 'license': license,
            'source': source, 'rights_approved': rights_approved} for s in shards]
        artifacts.append({'file': 'model.manifest.json',
            'destination': f'models/{model_id}/model.manifest.json',
            'wave': 'MBW-02', 'bytes': len(manifest_bytes),
            'sha256': sha256(manifest_bytes).hexdigest(), 'license': license,
            'source': source, 'rights_approved': rights_approved})
        ledger = {'schema_version': 1, 'artifacts': artifacts}
        (staging/'approved_artifacts.json').write_text(json.dumps(ledger,indent=2,sort_keys=True)+'\n')
        for name in ('model.manifest.json','approved_artifacts.json'):
            os.chmod(staging/name,0o400)
        # Never replace a previously created destination, even across races.
        if os.name!='posix' or not hasattr(os,'memfd_create'):
            raise GGUFManifestError('atomic no-replace publication requires Linux')
        libc=ctypes.CDLL(None,use_errno=True)
        try:
            renameat2=libc.renameat2
        except AttributeError as exc:
            raise GGUFManifestError('atomic RENAME_NOREPLACE unavailable') from exc
        renameat2.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        renameat2.restype=ctypes.c_int
        if renameat2(-100,os.fsencode(staging),-100,os.fsencode(out),1)!=0:
            err=ctypes.get_errno()
            raise GGUFManifestError(f'atomic, no-replace publication refused (errno={err})')
        staging=None
        return PrepareReceipt(model_id,complete.hexdigest(),total,len(shards),str(out),manifest.manifest_digest)
    finally:
        os.close(fd_root)
        if staging is not None:shutil.rmtree(staging,ignore_errors=True)
