import unittest
from skeleton.game.simulation.physics_query import QueryHit, RayQuery, SimulationContractError, rank_query_hits
D="a"*64

class TestPhysicsQuery(unittest.TestCase):
    def test_hits_are_distance_then_identity_ordered(self):
        RayQuery("q",(0,0,0),(1,0,0),100)
        hits=rank_query_hits((QueryHit("b",10,D),QueryHit("a",10,D),QueryHit("c",5,D)))
        self.assertEqual([h.entity_id for h in hits],["c","a","b"])
        with self.assertRaises(SimulationContractError):
            RayQuery("q",(0,0,0),(0,0,0),100)

if __name__=="__main__": unittest.main()
