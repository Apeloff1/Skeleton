import unittest
from skeleton.ai.model_runtime.kv_cache import KVCacheEntry, plan_kv_admission
class TestKV(unittest.TestCase):
    def test_lru_eviction_respects_pins(self):
        entries=(KVCacheEntry("old",40,1),KVCacheEntry("pin",40,2,True))
        evicted, admitted=plan_kv_admission(entries,KVCacheEntry("new",40,3),capacity_bytes=100)
        self.assertEqual(evicted,("old",))
        self.assertTrue(admitted)
if __name__=="__main__": unittest.main()
