import unittest
from skeleton.ai.agents.idempotent_writes import AgentContractError, IdempotentWriteLedger
D="a"*64
E="b"*64
F="c"*64
class TestIdempotentWrites(unittest.TestCase):
    def test_key_binds_input_and_result(self):
        ledger=IdempotentWriteLedger().commit("k",D,E)
        self.assertEqual(ledger.admit("k",D).result_digest,E)
        self.assertIs(ledger.commit("k",D,E),ledger)
        with self.assertRaises(AgentContractError): ledger.admit("k",F)
        with self.assertRaises(AgentContractError): ledger.commit("k",D,F)
if __name__=="__main__": unittest.main()
