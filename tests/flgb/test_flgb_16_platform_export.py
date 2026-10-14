import unittest
from skeleton.game.build.platform_export import PlatformExport
D="a"*64
class T(unittest.TestCase):
 def test_export_binds_toolchain(self): self.assertEqual(PlatformExport("e",D,"windows","x64",D,D).toolchain_digest,D)
if __name__=="__main__": unittest.main()
