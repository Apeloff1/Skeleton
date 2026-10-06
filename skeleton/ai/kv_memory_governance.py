"""Atomic admission binding KV cache leases to GPU memory reservations."""
from dataclasses import dataclass
import hashlib,json
from skeleton.runtime.gpu_memory import GPUMemoryPool
from skeleton.kv.cache_service import KVCacheEntry,KVCacheKey,KVCacheLease,reuse
@dataclass(frozen=True)
class KVMemoryAdmission:
 allocation_id:str; reservation_id:str; key_digest:str
def admit_kv_memory(pool:GPUMemoryPool,entry:KVCacheEntry,key:KVCacheKey,lease:KVCacheLease,*,holder:str,now:int,size:int):
 reuse(entry,key,now,lease,holder)
 if entry.allocation_id in {r.reservation_id for r in pool.reservations}: raise PermissionError("allocation identity already reserved")
 updated,reservation=pool.reserve(entry.allocation_id,size)
 body={"tenant":key.tenant,"session":key.session,"model":key.model,"config":key.config,"prefix":key.prefix_digest,"scope":key.privacy_scope}
 return updated,KVMemoryAdmission(entry.allocation_id,reservation.reservation_id,hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest())
