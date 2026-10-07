import unittest
from skeleton.game.presentation.skeletal_animation import PresentationContractError, Skeleton, SkeletonJoint
D="a"*64
class TestSkeleton(unittest.TestCase):
    def test_single_root_and_no_cycles(self):
        s=Skeleton((SkeletonJoint("root",None,D),SkeletonJoint("hand","root",D)))
        self.assertEqual(s.root_id,"root")
        with self.assertRaises(PresentationContractError):
            Skeleton((SkeletonJoint("a",None,D),SkeletonJoint("b",None,D)))
if __name__=="__main__": unittest.main()
