"""Opt-in pinned local ONNX sentence embeddings, with no remote model loader.

Disabled by default. The operator provisions both files and their exact SHA256
digests. Only a strict, finite CPU tensor contract is accepted. No model weights
are shipped or downloaded by Dragon; a missing dependency/config is held.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading

MAX_MODEL=1024**3
MAX_TOKENIZER=32*1024**2
MAX_BATCH=8
MAX_TOKENS=256
MAX_TEXT=24000
HEX=re.compile(r"[a-f0-9]{64}\Z")
_LOCK=threading.RLock()
_CACHED=None
_CONFIG=None


class EmbeddingHeld(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    model_sha256: str
    tokenizer: str
    tokenizer_sha256: str
    output: str
    dimensions: int
    max_tokens: int=128
    threads: int=2

    def __post_init__(self):
        if (not isinstance(self.model,str) or not isinstance(self.tokenizer,str)
                or not isinstance(self.model_sha256,str) or not HEX.fullmatch(self.model_sha256)
                or not isinstance(self.tokenizer_sha256,str) or not HEX.fullmatch(self.tokenizer_sha256)
                or not isinstance(self.output,str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}",self.output)
                or type(self.dimensions) is not int or not 32<=self.dimensions<=1024
                or type(self.max_tokens) is not int or not 16<=self.max_tokens<=MAX_TOKENS
                or type(self.threads) is not int or not 1<=self.threads<=8):
            raise ValueError("embedding configuration")
        if self.model==self.tokenizer:
            raise ValueError("independent model and tokenizer files required")

    @property
    def identity(self):
        blob=json.dumps({"schema":"dragon.local-onnx-mean-pool.v1",
                        "model_sha256":self.model_sha256,"tokenizer_sha256":self.tokenizer_sha256,
                        "output":self.output,"dimensions":self.dimensions,"max_tokens":self.max_tokens},
                        sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(blob).hexdigest()


def _read_verified(name,expected,maximum):
    path=Path(name)
    if not path.is_absolute() or path.resolve(strict=True)!=path:
        raise EmbeddingHeld("model path must be canonical and local")
    before=path.stat()
    if not stat.S_ISREG(before.st_mode) or not 1<=before.st_size<=maximum:
        raise EmbeddingHeld("model file bounds")
    if os.name=="posix" and before.st_mode&0o022:
        raise EmbeddingHeld("model is group/world writable")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(path,flags)
    try:
        opened=os.fstat(fd)
        if (opened.st_dev,opened.st_ino,opened.st_size)!=(before.st_dev,before.st_ino,before.st_size):
            raise EmbeddingHeld("model identity changed")
        with os.fdopen(fd,"rb",closefd=False) as stream:
            data=stream.read(maximum+1)
        after=os.fstat(fd)
        if len(data)!=before.st_size or len(data)>maximum or (after.st_size,after.st_mtime_ns)!=(opened.st_size,opened.st_mtime_ns):
            raise EmbeddingHeld("model bytes changed")
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest()!=expected:
        raise EmbeddingHeld("model digest mismatch")
    return data


class LocalEncoder:
    """ONNX bytes in memory; external graph initializer files are unsupported."""

    def __init__(self,config:EmbeddingConfig):
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise EmbeddingHeld("local optional embedding dependencies unavailable") from exc
        model=_read_verified(config.model,config.model_sha256,MAX_MODEL)
        tok=_read_verified(config.tokenizer,config.tokenizer_sha256,MAX_TOKENIZER)
        self.config=config
        self.identity=config.identity
        self.dimensions=config.dimensions
        self.np=np
        self.tokenizer=Tokenizer.from_str(tok.decode("utf-8"))
        self.tokenizer.enable_truncation(max_length=config.max_tokens)
        # Fixed padding avoids an unbounded model-side dynamic token allocation.
        self.tokenizer.enable_padding(length=config.max_tokens)
        options=ort.SessionOptions()
        options.intra_op_num_threads=config.threads
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern=False
        self.session=ort.InferenceSession(model,sess_options=options,providers=["CPUExecutionProvider"])
        self.inputs={i.name:i for i in self.session.get_inputs()}
        if set(self.inputs) not in ({"input_ids","attention_mask"},{"input_ids","attention_mask","token_type_ids"}):
            raise EmbeddingHeld("unsupported local model input contract")
        for info in self.inputs.values():
            if info.type!="tensor(int64)" or len(info.shape)!=2:
                raise EmbeddingHeld("unsupported input tensor")
            if isinstance(info.shape[1],int) and info.shape[1]!=config.max_tokens:
                raise EmbeddingHeld("model token dimension differs")
        outputs={o.name:o for o in self.session.get_outputs()}
        if config.output not in outputs or outputs[config.output].type!="tensor(float)":
            raise EmbeddingHeld("unsupported output tensor")
        if len(outputs[config.output].shape) not in (2,3):
            raise EmbeddingHeld("unsupported output rank")
        self._lock=threading.Lock()

    def encode(self,texts):
        if (not isinstance(texts,list) or not 1<=len(texts)<=MAX_BATCH
                or any(not isinstance(t,str) or not t.strip() or len(t)>MAX_TEXT for t in texts)):
            raise ValueError("embedding batch bounds")
        np=self.np
        with self._lock:
            tokens=self.tokenizer.encode_batch(texts)
            ids=np.asarray([x.ids for x in tokens],dtype=np.int64)
            mask=np.asarray([x.attention_mask for x in tokens],dtype=np.int64)
            if ids.shape!=(len(texts),self.config.max_tokens) or mask.shape!=ids.shape:
                raise EmbeddingHeld("tokenizer shape changed")
            if not np.all((mask==0)|(mask==1)) or np.any(mask.sum(axis=1)==0):
                raise EmbeddingHeld("empty or malformed attention mask")
            inputs={"input_ids":ids,"attention_mask":mask}
            if "token_type_ids" in self.inputs:
                types=np.asarray([x.type_ids for x in tokens],dtype=np.int64)
                if types.shape!=ids.shape:
                    raise EmbeddingHeld("token type shape changed")
                inputs["token_type_ids"]=types
            result=self.session.run([self.config.output],inputs)[0]
        if result.dtype!=np.float32 or result.ndim not in (2,3) or result.shape[0]!=len(texts):
            raise EmbeddingHeld("embedding output contract changed")
        if result.ndim==3:
            if result.shape[1]!=self.config.max_tokens or result.shape[2]!=self.dimensions:
                raise EmbeddingHeld("embedding output shape differs")
            masked=mask[...,None].astype(np.float32)
            result=(result*masked).sum(axis=1)/masked.sum(axis=1)
        if result.shape!=(len(texts),self.dimensions) or not np.all(np.isfinite(result)):
            raise EmbeddingHeld("non-finite or wrong-size embeddings")
        norms=np.linalg.norm(result.astype(np.float64),axis=1)
        if np.any(norms<=1e-12):
            raise EmbeddingHeld("zero embedding")
        return [(row/norm).tolist() for row,norm in zip(result,norms)]


def configured():
    return bool(os.getenv("SKL_DRAGON_LOCAL_EMBEDDING_JSON","").strip())


def encoder():
    """Return a single pinned encoder; changing identity requires process restart."""
    global _CACHED,_CONFIG
    raw=os.getenv("SKL_DRAGON_LOCAL_EMBEDDING_JSON","").strip()
    if not raw:
        raise EmbeddingHeld("local model not configured")
    if len(raw)>16*1024:
        raise EmbeddingHeld("embedding config too large")
    with _LOCK:
        if _CACHED is not None:
            if raw!=_CONFIG:
                raise EmbeddingHeld("embedding configuration changed")
            return _CACHED
        try:
            conf=EmbeddingConfig(**json.loads(raw))
            model=LocalEncoder(conf)
        except (TypeError,ValueError,OSError,RuntimeError,UnicodeError) as exc:
            raise EmbeddingHeld("local model did not qualify") from exc
        _CACHED=model
        _CONFIG=raw
        return model


def readiness():
    """No automatic model load as a side effect of a readiness request."""
    return {"configured":configured(),"loaded":_CACHED is not None,
            "model_identity":_CACHED.identity if _CACHED is not None else None,
            "remote_provider":False,"weights_shipped":False,"quality_verified":False}
