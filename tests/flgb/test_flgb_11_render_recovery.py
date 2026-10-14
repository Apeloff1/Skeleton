import unittest
from skeleton.game.render.render_recovery import RenderCheckpoint, RenderContractError, recover_render
D="a"*64
E="b"*64

class TestRenderRecovery(unittest.TestCase):
    def test_faults_map_to_bounded_recovery_modes(self):
        checkpoint=RenderCheckpoint(0,D,E,D)
        self.assertEqual(recover_render(checkpoint,"resource-lost").action,"rebuild-resources")
        self.assertEqual(recover_render(checkpoint,"device-lost").action,"safe-render")
        self.assertEqual(recover_render(checkpoint,"unknown").action,"safe-render")
        with self.assertRaises(RenderContractError):
            RenderCheckpoint(1,D,E,D)

if __name__=="__main__": unittest.main()
