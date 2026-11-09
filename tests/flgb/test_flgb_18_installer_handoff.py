import unittest
from skeleton.ai.product.installer_handoff import InstallerHandoff, ProductContractError
D="a"*64
E="b"*64

class TestInstallerHandoff(unittest.TestCase):
    def test_signing_provenance_and_platforms_are_bound(self):
        handoff=InstallerHandoff(D,E,D,E,("windows-x64","windows-arm64"),D)
        self.assertEqual(handoff.target_platforms,("windows-arm64","windows-x64"))
        self.assertEqual(len(handoff.digest),64)
        with self.assertRaises(ProductContractError):
            InstallerHandoff(D,E,D,E,(),D)

if __name__=="__main__": unittest.main()
