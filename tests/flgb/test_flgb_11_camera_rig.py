import unittest
from skeleton.game.render.camera_rig import CameraRig, RenderContractError

class TestCameraRig(unittest.TestCase):
    def test_target_and_clip_planes_are_validated(self):
        camera=CameraRig("main",0,0,0,0,0,-1000,60000,10,100000)
        self.assertEqual(len(camera.digest),64)
        with self.assertRaises(RenderContractError):
            CameraRig("bad",0,0,0,0,0,0,60000,10,100000)

if __name__=="__main__": unittest.main()
