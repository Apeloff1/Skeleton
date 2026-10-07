import unittest
from skeleton.game.simulation.collision_narrowphase import SphereCollider, sphere_contact

class TestNarrowphase(unittest.TestCase):
    def test_sphere_contact_uses_integer_distance(self):
        a=SphereCollider("a",0,0,0,10)
        b=SphereCollider("b",12,0,0,5)
        contact=sphere_contact(a,b)
        self.assertIsNotNone(contact)
        self.assertEqual(contact.penetration,3)
        self.assertIsNone(sphere_contact(a,SphereCollider("c",20,0,0,5)))

if __name__=="__main__": unittest.main()
