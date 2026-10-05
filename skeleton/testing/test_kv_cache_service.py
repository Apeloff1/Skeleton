import pytest
from skeleton.kv.cache_service import *
def k(t="a"):return KVCacheKey(t,"s","m","c","p")
def test_cross_tenant_or_model_reuse_rejected():
 e=KVCacheEntry(k(),"alloc");l=KVCacheLease(e,"h",10)
 with pytest.raises(PermissionError):reuse(e,k("b"),1,l)
def test_expired_lease_rejected():
 e=KVCacheEntry(k(),"a")
 with pytest.raises(PermissionError):reuse(e,k(),11,KVCacheLease(e,"h",10))
