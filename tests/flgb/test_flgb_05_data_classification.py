import unittest
from skeleton.security.data_classification import classify_data

class TestClassification(unittest.TestCase):
    def test_sensitive_inputs_raise_classification(self):
        self.assertEqual(classify_data(contains_secret=False,contains_pii=False,regulated=False).classification,"internal")
        self.assertEqual(classify_data(contains_secret=False,contains_pii=True,regulated=False).classification,"confidential")
        self.assertEqual(classify_data(contains_secret=True,contains_pii=False,regulated=False).classification,"restricted")

if __name__=="__main__": unittest.main()
