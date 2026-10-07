import unittest
from skeleton.game.presentation.skeletal_animation import Joint, PresentationContractError, Skeleton
class TestSkeleton(unittest.TestCase):
    def test_skeleton_is_single_root_and_acyclic(self):
        s=Skeleton((Joint("root",None,(0,0,0)),Joint("hand","root",(1,0,0))))
        self.assertEqual(s.root_id,"root")
        with self.assertRaises(PresentationContractError):
            Skeleton((Joint("a","b",(0,0,0)),Joint("b","a",(0,0,0))))
if __name__=="__main__":unittest.main()
