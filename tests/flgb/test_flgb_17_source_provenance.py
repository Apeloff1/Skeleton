import unittest
from skeleton.ai.forge.source_provenance import SourceProvenance
D="a"*64
E="b"*64

class TestSourceProvenance(unittest.TestCase):
    def test_source_rights_acquisition_and_transform_are_bound(self):
        p=SourceProvenance("source",D,E,D,E)
        self.assertEqual(len(p.digest),64)

if __name__=="__main__": unittest.main()
