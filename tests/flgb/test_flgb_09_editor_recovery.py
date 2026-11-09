import unittest
from skeleton.game.editor_recovery import EditorRecoveryReceipt, GameProjectError
D="a"*64
E="b"*64

class TestEditorRecovery(unittest.TestCase):
    def test_recovery_requires_exact_manifest_identity(self):
        receipt=EditorRecoveryReceipt("p",D,E,E,10,D)
        self.assertEqual(len(receipt.digest),64)
        with self.assertRaises(GameProjectError):
            EditorRecoveryReceipt("p",D,E,E,10,E)

if __name__=="__main__": unittest.main()
