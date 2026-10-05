from dataclasses import dataclass
@dataclass(frozen=True)
class KVCacheKey: tenant:str; session:str; model:str; config:str; prefix_digest:str; privacy_scope:str="private"
@dataclass(frozen=True)
class KVCacheEntry: key:KVCacheKey; allocation_id:str
@dataclass(frozen=True)
class KVCacheLease: entry:KVCacheEntry; holder:str; issued_at:int; expires_at:int
def reuse(entry,key,now,lease,holder=None):
 if entry.key!=key:raise PermissionError("incompatible KV cache boundary")
 if not all((key.tenant,key.session,key.model,key.config,key.prefix_digest,key.privacy_scope,entry.allocation_id)):raise ValueError("complete KV cache identity required")
 if lease.entry!=entry or not lease.holder or (holder is not None and holder!=lease.holder):raise PermissionError("invalid KV cache lease holder")
 if lease.expires_at<=lease.issued_at or now<lease.issued_at or now>=lease.expires_at:raise PermissionError("invalid KV cache lease time")
 return entry
