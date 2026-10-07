import unittest
from skeleton.game.gameplay.event_bus import GameplayContractError, GameplayEvent, GameplayEventBus
D="a"*64
E="b"*64
class TestEventBus(unittest.TestCase):
    def test_append_only_hash_chain(self):
        bus=GameplayEventBus().publish("quest","system",D).publish("combat","player",E)
        self.assertEqual(bus.events[1].prior_event_digest,bus.events[0].digest)
        self.assertEqual(len(bus.topic("quest")),1)
        with self.assertRaises(GameplayContractError): GameplayEventBus((GameplayEvent(1,"x","s",D),))
if __name__=="__main__": unittest.main()
