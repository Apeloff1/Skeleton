import unittest
from skeleton.game.editor_transaction import EditorOperation, EditorTransaction, GameContractError
D="a"*64
E="b"*64

class TestEditorTransaction(unittest.TestCase):
    def test_operation_sequence_and_state_change_are_bound(self):
        ops=(EditorOperation(0,"create","entity",None,E,D),)
        tx=EditorTransaction("tx",D,E,ops,D,"idem")
        self.assertEqual(len(tx.digest),64)
        with self.assertRaises(GameContractError):
            EditorTransaction("tx",D,E,(EditorOperation(1,"create","entity",None,E,D),),D,"idem")

if __name__=="__main__": unittest.main()
