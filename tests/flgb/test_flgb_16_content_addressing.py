import unittest
from skeleton.game.build.content_addressing import ContentAddress
D="a"*64
class T(unittest.TestCase):
 def test_uri(self): self.assertEqual(ContentAddress("asset","sha256",D).uri,f"ca://asset/sha256/{D}")
if __name__=="__main__": unittest.main()
