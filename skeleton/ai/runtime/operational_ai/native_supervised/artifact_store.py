"""Immutable owner-private POSIX native SFT checkpoint + candidate manifest store.

Both leaves are content addressed; partial publication is an incident hold.
No symlink paths, hardlink aliases, truncation, overwrite or provider fallback.
"""
from __future__ import annotations
from pathlib import Path
import os
import hashlib
import stat

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from ..model.gguf.file_guard import open_trusted_root,regular_beneath
from .canonical import encode,bytes_sha,require_sha
from .errors import reject

MAX_BYTES=256000000


def _root(directory:Path,*,create:bool)->int:
    if type(directory) is not Path or not directory.is_absolute():
        reject("store-absolute-path")
    if create:
        directory.mkdir(mode=0o700,parents=False,exist_ok=True)
    try:
        fd=open_trusted_root(directory)
    except (OSError,ValueError):
        reject("store-parent-custody")
    st=os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode) or st.st_mode&0o077 or st.st_uid!=os.geteuid():
        os.close(fd)
        reject("store-private-directory")
    return fd


def _exclusive(fd:int,name:str,data:bytes)->None:
    child=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|
                  os.O_CLOEXEC,0o600,dir_fd=fd)
    try:
        with os.fdopen(child,"wb",closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.unlink(name,dir_fd=fd)
        except OSError:
            pass
        raise


def publish(
    directory:Path,checkpoint:bytes,*,model_sha256:str,
    tokenizer_sha256:str,kind:str,source_sha256:str,
    training_receipt_sha256:str|None=None,
)->dict:
    if type(checkpoint) is not bytes or not 1<=len(checkpoint)<=MAX_BYTES:
        reject("store-checkpoint-budget")
    for label,val in (("model",model_sha256),("tokenizer",tokenizer_sha256),
                      ("source",source_sha256)):
        require_sha(val,label)
    if kind not in ("untrained-genesis","sft-candidate"):
        reject("store-artifact-kind")
    if training_receipt_sha256 is not None:
        require_sha(training_receipt_sha256,"training-receipt")
    if kind=="sft-candidate" and training_receipt_sha256 is None:
        reject("store-candidate-requires-training")
    restored=NativeLLMRuntime.restore_json(checkpoint.decode("utf-8"))
    if restored.model_digest!=model_sha256 or restored.tokenizer.digest!=tokenizer_sha256:
        reject("store-model-tokenizer-mismatch")
    content_sha=bytes_sha(checkpoint)
    manifest={
        "schema":"skeleton.native-supervised.artifact-manifest.v1",
        "checkpoint_sha256":content_sha,
        "model_sha256":model_sha256,
        "tokenizer_sha256":tokenizer_sha256,
        "source_sha256":source_sha256,
        "training_receipt_sha256":training_receipt_sha256,
        "kind":kind,"production_authorized":False,
        "release_certified":False,
    }
    metadata=encode(manifest)
    root=_root(directory,create=True)
    try:
        leaf=content_sha+".native.json"
        manifest_leaf=content_sha+".manifest.json"
        for name in (leaf,manifest_leaf):
            try:
                os.stat(name,dir_fd=root,follow_symlinks=False)
            except FileNotFoundError:
                continue
            reject("store-existing-artifact-held")
        _exclusive(root,leaf,checkpoint)
        # A crash between objects leaves an explicitly incomplete held state.
        _exclusive(root,manifest_leaf,metadata)
        os.fsync(root)
        return {
            "schema":"skeleton.native-supervised.publication.v1",
            "checkpoint_sha256":content_sha,
            "model_sha256":model_sha256,
            "tokenizer_sha256":tokenizer_sha256,
            "manifest_sha256":bytes_sha(metadata),
            "bytes":len(checkpoint),"kind":kind,
            "candidate_only":True,"serving_activated":False,
        }
    finally:
        os.close(root)


def read(directory:Path,expected_sha256:str,*,max_bytes:int=MAX_BYTES)->bytes:
    require_sha(expected_sha256,"checkpoint")
    if type(max_bytes) is not int or not 1<=max_bytes<=MAX_BYTES:
        reject("store-size-limit")
    root=_root(directory,create=False)
    try:
        leaf=expected_sha256+".native.json"
        st=os.stat(leaf,dir_fd=root,follow_symlinks=False)
        if not 1<=st.st_size<=max_bytes:
            reject("store-byte-ceiling")
        h=hashlib.sha256()
        segments=[]
        with regular_beneath(root,leaf,st.st_size) as child:
            remain=st.st_size
            while remain:
                part=os.read(child,min(65536,remain))
                if not part:
                    reject("store-short-read")
                h.update(part)
                segments.append(part)
                remain-=len(part)
            if os.read(child,1):
                reject("store-trailing-data")
        if h.hexdigest()!=expected_sha256:
            reject("store-digest-drift")
        # Publication of both files is required for an artifact to be readable.
        manifest_leaf=expected_sha256+".manifest.json"
        manifest_st=os.stat(manifest_leaf,dir_fd=root,follow_symlinks=False)
        if not 1<=manifest_st.st_size<=8192:
            reject("store-manifest-size")
        with regular_beneath(root,manifest_leaf,manifest_st.st_size) as child:
            manifest_raw=os.read(child,8193)
        from .canonical import decode
        metadata=decode(manifest_raw)
        if type(metadata) is not dict or metadata.get("checkpoint_sha256")!=expected_sha256:
            reject("store-manifest-mismatch")
        if metadata.get("release_certified") is not False:
            reject("store-manifest-release-fraud")
        content=b"".join(segments)
        native=NativeLLMRuntime.restore_json(content.decode("utf-8"))
        if native.model_digest!=metadata.get("model_sha256"):
            reject("store-weights-mismatch")
        if native.tokenizer.digest!=metadata.get("tokenizer_sha256"):
            reject("store-vocabulary-mismatch")
        return content
    finally:
        os.close(root)
