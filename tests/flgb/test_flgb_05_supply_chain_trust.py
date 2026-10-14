import unittest
from skeleton.security.supply_chain_trust import SupplyChainArtifact, verify_supply_chain
D="a"*64

class TestSupplyChain(unittest.TestCase):
    def test_signature_and_provenance_are_non_compensable(self):
        complete=SupplyChainArtifact("a",D,"registry","signer",D)
        unsigned=SupplyChainArtifact("b",D,"registry",None,D)
        unprovenanced=SupplyChainArtifact("c",D,"registry","signer",None)
        self.assertTrue(verify_supply_chain(complete))
        self.assertFalse(verify_supply_chain(unsigned))
        self.assertFalse(verify_supply_chain(unprovenanced))

if __name__=="__main__": unittest.main()
