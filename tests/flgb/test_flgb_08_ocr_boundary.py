import unittest
from skeleton.ai.multimodal.ocr_boundary import MultimodalContractError, OCRReceipt, OCRRequest
D="a"*64

class TestOCRBoundary(unittest.TestCase):
    def test_ocr_input_remains_untrusted(self):
        req=OCRRequest("r",D,("en",),1000)
        self.assertTrue(req.untrusted_input)
        receipt=OCRReceipt("r",D,10,D)
        self.assertEqual(receipt.output_chars,10)
        with self.assertRaises(MultimodalContractError):
            OCRRequest("r",D,(),1000,False)

if __name__=="__main__": unittest.main()
