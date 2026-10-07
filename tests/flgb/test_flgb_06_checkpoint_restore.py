import unittest
from skeleton.ai.assurance.checkpoint_restore import AssuranceContractError, RestoreReceipt
D="a"*64
E="b"*64

class TestCheckpointRestore(unittest.TestCase):
    def test_restore_digest_mismatch_fails_closed(self):
        receipt=RestoreReceipt(D,E,E,7,D)
        self.assertEqual(len(receipt.digest),64)
        with self.assertRaises(AssuranceContractError): RestoreReceipt(D,D,E,7,D)

if __name__=="__main__": unittest.main()
