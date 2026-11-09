import unittest
from skeleton.game.platform.replication import ReplicatedField, merge_replication
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_latest_tick_wins(self):
  r=merge_replication((ReplicatedField("e","x",1,D,"a"),ReplicatedField("e","x",2,E,"a")))
  self.assertEqual(r[0].value_digest,E)
if __name__=="__main__": unittest.main()
