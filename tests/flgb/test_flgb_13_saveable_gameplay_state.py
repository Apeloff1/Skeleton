import unittest
from skeleton.game.gameplay.saveable_gameplay_state import GameplayContractError, GameplaySnapshot
D="a"*64
E="b"*64
class TestSaveState(unittest.TestCase):
    def test_snapshot_lineage_is_explicit(self):
        base=GameplaySnapshot(0,D,D,D,D)
        nxt=GameplaySnapshot(1,E,D,E,D,base.digest)
        self.assertEqual(nxt.prior_snapshot_digest,base.digest)
        with self.assertRaises(GameplayContractError): GameplaySnapshot(1,E,D,E,D)
if __name__=="__main__": unittest.main()
