import unittest
from skeleton.game.simulation.rigid_body import RigidBody

class TestRigidBody(unittest.TestCase):
    def test_integer_integration_and_static_body(self):
        body=RigidBody("e",1000,0,0,0,1000000,0,0,True)
        nxt=body.integrate(1000000)
        self.assertEqual((nxt.pos_x,nxt.vel_x),(1000000,1000000))
        static=RigidBody("s",1000,1,2,3,4,5,6,False)
        self.assertIs(static.integrate(1000),static)

if __name__=="__main__": unittest.main()
