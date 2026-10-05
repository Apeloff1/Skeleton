from dataclasses import dataclass
@dataclass(frozen=True)
class KVCacheKey: tenant:str; session:str; model:str; config:str; prefix_digest:str
@dataclass(frozen=True)
class KVCacheEntry: key:KVCacheKey; allocation_id:str
@dataclass(frozen=True)
class KVCacheLease: entry:KVCacheEntry; holder:str; expires_at:int
def reuse(entry,key,now,lease):
 if entry.key!=key:raise PermissionError("incompatible KV cache boundary")
 if lease.entry!=entry or now>lease.expires_at:raise PermissionError("invalid KV cache lease")
 return entry
