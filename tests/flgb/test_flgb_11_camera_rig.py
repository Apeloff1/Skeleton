import unittest
from skeleton.game.render.camera_rig import Camera, CameraRig, RenderContractError

class TestCameraRig(unittest.TestCase):
    def test_active_camera_and_clip_planes_are_validated(self):
        cam=Camera("main",(0,0,0),(0,0,0),60000,10,100000)
        rig=CameraRig("r",(cam,),"main")
        self.assertEqual(rig.active_camera_id,"main")
        with self.assertRaises(RenderContractError):
            CameraRig("r",(cam,),"missing")

if __name__=="__main__": unittest.main()
