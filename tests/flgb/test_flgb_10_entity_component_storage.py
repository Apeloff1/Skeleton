import unittest
from skeleton.game.simulation.entity_component_storage import ComponentValue, EntityComponentStore, SimulationContractError
D="a"*64
E="b"*64

class TestECS(unittest.TestCase):
    def test_component_identity_is_unique_and_immutable_by_store_version(self):
        base=EntityComponentStore()
        one=base.put("e",ComponentValue("transform",D,E))
        self.assertEqual(one.get("e","transform").value_digest,E)
        self.assertNotEqual(base.digest,one.digest)
        with self.assertRaises(SimulationContractError):
            EntityComponentStore({"e":(ComponentValue("x",D,D),ComponentValue("x",D,E))})

if __name__=="__main__": unittest.main()
