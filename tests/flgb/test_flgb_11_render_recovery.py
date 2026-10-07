import unittest
from skeleton.game.render.render_recovery import RenderContractError, RenderRecoveryReceipt
D="a"*64
E="b"*64

class TestRenderRecovery(unittest.TestCase):
    def test_fallback_backend_requires_exact_restored_state(self):
        receipt=RenderRecoveryReceipt(7,D,E,"vulkan","software",D,D)
        self.assertEqual(len(receipt.digest),64)
        with self.assertRaises(RenderContractError):
            RenderRecoveryReceipt(7,D,E,"vulkan","software",D,E)
        with self.assertRaises(RenderContractError):
            RenderRecoveryReceipt(7,D,E,"vulkan","vulkan",D,D)

if __name__=="__main__": unittest.main()
