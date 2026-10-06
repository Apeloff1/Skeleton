import pytest
from skeleton.runtime.gpu_memory import GPUMemoryPool
from skeleton.kv.cache_service import KVCacheKey,KVCacheEntry,KVCacheLease
from skeleton.ai.kv_memory_governance import admit_kv_memory
def fixture():
 k=KVCacheKey("t","s","m","c","p");e=KVCacheEntry(k,"alloc");return k,e,KVCacheLease(e,"worker",1,10)
def test_kv_lease_reserves_gpu_memory_atomically():
 k,e,l=fixture();p,a=admit_kv_memory(GPUMemoryPool(100),e,k,l,holder="worker",now=2,size=20);assert p.reservations[0].reservation_id=="alloc" and len(a.key_digest)==64
def test_wrong_holder_fails_before_allocation():
 k,e,l=fixture()
 with pytest.raises(PermissionError):admit_kv_memory(GPUMemoryPool(100),e,k,l,holder="other",now=2,size=20)
