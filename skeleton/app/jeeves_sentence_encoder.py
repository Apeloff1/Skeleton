"""Pinned CPU-only local transformer sentence encoder.

Optional dependencies are imported only when an operator supplies a local
ONNX model and a tokenizer JSON. Nothing is downloaded; no Python model
code, plugins, custom native operator libraries, or external ONNX weight
files are accepted by this adapter. It is not a sandbox for hostile models.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
from typing import Any

from skeleton.app.jeeves_approved_memory import MemoryRejected
from skeleton.app.jeeves_deliberation import digest,stable

SCHEMA="skeleton.jeeves.transformer-encoder.v1"
MAX_MODEL_BYTES=512*1024*1024
MAX_TOKENIZER_BYTES=32*1024*1024
MAX_INPUT_BYTES=4096
MAX_BATCH=16
MAX_LENGTH=512
MAX_DIMENSION=1536
MAX_GRAPH_NODES=50_000
MAX_INITIALIZERS=20_000
MAX_TENSOR_BYTES=512*1024*1024
MAX_ASSET_HEADER=4096
_SHA=re.compile(r"[a-f0-9]{64}\Z")
_TOKEN_NAME=re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}\Z")
_INPUTS=frozenset({"input_ids","attention_mask","token_type_ids"})
_DOMAINS=frozenset({"","ai.onnx"})
# The graph must use built-in standard operators. Restrict direct resource
# expansion and control-flow operators, rather than allow arbitrary sessions.
_BLOCKED_OPS=frozenset({"Loop","Scan","If","RandomNormal","RandomNormalLike",
                        "RandomUniform","RandomUniformLike","Multinomial",
                        "StringNormalizer","Tokenizer","TfIdfVectorizer"})


class EncoderUnavailable(MemoryRejected):
    """Missing optional runtime, invalid artifact or incompatible encoder."""


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise EncoderUnavailable("invalid encoder asset SHA-256")
    return value


def _int(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise EncoderUnavailable("invalid encoder numeric limit")
    return value


def _text(value,limit,*,empty=False):
    if type(value) is not str or (not empty and not value.strip()) or "\x00" in value:
        raise EncoderUnavailable("invalid encoder text")
    try:
        if len(value.encode("utf-8","strict"))>limit:
            raise EncoderUnavailable("encoder text exceeds UTF-8 budget")
    except UnicodeError:
        raise EncoderUnavailable("invalid encoder Unicode") from None
    return value


def _identity(details):
    return (details.st_dev,details.st_ino,details.st_size,details.st_mtime_ns,details.st_ctime_ns)


def _read_pinned(path: Path,expected: str,limit: int) -> tuple[bytes,tuple]:
    """Read one stable regular file; digest the exact bytes given to runtime."""
    _sha(expected)
    try:
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 1<=before.st_size<=limit:
            raise EncoderUnavailable("encoder file is not a bounded regular file")
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|
                   getattr(os,"O_NONBLOCK",0)|getattr(os,"O_BINARY",0))
        with os.fdopen(fd,"rb") as handle:
            if _identity(os.fstat(handle.fileno()))!=_identity(before):
                raise EncoderUnavailable("encoder file changed while opening")
            raw=handle.read(limit+1)
            if (len(raw)!=before.st_size or len(raw)>limit
                    or _identity(os.fstat(handle.fileno()))!=_identity(before)
                    or _identity(path.lstat())!=_identity(before)
                    or sha256(raw).hexdigest()!=expected):
                raise EncoderUnavailable("encoder file digest or custody mismatch")
        return raw,_identity(before)
    except OSError:
        raise EncoderUnavailable("pinned encoder file unavailable") from None


def _path(value):
    text=_text(value,2048)
    candidate=Path(text)
    if not candidate.is_absolute():
        raise EncoderUnavailable("encoder asset requires absolute local path")
    # No URL, UNC or remote-device prefix is accepted. It remains the
    # operator's responsibility to avoid mounted network filesystems.
    if text.startswith(("//","\\\\","\\\\?\\","\\\\.\\")):
        raise EncoderUnavailable("remote or device encoder path denied")
    if any(item==".." for item in candidate.parts):
        raise EncoderUnavailable("noncanonical asset path")
    return candidate


@dataclass(frozen=True,slots=True)
class EncoderSpec:
    model_path: str
    model_sha256: str
    tokenizer_path: str
    tokenizer_sha256: str
    output_name: str
    dimensions: int
    max_length: int
    pooling: str
    threads: int
    query_prefix: str
    document_prefix: str

    @classmethod
    def parse(cls,raw: Any) -> "EncoderSpec":
        keys={"model_path","model_sha256","tokenizer_path","tokenizer_sha256",
              "output_name","dimensions","max_length","pooling","threads",
              "query_prefix","document_prefix"}
        if type(raw) is not dict or set(raw)!=keys:
            raise EncoderUnavailable("invalid encoder specification fields")
        model=_path(raw["model_path"]);tokenizer=_path(raw["tokenizer_path"])
        output=raw["output_name"]
        if type(output) is not str or not _TOKEN_NAME.fullmatch(output):
            raise EncoderUnavailable("invalid selected ONNX output")
        if raw["pooling"] not in ("mean","cls","sentence"):
            raise EncoderUnavailable("unsupported encoder pooling")
        return cls(str(model),_sha(raw["model_sha256"]),str(tokenizer),
                   _sha(raw["tokenizer_sha256"]),output,
                   _int(raw["dimensions"],4,MAX_DIMENSION),
                   _int(raw["max_length"],8,MAX_LENGTH),raw["pooling"],
                   _int(raw["threads"],1,8),
                   _text(raw["query_prefix"],128,empty=True),
                   _text(raw["document_prefix"],128,empty=True))

    def as_dict(self,*,private=True):
        result={"model_sha256":self.model_sha256,"tokenizer_sha256":self.tokenizer_sha256,
                "output_name":self.output_name,"dimensions":self.dimensions,
                "max_length":self.max_length,"pooling":self.pooling,"threads":self.threads,
                "query_prefix":self.query_prefix,"document_prefix":self.document_prefix}
        if private:
            result.update({"model_path":self.model_path,"tokenizer_path":self.tokenizer_path})
        return result

    @property
    def identity(self):
        # File location is not model identity. Pooling, prefixing and token
        # cutoff are identity-bearing; threading affects the execution spec.
        return digest(stable({"schema":SCHEMA,**self.as_dict(private=False)}))


def _inspect_onnx(raw,onnx):
    """Reject external/nested/custom executable graph surfaces before ORT."""
    try:
        model=onnx.load_model_from_string(raw)
        if (not model.HasField("graph") or len(model.functions)
                or len(model.training_info) or len(model.graph.sparse_initializer)
                or not 1<=len(model.graph.node)<=MAX_GRAPH_NODES
                or len(model.graph.initializer)>MAX_INITIALIZERS
                or any(op.domain not in _DOMAINS for op in model.opset_import)):
            raise EncoderUnavailable("unsupported encoder graph surface")
        bytes_seen=0
        tensor_type=onnx.TensorProto
        attribute_type=onnx.AttributeProto
        def check_tensor(tensor):
            nonlocal bytes_seen
            if (tensor.data_location==tensor_type.EXTERNAL or len(tensor.external_data)
                    or tensor.data_type==tensor_type.STRING or tensor.HasField("segment")):
                raise EncoderUnavailable("external or unsupported encoder tensor storage")
            # Serialized repeated fields count toward the same input limit.
            bytes_seen+=tensor.ByteSize()
            if bytes_seen>MAX_TENSOR_BYTES:
                raise EncoderUnavailable("encoder tensor inventory exceeds budget")
        for tensor in model.graph.initializer:
            check_tensor(tensor)
        for node in model.graph.node:
            if node.domain not in _DOMAINS or node.op_type in _BLOCKED_OPS:
                raise EncoderUnavailable("unsupported or nonstandard encoder operator")
            for attribute in node.attribute:
                if attribute.type in (
                    attribute_type.GRAPH,attribute_type.GRAPHS,
                    attribute_type.SPARSE_TENSOR,attribute_type.SPARSE_TENSORS,
                    attribute_type.TYPE_PROTO,attribute_type.TYPE_PROTOS,
                ):
                    raise EncoderUnavailable("unsupported nested encoder graph attribute")
                if attribute.type==attribute_type.TENSOR:
                    check_tensor(attribute.t)
                elif attribute.type==attribute_type.TENSORS:
                    for tensor in attribute.tensors:
                        check_tensor(tensor)
        onnx.checker.check_model(model,full_check=False)
    except EncoderUnavailable:
        raise
    except Exception:
        raise EncoderUnavailable("ONNX graph validation failed") from None


class SentenceEncoder:
    """One immutable model/tokenizer configuration, with serialized batches."""

    def __init__(self,spec: EncoderSpec):
        self.spec=spec
        try:
            import numpy as np
            import onnx
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError:
            raise EncoderUnavailable("install approved local numpy/onnx/onnxruntime/tokenizers dependencies") from None
        self._np=np
        self._lock=threading.RLock()
        self._closed=False
        model,model_stamp=_read_pinned(Path(spec.model_path),spec.model_sha256,MAX_MODEL_BYTES)
        tok,tok_stamp=_read_pinned(Path(spec.tokenizer_path),spec.tokenizer_sha256,MAX_TOKENIZER_BYTES)
        _inspect_onnx(model,onnx)
        try:
            # from_str uses declarative tokenizer JSON, no model repo or
            # trust_remote_code mechanism. Explicit length and pad policy.
            self._tokenizer=Tokenizer.from_str(tok.decode("utf-8","strict"))
            vocab=self._tokenizer.get_vocab_size(with_added_tokens=True)
            if not 1<=vocab<=2_000_000:
                raise EncoderUnavailable("tokenizer vocabulary exceeds budget")
            options=ort.SessionOptions()
            options.intra_op_num_threads=spec.threads
            options.inter_op_num_threads=1
            options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            options.enable_mem_pattern=False
            options.enable_cpu_mem_arena=False
            options.log_severity_level=3
            self._session=ort.InferenceSession(model,sess_options=options,
                                               providers=["CPUExecutionProvider"])
            if self._session.get_providers()!=["CPUExecutionProvider"]:
                raise EncoderUnavailable("local CPU-only execution provider mismatch")
            inputs={row.name:row for row in self._session.get_inputs()}
            if not {"input_ids","attention_mask"}<=inputs.keys() or not inputs.keys()<=_INPUTS:
                raise EncoderUnavailable("unsupported encoder input contract")
            self._types={}
            fixed_length=None;fixed_batch=None
            for name,row in inputs.items():
                if row.type not in ("tensor(int64)","tensor(int32)") or len(row.shape)!=2:
                    raise EncoderUnavailable("unsupported encoder input shape")
                self._types[name]=np.int64 if row.type=="tensor(int64)" else np.int32
                batch,length=row.shape
                if isinstance(batch,int):
                    if not 1<=batch<=MAX_BATCH or (fixed_batch is not None and fixed_batch!=batch):
                        raise EncoderUnavailable("unsupported fixed batch")
                    fixed_batch=batch
                if isinstance(length,int):
                    if not 1<=length<=spec.max_length or (fixed_length is not None and fixed_length!=length):
                        raise EncoderUnavailable("unsupported fixed sequence")
                    fixed_length=length
            self._fixed_batch=fixed_batch
            self._length=fixed_length or spec.max_length
            output=next((o for o in self._session.get_outputs() if o.name==spec.output_name),None)
            if output is None or output.type not in ("tensor(float)","tensor(float16)","tensor(double)"):
                raise EncoderUnavailable("selected embedding output unavailable")
            rank=2 if spec.pooling=="sentence" else 3
            if len(output.shape)!=rank:
                raise EncoderUnavailable("encoder output rank and pooling differ")
            if isinstance(output.shape[-1],int) and output.shape[-1]!=spec.dimensions:
                raise EncoderUnavailable("encoder declares different output dimension")
            # Exported models use the configured tokenizer's pad token; do
            # not silently choose an arbitrary model-specific token.
            pad=self._tokenizer.padding
            pad_id=None
            if isinstance(pad,dict) and type(pad.get("pad_id")) is int:
                pad_id=pad["pad_id"]
            if pad_id is None:
                for symbol in ("[PAD]","<pad>"):
                    found=self._tokenizer.token_to_id(symbol)
                    if found is not None:
                        pad_id=found;break
            if type(pad_id) is not int or not 0<=pad_id<vocab:
                raise EncoderUnavailable("encoder tokenizer requires an explicit recognized pad token")
            self._pad_id=pad_id
            self._vocab=vocab
            self._tokenizer.no_padding()
            self._tokenizer.enable_truncation(max_length=self._length,stride=0,
                                               strategy="longest_first")
            self._model_stamp=model_stamp;self._tokenizer_stamp=tok_stamp
        except EncoderUnavailable:
            raise
        except Exception:
            raise EncoderUnavailable("local sentence encoder initialization failed") from None

    def assert_stable(self):
        if self._closed:
            raise EncoderUnavailable("sentence encoder closed")
        try:
            for path,stamp in ((self.spec.model_path,self._model_stamp),
                               (self.spec.tokenizer_path,self._tokenizer_stamp)):
                current=Path(path).lstat()
                if not stat.S_ISREG(current.st_mode) or _identity(current)!=stamp:
                    raise EncoderUnavailable("sentence encoder file identity changed")
        except OSError:
            raise EncoderUnavailable("sentence encoder custody unavailable") from None

    def close(self):
        with self._lock:
            self._closed=True
            self._session=None
            self._tokenizer=None

    def encode(self,texts: list[str],*,query: bool) -> list[tuple[float,...]]:
        if type(query) is not bool or type(texts) is not list or not 1<=len(texts)<=MAX_BATCH:
            raise EncoderUnavailable("sentence encoder batch exceeds bound")
        prefix=self.spec.query_prefix if query else self.spec.document_prefix
        canonical=[prefix+_text(t,MAX_INPUT_BYTES) for t in texts]
        with self._lock:
            self.assert_stable()
            # Fixed batch models may require individual runs or a padded
            # final batch. Dummy rows are never returned to the caller.
            cap=self._fixed_batch or MAX_BATCH
            result=[]
            for start in range(0,len(canonical),cap):
                current=canonical[start:start+cap]
                count=len(current)
                if self._fixed_batch is not None:
                    current=current+[current[-1]]*(self._fixed_batch-count)
                result.extend(self._encode_batch(current)[:count])
            self.assert_stable()
            return result

    def _encode_batch(self,texts):
        np=self._np
        try:
            encodings=self._tokenizer.encode_batch(texts,add_special_tokens=True)
            if len(encodings)!=len(texts):
                raise EncoderUnavailable("tokenizer batch shape mismatch")
            ids=[];mask=[];types=[]
            for row in encodings:
                tokens=list(row.ids)
                token_types=list(row.type_ids)
                if (not 1<=len(tokens)<=self._length or len(token_types)!=len(tokens)
                        or any(type(t) is not int or not 0<=t<self._vocab for t in tokens)
                        or any(type(t) is not int or not 0<=t<=2**31-1 for t in token_types)):
                    raise EncoderUnavailable("invalid bounded encoder tokens")
                padding=self._length-len(tokens)
                ids.append(tokens+[self._pad_id]*padding)
                mask.append([1]*len(tokens)+[0]*padding)
                types.append(token_types+[0]*padding)
            values={"input_ids":ids,"attention_mask":mask,"token_type_ids":types}
            feeds={name:np.asarray(values[name],dtype=kind) for name,kind in self._types.items()}
            raw=self._session.run([self.spec.output_name],feeds)
            if not isinstance(raw,list) or len(raw)!=1:
                raise EncoderUnavailable("invalid selected encoder output")
            arr=np.asarray(raw[0],dtype=np.float64)
            expected=((len(texts),self.spec.dimensions) if self.spec.pooling=="sentence"
                      else (len(texts),self._length,self.spec.dimensions))
            if arr.shape!=expected or not np.isfinite(arr).all():
                raise EncoderUnavailable("invalid finite sentence embedding output")
            if self.spec.pooling=="mean":
                weights=np.asarray(mask,dtype=np.float64)
                arr=(arr*weights[:,:,None]).sum(axis=1)/weights.sum(axis=1)[:,None]
            elif self.spec.pooling=="cls":
                arr=arr[:,0,:]
            length=np.linalg.norm(arr,axis=1)
            if not np.isfinite(length).all() or (length<=1e-20).any():
                raise EncoderUnavailable("empty or nonfinite sentence embedding")
            arr=arr/length[:,None]
            return [tuple(float(x) for x in row) for row in arr]
        except EncoderUnavailable:
            raise
        except Exception:
            raise EncoderUnavailable("local transformer encoder batch failed") from None

    def qualification(self):
        """Execute a minimal real artifact smoke; not a benchmark or safety proof."""
        samples=["local encoder integrity probe","a second independent sentence"]
        observed=self.encode(samples,query=False)
        queries=self.encode([samples[0]],query=True)
        if len(observed)!=2 or len(queries)!=1:
            raise EncoderUnavailable("encoder probe batch mismatch")
        distance=math.fsum(a*b for a,b in zip(observed[0],observed[1]))
        if not math.isfinite(distance) or distance>0.9999999:
            raise EncoderUnavailable("encoder probe returned indistinguishable document vectors")
        return {"encoder_identity":self.spec.identity,"document_vectors":len(observed),
                "query_vectors":len(queries),"dimensions":self.spec.dimensions,
                "query_path_executed":True,"document_path_executed":True,
                "input_truncation_enabled":True,"independent_quality_certified":False}
