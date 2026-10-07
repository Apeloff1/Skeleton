import unittest
from skeleton.ai.model_runtime.quantization import ModelRuntimeError, QuantizationProfile
class TestQuantization(unittest.TestCase):
    def test_scheme_precision_contract(self):
        self.assertEqual(QuantizationProfile("int4",4,128).bits,4)
        with self.assertRaises(ModelRuntimeError): QuantizationProfile("int4",8,128)
        with self.assertRaises(ModelRuntimeError): QuantizationProfile("none",4,None)
if __name__=="__main__": unittest.main()
