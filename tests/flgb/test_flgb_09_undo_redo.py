import unittest
from skeleton.game.undo_redo import HistoryEntry, UndoRedoState
D="a"*64
E="b"*64
F="c"*64

class TestUndoRedo(unittest.TestCase):
    def test_commit_undo_redo_round_trip(self):
        base=UndoRedoState(D)
        committed=base.commit(HistoryEntry(F,D,E))
        undone=committed.undo()
        redone=undone.redo()
        self.assertEqual(committed.current_digest,E)
        self.assertEqual(undone.current_digest,D)
        self.assertEqual(redone.current_digest,E)

if __name__=="__main__": unittest.main()
