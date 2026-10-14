import unittest
from skeleton.game.asset_references import AssetReference
D="a"*64
E="b"*64
F="c"*64

class TestAssetReferences(unittest.TestCase):
    def test_asset_reference_binds_content_rights_and_provenance(self):
        asset=AssetReference("hero","texture",D,E,F)
        self.assertEqual(len(asset.digest),64)
        self.assertNotEqual(asset.content_digest,asset.rights_digest)

if __name__=="__main__": unittest.main()
