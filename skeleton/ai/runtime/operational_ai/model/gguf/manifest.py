"""Strict signed-off operator inventory for one complete GGUF model artifact."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
import json
import re
import hashlib

SHA = re.compile(r"^[0-9a-f]{64}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_SHARD = 99_000_000
MAX_MODEL = 1_940_000_000
MAX_SHARDS = 64

class GGUFManifestError(ValueError):
    pass


def _uint(x: object, name: str, minimum: int, maximum: int) -> int:
    if type(x) is not int or not minimum <= x <= maximum:
        raise GGUFManifestError(f"{name} outside permitted integer range")
    return x


def _sha(x: object, name: str) -> str:
    if not isinstance(x, str) or not SHA.fullmatch(x):
        raise GGUFManifestError(f"invalid {name} sha256")
    return x


def _path(x: object) -> str:
    if not isinstance(x, str) or not x or len(x)>512 or '\\' in x or '\x00' in x:
        raise GGUFManifestError("noncanonical shard path")
    p=PurePosixPath(x)
    if p.is_absolute() or str(p)!=x or any(part in ('', '.', '..') for part in x.split('/')):
        raise GGUFManifestError("shard path traversal")
    if any(ord(c)<33 or ord(c)>126 for c in x):
        raise GGUFManifestError("shard path contains unsafe characters")
    return x


@dataclass(frozen=True, slots=True)
class Shard:
    path: str
    bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _path(self.path)
        _uint(self.bytes, "shard bytes", 1, MAX_SHARD)
        _sha(self.sha256, "shard")


@dataclass(frozen=True, slots=True)
class GGUFModelManifest:
    model_id: str
    shards: tuple[Shard, ...]
    model_sha256: str
    total_bytes: int
    license: str
    source: str
    rights_approved: bool
    context_ceiling: int
    gpu_layers_ceiling: int
    minimum_memory_bytes: int
    architecture: str = "gguf"

    def __post_init__(self) -> None:
        if not NAME.fullmatch(self.model_id):
            raise GGUFManifestError("invalid model identifier")
        if not self.shards or len(self.shards)>MAX_SHARDS:
            raise GGUFManifestError("model must have 1-64 real shard members")
        if len(set(s.path for s in self.shards)) != len(self.shards):
            raise GGUFManifestError("shard members must be unique")
        _sha(self.model_sha256, "complete model")
        _uint(self.total_bytes, "complete model bytes", 1, MAX_MODEL)
        if sum(s.bytes for s in self.shards)!=self.total_bytes:
            raise GGUFManifestError("model size does not match declared shard sum")
        if type(self.rights_approved) is not bool or not self.rights_approved:
            raise GGUFManifestError("model requires explicit independently approved rights")
        for name in ("license", "source"):
            v=getattr(self,name)
            if not isinstance(v,str) or not 1<=len(v)<=512 or not v.strip():
                raise GGUFManifestError(f"missing verified {name}")
        _uint(self.context_ceiling,"context ceiling",128,131072)
        _uint(self.gpu_layers_ceiling,"gpu layer ceiling",0,256)
        _uint(self.minimum_memory_bytes,"memory floor",1,8_000_000_000)
        if self.architecture!="gguf":
            raise GGUFManifestError("only GGUF local model format supported")

    @property
    def manifest_digest(self)->str:
        raw=json.dumps(self.to_record(),sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_record(self)->dict[str,Any]:
        return {"schema_version":1,"model_id":self.model_id,"shards":[{"path":s.path,"bytes":s.bytes,"sha256":s.sha256} for s in self.shards],
                "model_sha256":self.model_sha256,"total_bytes":self.total_bytes,"license":self.license,
                "source":self.source,"rights_approved":self.rights_approved,
                "context_ceiling":self.context_ceiling,"gpu_layers_ceiling":self.gpu_layers_ceiling,
                "minimum_memory_bytes":self.minimum_memory_bytes,"architecture":self.architecture}


def _reject_duplicate_pairs(pairs:list[tuple[str,Any]])->dict[str,Any]:
    d:dict[str,Any]={}
    for k,v in pairs:
        if k in d:raise GGUFManifestError(f"duplicate manifest key: {k}")
        d[k]=v
    return d


def load_manifest(raw: bytes)->GGUFModelManifest:
    if not isinstance(raw,bytes) or not 0<len(raw)<=128_000:
        raise GGUFManifestError("manifest bytes invalid")
    try:
        j=json.loads(raw.decode('utf-8'),object_pairs_hook=_reject_duplicate_pairs,
                     parse_constant=lambda _:(_ for _ in ()).throw(GGUFManifestError("nonfinite manifest number")))
    except (UnicodeError,ValueError) as exc:
        raise GGUFManifestError(f"unreadable model manifest: {exc}") from exc
    if not isinstance(j,dict) or j.get('schema_version')!=1:
        raise GGUFManifestError("unsupported manifest schema")
    expected={"schema_version","model_id","shards","model_sha256","total_bytes","license","source", "rights_approved","context_ceiling","gpu_layers_ceiling","minimum_memory_bytes","architecture"}
    if set(j)!=expected:
        raise GGUFManifestError("unknown or omitted manifest fields")
    if not isinstance(j['shards'],list):
        raise GGUFManifestError("shards must be a list")
    shards=[]
    for item in j['shards']:
        if not isinstance(item,dict) or set(item)!={"path","bytes","sha256"}:
            raise GGUFManifestError("malformed shard member")
        shards.append(Shard(**item))
    return GGUFModelManifest(shards=tuple(shards),**{k:v for k,v in j.items() if k not in ('shards','schema_version')})
