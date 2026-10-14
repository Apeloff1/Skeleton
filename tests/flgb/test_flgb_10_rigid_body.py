import unittest
from skeleton.game.simulation.rigid_body import RigidBody

class TestRigidBody(unittest.TestCase):
    def test_integer_integration_is_deterministic(self):
        body=RigidBody("b",1000,(0,0,0),(100,0,-50))
        self.assertEqual(body.integrate(500000000).position,(50,0,-25))
        static=RigidBody("s",1000,(1,2,3),(999,999,999),False)
        self.assertIs(static.integrate(1000000000),static)

if __name__=="__main__": unittest.main()
