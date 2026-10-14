import unittest
from skeleton.game.build.asset_import import AssetImportReceipt
D="a"*64
class T(unittest.TestCase):
 def test_receipt(self): self.assertEqual(len(AssetImportReceipt("a",D,"imp","1",D,D).digest),64)
if __name__=="__main__": unittest.main()
