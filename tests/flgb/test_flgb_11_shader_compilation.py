import unittest
from skeleton.game.render.shader_compilation import RenderContractError, ShaderCompileReceipt, ShaderCompileRequest
D="a"*64
E="b"*64

class TestShaderCompilation(unittest.TestCase):
    def test_request_identity_binds_target_and_defines(self):
        request=ShaderCompileRequest("s",D,"vertex","spirv",("FOO","BAR"))
        self.assertEqual(request.defines,("BAR","FOO"))
        receipt=ShaderCompileReceipt(request.digest,D,E,D,E)
        self.assertEqual(len(receipt.digest),64)
        with self.assertRaises(RenderContractError):
            ShaderCompileRequest("s",D,"invalid","spirv")

if __name__=="__main__": unittest.main()
