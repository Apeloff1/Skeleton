"""Local learned contextual token embeddings, without model download or remote code.

An explicit operator provisions a self-contained ONNX encoder and a tokenizer
JSON. Both exact file bytes are pinned. This uses token-level hidden states,
not hashing, word counts or a generator's unsupported semantic claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import stat
import threading


def _digest(obj):
    return sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()).hexdigest()


def _pin(value):
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)


def _read_pinned(path, expected, limit):
    if not _pin(expected):
        raise ValueError("explicit SHA-256 artifact pin required")
    path=Path(path)
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size<1 or before.st_size>limit:
        raise ValueError("local embedding artifact outside file bounds")
    if path.resolve(strict=True)!=Path(os.path.abspath(path)):
        raise PermissionError("symlinked embedding artifact ancestry denied")
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
    with os.fdopen(fd,"rb") as handle:
        first=os.fstat(handle.fileno())
        ident=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if not stat.S_ISREG(first.st_mode) or ident(first)!=ident(before):
            raise OSError("embedding artifact replaced")
        raw=handle.read(limit+1)
        if len(raw)!=first.st_size or ident(os.fstat(handle.fileno()))!=ident(first) or ident(path.lstat())!=ident(first):
            raise OSError("embedding artifact changed during admission")
        if sha256(raw).hexdigest()!=expected:
            raise ValueError("embedding artifact digest mismatch")
        return raw


@dataclass(frozen=True,slots=True)
class EncoderPolicy:
    dimension:int
    max_tokens:int=2048
    max_input_bytes:int=131072
    max_hidden_bytes:int=64*1024**2
    threads:int=2
    query_prefix:str=""
    document_prefix:str=""
    output_name:str="last_hidden_state"

    def __post_init__(self):
        for v,lo,hi in ((self.dimension,2,4096),(self.max_tokens,8,32768),
                         (self.max_input_bytes,64,1024**2),(self.max_hidden_bytes,1024,1024**3),(self.threads,1,32)):
            if type(v) is not int or not lo<=v<=hi:
                raise ValueError("invalid semantic encoder resource policy")
        if self.max_tokens*self.dimension*4>self.max_hidden_bytes:
            raise ValueError("encoder token/dimension envelope exceeds hidden output budget")
        for field in (self.query_prefix,self.document_prefix):
            if not isinstance(field,str) or len(field.encode())>1024:
                raise ValueError("bounded operator embedding prefix required")
        if not isinstance(self.output_name,str) or not 1<=len(self.output_name)<=128:
            raise ValueError("explicit token output name required")


def _validate_graph(raw):
    import onnx
    model=onnx.load_model_from_string(raw)
    # Reject external tensor files, training graphs, local custom functions,
    # nested graph execution and custom operator libraries. Ordinary ONNX
    # transformer exports use the standard ai.onnx domain.
    if model.functions or model.training_info:
        raise ValueError("embedding graph contains executable extensions")
    if any(x.domain not in {"","ai.onnx"} for x in model.opset_import):
        raise ValueError("embedding graph uses nonstandard operator domain")
    def tensor(t):
        if t.data_location==onnx.TensorProto.EXTERNAL or t.external_data:
            raise ValueError("external tensor data is not admitted")
    for t in model.graph.initializer:
        tensor(t)
    if model.graph.sparse_initializer:
        raise ValueError("sparse initializer not admitted")
    if len(model.graph.node)>100000:
        raise ValueError("embedding graph exceeds node ceiling")
    for node in model.graph.node:
        if node.domain not in {"","ai.onnx"}:
            raise ValueError("custom embedding operator denied")
        for attribute in node.attribute:
            if attribute.type in {onnx.AttributeProto.GRAPH,onnx.AttributeProto.GRAPHS,
                                  onnx.AttributeProto.SPARSE_TENSOR,onnx.AttributeProto.SPARSE_TENSORS}:
                raise ValueError("nested graph or sparse tensor not admitted")
            if attribute.type==onnx.AttributeProto.TENSOR:
                tensor(attribute.t)
            if attribute.type==onnx.AttributeProto.TENSORS:
                for t in attribute.tensors:
                    tensor(t)
    onnx.checker.check_model(model)


def _unit(matrix):
    import numpy as np
    values=np.asarray(matrix,dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite learned embedding")
    norms=np.linalg.norm(values,axis=-1,keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms<=1e-12):
        raise ValueError("degenerate learned embedding")
    return values/norms


@dataclass(frozen=True)
class SpanEmbedding:
    dense:tuple[float,...]
    segments:tuple[tuple[float,...],...]

    def as_record(self):
        return {"dense":list(self.dense),"segments":[list(x) for x in self.segments]}


class LocalContextEncoder:
    """Pinned CPU ONNX token encoder. Trusted native library; not an OS sandbox."""
    def __init__(self,model_path:Path,model_sha256:str,tokenizer_path:Path,tokenizer_sha256:str,
                 policy:EncoderPolicy,*,max_model_bytes:int=512*1024**2):
        if not isinstance(policy,EncoderPolicy) or type(max_model_bytes) is not int or not 1<=max_model_bytes<=1024**3:
            raise ValueError("explicit local encoder policy and artifact ceiling required")
        import onnxruntime as ort
        from tokenizers import Tokenizer
        import numpy as np
        raw=_read_pinned(model_path,model_sha256,max_model_bytes)
        tokenizer_raw=_read_pinned(tokenizer_path,tokenizer_sha256,32*1024**2)
        _validate_graph(raw)
        tokenizer=Tokenizer.from_str(tokenizer_raw.decode("utf-8"))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        options=ort.SessionOptions()
        options.intra_op_num_threads=policy.threads
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern=False
        # No custom op library, no provider options passed from user data.
        session=ort.InferenceSession(raw,sess_options=options,providers=["CPUExecutionProvider"])
        allowed={"input_ids","attention_mask","token_type_ids"}
        inputs={x.name:x for x in session.get_inputs()}
        if "input_ids" not in inputs or set(inputs)-allowed or any(x.type!="tensor(int64)" or len(x.shape)!=2 for x in inputs.values()):
            raise ValueError("unsupported encoder input tensor contract")
        outputs={x.name:x for x in session.get_outputs()}
        output=outputs.get(policy.output_name)
        if output is None or output.type not in {"tensor(float)","tensor(float16)"} or len(output.shape)!=3:
            raise ValueError("encoder must expose token-level rank-three hidden states")
        if isinstance(output.shape[-1],int) and output.shape[-1]!=policy.dimension:
            raise ValueError("embedding dimension mismatch")
        if session.get_providers()!=["CPUExecutionProvider"]:
            raise RuntimeError("local encoder provider drift")
        self._session,self._tokenizer,self._inputs=session,tokenizer,tuple(inputs)
        self._policy=policy
        self._identity=_digest({"schema":"skeleton.learned-context-encoder.v1","model":model_sha256,
            "tokenizer":tokenizer_sha256,"policy":asdict(policy),"runtime":ort.__version__,
            "numpy":np.__version__,"provider":"CPUExecutionProvider"})
        self._lock=threading.RLock()

    @property
    def identity(self): return self._identity
    @property
    def policy(self): return self._policy

    def _encode(self,text,prefix):
        import numpy as np
        if not isinstance(text,str) or not text.strip() or len((prefix+text).encode())>self.policy.max_input_bytes:
            raise ValueError("local embedding input outside byte budget")
        with self._lock:
            entered=self._tokenizer.encode(prefix+text,add_special_tokens=True)
            n=len(entered.ids)
            if not 1<=n<=self.policy.max_tokens:
                raise ValueError("local embedding context token limit exceeded")
            values={"input_ids":entered.ids,"attention_mask":entered.attention_mask,
                    "token_type_ids":entered.type_ids}
            feed={k:np.asarray([values[k]],dtype=np.int64) for k in self._inputs}
            result=self._session.run([self.policy.output_name],feed)[0]
        if result.shape!=(1,n,self.policy.dimension) or result.nbytes>self.policy.max_hidden_bytes or not np.isfinite(result).all():
            raise ValueError("invalid native embedding hidden state")
        offsets=[]
        selected=[]
        for i,((start,end),special) in enumerate(zip(entered.offsets,entered.special_tokens_mask)):
            if not special and start>=len(prefix) and end>start and end<=len(prefix)+len(text):
                offsets.append((start-len(prefix),end-len(prefix)))
                selected.append(i)
        if not selected:
            raise ValueError("embedding text has no representable non-special tokens")
        return result[0,selected].astype(np.float32,copy=False),offsets

    @staticmethod
    def _pool(hidden,indices,segments):
        import numpy as np
        values=hidden[indices]
        dense=_unit(values.mean(axis=0))
        # Fine-grained segment vectors retain several local facets instead
        # of a single topic centroid. This is segment MaxSim, not ColBERT weights.
        parts=[_unit(group.mean(axis=0)) for group in np.array_split(values,min(segments,len(values)))]
        return SpanEmbedding(tuple(map(float,dense)),tuple(tuple(map(float,p)) for p in parts))

    def query(self,text,*,segments=16):
        if type(segments) is not int or not 1<=segments<=32:
            raise ValueError("query segment count outside bounds")
        hidden,offsets=self._encode(text,self.policy.query_prefix)
        return self._pool(hidden,list(range(len(offsets))),segments)

    def spans(self,text,spans,*,segments=8):
        if type(segments) is not int or not 1<=segments<=32 or not 1<=len(spans)<=256:
            raise ValueError("contextual pooling span budget exceeded")
        if any(type(start) is not int or type(end) is not int or not 0<=start<end<=len(text) for start,end in spans):
            raise ValueError("invalid source span offsets")
        hidden,offsets=self._encode(text,self.policy.document_prefix)
        pooled=[]
        for start,end in spans:
            indices=[i for i,(left,right) in enumerate(offsets) if left<end and right>start]
            if not indices:
                raise ValueError("source span has no contextual token representations")
            pooled.append(self._pool(hidden,indices,segments))
        return tuple(pooled)

@dataclass(frozen=True,slots=True)
class PairRerankerPolicy:
    max_tokens:int=512
    max_input_bytes:int=32768
    max_pairs:int=16
    output_name:str="logits"
    positive_index:int=0
    threads:int=2

    def __post_init__(self):
        for v,lo,hi in ((self.max_tokens,8,8192),(self.max_input_bytes,64,262144),
                        (self.max_pairs,1,32),(self.positive_index,0,1),(self.threads,1,32)):
            if type(v) is not int or not lo<=v<=hi:
                raise ValueError("invalid local pair reranker bounds")
        if not isinstance(self.output_name,str) or not 1<=len(self.output_name)<=128:
            raise ValueError("explicit pair output required")


class LocalPairReranker:
    """Pinned local ONNX cross-encoder; independent query/passage pair logits."""
    def __init__(self,model_path,model_sha256,tokenizer_path,tokenizer_sha256,
                 policy:PairRerankerPolicy,*,max_model_bytes=512*1024**2):
        if not isinstance(policy,PairRerankerPolicy) or type(max_model_bytes) is not int or not 1<=max_model_bytes<=1024**3:
            raise ValueError("bounded local pair model policy required")
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        raw=_read_pinned(model_path,model_sha256,max_model_bytes)
        tokenizer_raw=_read_pinned(tokenizer_path,tokenizer_sha256,32*1024**2)
        _validate_graph(raw)
        tokenizer=Tokenizer.from_str(tokenizer_raw.decode("utf-8"))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        options=ort.SessionOptions()
        options.intra_op_num_threads=policy.threads
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern=False
        session=ort.InferenceSession(raw,sess_options=options,providers=["CPUExecutionProvider"])
        allowed={"input_ids","attention_mask","token_type_ids"}
        inputs={x.name:x for x in session.get_inputs()}
        if "input_ids" not in inputs or set(inputs)-allowed or any(x.type!="tensor(int64)" or len(x.shape)!=2 for x in inputs.values()):
            raise ValueError("invalid reranker native inputs")
        output={x.name:x for x in session.get_outputs()}.get(policy.output_name)
        if output is None or output.type not in {"tensor(float)","tensor(float16)"} or len(output.shape)!=2:
            raise ValueError("reranker must expose rank-two classification logits")
        if isinstance(output.shape[-1],int) and (output.shape[-1] not in {1,2} or policy.positive_index>=output.shape[-1]):
            raise ValueError("invalid reranker classification output geometry")
        if session.get_providers()!=["CPUExecutionProvider"]:
            raise RuntimeError("local pair model provider drift")
        self._session,self._tokenizer,self._inputs=session,tokenizer,tuple(inputs)
        self._policy=policy
        self._lock=threading.RLock()
        self._identity=_digest({"schema":"skeleton.local.pair-reranker.v1","model":model_sha256,
            "tokenizer":tokenizer_sha256,"policy":asdict(policy),"runtime":ort.__version__,
            "numpy":np.__version__,"provider":"CPUExecutionProvider"})

    @property
    def identity(self):return self._identity
    @property
    def policy(self):return self._policy

    def score(self,query,passages):
        import numpy as np
        if not isinstance(query,str) or not query.strip() or not isinstance(passages,(list,tuple)) or not 1<=len(passages)<=self.policy.max_pairs:
            raise ValueError("bounded explicit query/passage rerank batch required")
        results=[]
        with self._lock:
            for text in passages:
                if not isinstance(text,str) or not text.strip() or len(query.encode())+len(text.encode())>self.policy.max_input_bytes:
                    raise ValueError("pair text exceeds reranker input budget")
                encoded=self._tokenizer.encode(query,pair=text,add_special_tokens=True)
                if not 1<=len(encoded.ids)<=self.policy.max_tokens:
                    raise ValueError("pair token context limit exceeded")
                sequence_ids=encoded.sequence_ids
                # A broken tokenizer postprocessor must not silently discard
                # either side while claiming joint-context scoring.
                if 0 not in sequence_ids or 1 not in sequence_ids:
                    raise ValueError("reranker tokenizer did not preserve both sequences")
                payload={"input_ids":encoded.ids,"attention_mask":encoded.attention_mask,
                         "token_type_ids":encoded.type_ids}
                output=self._session.run([self.policy.output_name],{k:np.asarray([payload[k]],dtype=np.int64) for k in self._inputs})[0]
                if output.shape not in {(1,1),(1,2)} or self.policy.positive_index>=output.shape[1] or not np.isfinite(output).all():
                    raise ValueError("invalid native cross-encoder score")
                score=float(output[0,self.policy.positive_index])
                if output.shape[1]==2:
                    score-=float(output[0,1-self.policy.positive_index])
                # Stable monotone transform; not a calibrated probability.
                score=max(-60.0,min(60.0,score))
                results.append(1/(1+math.exp(-score)))
        return tuple(results)
