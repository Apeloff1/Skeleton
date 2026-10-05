from skeleton.kv.prefix_cache import *
def k(scope="p"):return PrefixCacheKey("i","q","m","tok","v1",scope)
def test_instruction_or_scope_drift_blocks_reuse():
 a=PrefixArtifact(k(),True);assert not can_reuse(a,PrefixCacheKey("other","q","m","tok","v1","p"),{"p"}).reusable
 assert not can_reuse(a,k(),set()).reusable
