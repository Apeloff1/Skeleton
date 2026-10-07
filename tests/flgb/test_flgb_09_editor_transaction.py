import unittest
from skeleton.game.editor_transaction import CreatorContractError, EditorOperation, EditorTransaction
D="a"*64
E="b"*64
class TestEditorTransaction(unittest.TestCase):
    def test_transaction_binds_ordered_operations(self):
        op=EditorOperation("op","entity",D,E,True)
        tx=EditorTransaction("tx",D,(op,),"author")
        self.assertEqual(len(tx.digest),64)
        self.assertNotEqual(tx.base_state_digest,tx.result_state_digest)
        with self.assertRaises(CreatorContractError): EditorTransaction("tx",D,(op,op),"author")
if __name__=="__main__": unittest.main()
