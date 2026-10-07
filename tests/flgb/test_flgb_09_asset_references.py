import unittest
from skeleton.game.asset_references import AssetReference
D="a"*64
E="b"*64
class TestAssetReferences(unittest.TestCase):
    def test_asset_binds_content_provenance_and_rights(self):
        asset=AssetReference("mesh:hero",D,"mesh",E,D)
        self.assertEqual(len(asset.digest),64)
        self.assertEqual(asset.rights_digest,D)
if __name__=="__main__": unittest.main()
