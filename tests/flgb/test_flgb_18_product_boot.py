import unittest
from skeleton.ai.product.product_boot import PlaneBootEvidence, ProductBootManifest, ProductContractError
D="a"*64
E="b"*64

class TestProductBoot(unittest.TestCase):
    def evidence(self):
        return tuple(PlaneBootEvidence(f"FLGB-{i:02d}",D,"implemented-pending-verification") for i in range(1,19))

    def test_boot_requires_all_eighteen_planes(self):
        boot=ProductBootManifest("product",D,self.evidence(),D,E)
        self.assertEqual(len(boot.plane_evidence),18)
        self.assertEqual(len(boot.digest),64)
        with self.assertRaises(ProductContractError):
            ProductBootManifest("product",D,self.evidence()[:-1],D,E)

if __name__=="__main__": unittest.main()
