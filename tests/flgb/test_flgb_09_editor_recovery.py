import unittest
from skeleton.game.editor_recovery import EditorCheckpoint, recover_editor
D="a"*64
E="b"*64
class TestEditorRecovery(unittest.TestCase):
    def test_pending_transaction_is_discarded_to_last_durable_state(self):
        base=EditorCheckpoint("c0",0,D,None)
        dirty=EditorCheckpoint("c1",1,E,D,base.digest)
        recovered=recover_editor((base,dirty))
        self.assertEqual(recovered.durable_state_digest,E)
        self.assertIsNone(recovered.pending_transaction_digest)
        self.assertEqual(recovered.prior_checkpoint_digest,dirty.digest)
if __name__=="__main__": unittest.main()
