import unittest
from skeleton.game.undo_redo import CreatorContractError, UndoRedoLog
D="a"*64
E="b"*64
F="c"*64
class TestUndoRedo(unittest.TestCase):
    def test_undo_redo_and_branch_truncation(self):
        log=UndoRedoLog().append(D,E,F)
        undone,state=log.undo()
        self.assertEqual(state,F)
        redone,state2=undone.redo()
        self.assertEqual(state2,E)
        branched=undone.append(E,F,D)
        self.assertEqual(len(branched.entries),1)
        with self.assertRaises(CreatorContractError): UndoRedoLog().undo()
if __name__=="__main__": unittest.main()
