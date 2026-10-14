import unittest
from skeleton.ai.assurance.benchmark_registry import AssuranceContractError, BenchmarkRegistry, BenchmarkSpec
D="a"*64
E="b"*64

class TestBenchmarkRegistry(unittest.TestCase):
    def test_version_identity_is_immutable(self):
        item=BenchmarkSpec("bench","v1",D,True,E)
        reg=BenchmarkRegistry().register(item)
        self.assertEqual(reg.resolve("bench","v1"),item)
        with self.assertRaises(AssuranceContractError):
            reg.register(BenchmarkSpec("bench","v1",E,True,E))

if __name__=="__main__": unittest.main()
