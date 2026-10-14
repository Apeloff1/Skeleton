import unittest
from skeleton.game.simulation.collision_narrowphase import AABB, narrowphase_aabb

class TestNarrowphase(unittest.TestCase):
    def test_penetration_is_integer_and_symmetric_identity(self):
        a=AABB("a",(0,0,0),(10,10,10))
        b=AABB("b",(5,2,1),(15,20,4))
        contact=narrowphase_aabb(b,a)
        self.assertEqual((contact.left_id,contact.right_id),("a","b"))
        self.assertEqual(contact.penetration_xyz,(5,8,3))
        self.assertIsNone(narrowphase_aabb(a,AABB("c",(10,0,0),(20,10,10))))

if __name__=="__main__": unittest.main()
