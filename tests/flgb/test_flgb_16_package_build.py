import unittest
from skeleton.game.build.package_build import PackageManifest
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_package_entries_canonical(self):
  p=PackageManifest("pkg","1",(E,D),D,D); self.assertEqual(p.entry_digests,(D,E)); self.assertEqual(len(p.digest),64)
if __name__=="__main__": unittest.main()
