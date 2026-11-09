import unittest
from skeleton.game.presentation.skeletal_animation import Bone, Pose, PresentationContractError, Skeleton
D="a"*64
E="b"*64

class TestSkeletalAnimation(unittest.TestCase):
    def test_bone_hierarchy_is_acyclic_and_pose_is_canonical(self):
        skeleton=Skeleton((Bone("root",None,D),Bone("hand","root",D)))
        pose=Pose(skeleton.digest,{"hand":E,"root":D})
        self.assertEqual(list(pose.local_pose_digests),["hand","root"])
        with self.assertRaises(PresentationContractError):
            Skeleton((Bone("a","b",D),Bone("b","a",D)))

if __name__=="__main__": unittest.main()
