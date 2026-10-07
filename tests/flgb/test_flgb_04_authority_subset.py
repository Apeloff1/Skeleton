import unittest
from skeleton.ai.agents.authority_subset import AgentContractError, AuthorityGrant
class TestAuthoritySubset(unittest.TestCase):
    def test_child_cannot_widen_parent(self):
        root=AuthorityGrant("supervisor",("read","write"))
        child=root.delegate("worker",("read",))
        self.assertEqual(child.parent_digest,root.digest)
        with self.assertRaises(AgentContractError):
            root.delegate("worker",("read","admin"))
if __name__=="__main__": unittest.main()
