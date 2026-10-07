import unittest
from skeleton.ai.context.project_memory import ContextContractError, ProjectMemorySnapshot
D="a"*64
E="b"*64
class TestProjectMemory(unittest.TestCase):
    def test_parent_binding(self):
        genesis=ProjectMemorySnapshot("p",0,D,D,E)
        child=ProjectMemorySnapshot("p",1,E,D,E,genesis.digest)
        self.assertEqual(child.parent_digest,genesis.digest)
        with self.assertRaises(ContextContractError): ProjectMemorySnapshot("p",1,E,D,E)
if __name__=="__main__": unittest.main()
