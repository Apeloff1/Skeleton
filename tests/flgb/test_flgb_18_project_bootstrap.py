import unittest
from skeleton.ai.product.project_bootstrap import ProductContractError, ProjectBootstrapReceipt, ProjectBootstrapRequest
D="a"*64
E="b"*64

class TestProjectBootstrap(unittest.TestCase):
    def test_request_identity_and_receipt_are_bound(self):
        request=ProjectBootstrapRequest("project",D,E,D,E,("world-b","world-a"))
        self.assertEqual(request.requested_worlds,("world-a","world-b"))
        receipt=ProjectBootstrapReceipt(request.digest,D,E,D)
        self.assertEqual(len(receipt.digest),64)
        with self.assertRaises(ProductContractError):
            ProjectBootstrapRequest("project",D,E,D,E,())

if __name__=="__main__": unittest.main()
