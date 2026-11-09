import unittest
from skeleton.game.undo_redo import GameProjectError, UndoRedoLog
D="a"*64
E="b"*64
F="c"*64

class TestUndoRedo(unittest.TestCase):
    def test_undo_redo_and_branch_truncation(self):
        log=UndoRedoLog().append(D,E).append(E,F)
        log,inverse=log.undo()
        self.assertEqual(inverse,F)
        log,forward=log.redo()
        self.assertEqual(forward,E)
        log,_=log.undo()
        branched=log.append(F,D)
        self.assertEqual(len(branched.entries),2)
        with self.assertRaises(GameProjectError): UndoRedoLog().undo()

if __name__=="__main__": unittest.main()
