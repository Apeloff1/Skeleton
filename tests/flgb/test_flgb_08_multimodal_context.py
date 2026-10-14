import unittest
from skeleton.ai.multimodal.multimodal_context import MultimodalContextItem, MultimodalContractError, compile_multimodal_context
D="a"*64

class TestMultimodalContext(unittest.TestCase):
    def test_mandatory_items_obey_token_and_byte_budgets(self):
        must=MultimodalContextItem("m","image",D,5,100,10,True)
        optional=MultimodalContextItem("o","audio",D,5,100,1,False)
        self.assertEqual(compile_multimodal_context((must,optional),5,100),("m",))
        with self.assertRaises(MultimodalContractError):
            compile_multimodal_context((must,),4,100)

if __name__=="__main__": unittest.main()
