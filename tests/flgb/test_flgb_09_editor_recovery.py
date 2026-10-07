import unittest
from skeleton.game.editor_recovery import EditorCheckpoint, GameContractError, recover_editor
D="a"*64
E="b"*64
F="c"*64

class TestEditorRecovery(unittest.TestCase):
    def test_pending_transaction_requires_explicit_recovery_action(self):
        clean=EditorCheckpoint("s",0,D,E,None)
        self.assertEqual(recover_editor(clean).action,"resume")
        pending=EditorCheckpoint("s",0,D,E,F)
        self.assertEqual(recover_editor(pending,prefer_rollback=True).action,"rollback-pending")
        self.assertEqual(recover_editor(pending,prefer_rollback=False).action,"discard-pending")
        with self.assertRaises(GameContractError):
            EditorCheckpoint("s",1,D,E,None)

if __name__=="__main__": unittest.main()
