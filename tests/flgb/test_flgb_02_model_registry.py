import unittest
from skeleton.ai.model_runtime.model_registry import ModelIdentity, ModelRegistry, ModelRuntimeError
D="a"*64
E="b"*64
class TestRegistry(unittest.TestCase):
    def test_revision_is_immutable(self):
        m=ModelIdentity("m","r1","arch",D,D,D)
        reg=ModelRegistry().register(m)
        self.assertEqual(reg.resolve("m","r1"),m)
        with self.assertRaises(ModelRuntimeError): reg.register(ModelIdentity("m","r1","arch",E,D,D))
if __name__=="__main__": unittest.main()
