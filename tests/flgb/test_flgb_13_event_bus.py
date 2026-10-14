import unittest
from skeleton.game.gameplay.event_bus import EventBus
D="a"*64
class T(unittest.TestCase):
 def test_append_sequence(self):
  b=EventBus().publish("hit","e",D).publish("heal","e",D)
  self.assertEqual([e.sequence for e in b.events],[0,1]); self.assertEqual(len(b.digest),64)
if __name__=="__main__": unittest.main()
