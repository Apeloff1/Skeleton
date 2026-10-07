import unittest
from skeleton.ai.training.dataset_rights import DatasetRights

D="a"*64

class TestDatasetRights(unittest.TestCase):
    def test_training_scope_requires_explicit_allowed_rights(self):
        rights=DatasetRights("data","source","allowed","lic",("training",),D)
        self.assertTrue(rights.permits("training"))
        self.assertFalse(rights.permits("redistribution"))
        denied=DatasetRights("data2","source","denied",None,(),D)
        self.assertFalse(denied.permits("training"))

if __name__=="__main__": unittest.main()
