import unittest
from skeleton.ai.context.working_memory import ContextContractError, WorkingMemory
D="a"*64
E="b"*64
class TestWorkingMemory(unittest.TestCase):
    def test_revisions_are_immutable(self):
        base=WorkingMemory()
        one=base.upsert("k",D,E)
        two=one.upsert("k",E,D)
        self.assertEqual((base.revision,one.revision,two.revision),(0,1,2))
        with self.assertRaises(ContextContractError): two.remove("missing")
if __name__=="__main__": unittest.main()
