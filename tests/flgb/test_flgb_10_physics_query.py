import unittest
from skeleton.game.simulation.physics_query import AABB, query_aabb

class TestPhysicsQuery(unittest.TestCase):
    def test_query_hits_are_distance_then_identity_ordered(self):
        q=AABB("q",(0,0,0),(10,10,10))
        boxes=(AABB("b",(8,0,0),(12,10,10)),AABB("a",(2,0,0),(6,10,10)),AABB("x",(20,0,0),(30,10,10)))
        hits=query_aabb(boxes,q)
        self.assertEqual([h.collider_id for h in hits],["a","b"])

if __name__=="__main__": unittest.main()
