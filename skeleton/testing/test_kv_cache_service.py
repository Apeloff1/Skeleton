import pytest
from skeleton.kv.cache_service import *
def k(t="a",scope="private"):return KVCacheKey(t,"s","m","c","p",scope)
def test_cross_tenant_or_model_reuse_rejected():
 e=KVCacheEntry(k(),"alloc");l=KVCacheLease(e,"h",0,10)
 with pytest.raises(PermissionError):reuse(e,k("b"),1,l,"h")
def test_expired_and_future_lease_rejected():
 e=KVCacheEntry(k(),"a")
 with pytest.raises(PermissionError):reuse(e,k(),10,KVCacheLease(e,"h",0,10),"h")
 with pytest.raises(PermissionError):reuse(e,k(),0,KVCacheLease(e,"h",1,10),"h")
def test_wrong_holder_and_privacy_scope_rejected():
 e=KVCacheEntry(k(),"a");l=KVCacheLease(e,"h",0,10)
 with pytest.raises(PermissionError):reuse(e,k(),1,l,"other")
 with pytest.raises(PermissionError):reuse(e,k(scope="shared"),1,l,"h")
