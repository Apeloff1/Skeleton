import unittest
from skeleton.game.editor_transaction import EditorOperation, EditorTransaction, GameProjectError, commit_transaction
from skeleton.game.project_manifest import ProjectManifest
D="a"*64
E="b"*64

class TestEditorTransaction(unittest.TestCase):
    def test_stale_transaction_fails_closed(self):
        base=ProjectManifest("p",0,1,(),D,D,D)
        nxt=base.revise(config_digest=E)
        op=EditorOperation("o","update","target",D,E)
        tx=EditorTransaction("t","p",0,"idem",(op,))
        receipt=commit_transaction(tx,base,nxt)
        self.assertEqual(receipt.committed_revision,1)
        stale=EditorTransaction("t2","p",1,"idem2",(op,))
        with self.assertRaises(GameProjectError): commit_transaction(stale,base,nxt)

if __name__=="__main__": unittest.main()
