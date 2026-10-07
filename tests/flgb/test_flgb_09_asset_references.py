import unittest
from skeleton.game.asset_references import AssetCatalog, AssetReference, GameContractError
D="a"*64
E="b"*64

class TestAssetReferences(unittest.TestCase):
    def test_catalog_resolves_immutable_asset_identity(self):
        asset=AssetReference("hero.mesh",D,"mesh",E,D)
        catalog=AssetCatalog((asset,))
        self.assertEqual(catalog.resolve("hero.mesh"),asset)
        with self.assertRaises(GameContractError):
            AssetCatalog((asset,asset))

if __name__=="__main__": unittest.main()
