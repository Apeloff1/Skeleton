import unittest
from skeleton.ai.product.chat_to_build_transaction import BuildOperation, ChatBuildTransaction, ProductContractError
D="a"*64
E="b"*64
F="c"*64

class TestChatToBuild(unittest.TestCase):
    def test_operations_are_sequenced_and_state_changes(self):
        tx=ChatBuildTransaction("tx",D,E,D,E,(BuildOperation(0,"edit",D,E,F),),"idem")
        self.assertEqual(len(tx.digest),64)
        with self.assertRaises(ProductContractError):
            ChatBuildTransaction("tx",D,E,D,E,(BuildOperation(1,"edit",D,E,F),),"idem")
        with self.assertRaises(ProductContractError):
            ChatBuildTransaction("tx",D,E,D,D,(BuildOperation(0,"edit",D,E,F),),"idem")

if __name__=="__main__": unittest.main()
