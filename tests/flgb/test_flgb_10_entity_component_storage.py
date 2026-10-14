import unittest
from skeleton.game.simulation.entity_component_storage import ComponentValue, EntityComponentStore, SimulationContractError
D="a"*64
E="b"*64

class TestECS(unittest.TestCase):
    def test_component_updates_are_immutable_and_unique(self):
        store=EntityComponentStore().set_component("e",ComponentValue("transform",D,E))
        changed=store.set_component("e",ComponentValue("transform",D,D))
        self.assertNotEqual(store.digest,changed.digest)
        with self.assertRaises(SimulationContractError):
            EntityComponentStore({"e":(ComponentValue("x",D,D),ComponentValue("x",D,E))})

if __name__=="__main__": unittest.main()
