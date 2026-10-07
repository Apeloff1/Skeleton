import unittest
from skeleton.game.render.shader_compilation import RenderContractError, ShaderCompileReceipt, ShaderCompileRequest
D="a"*64
E="b"*64

class TestShaderCompilation(unittest.TestCase):
    def test_request_identity_binds_backend_compiler_and_defines(self):
        req=ShaderCompileRequest("s",D,"vertex","spirv",("B","A"),E)
        self.assertEqual(req.defines,("A","B"))
        receipt=ShaderCompileReceipt(req.digest,E,D)
        self.assertEqual(receipt.request_digest,req.digest)
        with self.assertRaises(RenderContractError):
            ShaderCompileRequest("s",D,"vertex","unknown",(),E)

if __name__=="__main__": unittest.main()
