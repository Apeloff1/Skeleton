import unittest
from skeleton.game.build.shader_bake import ShaderBakeReceipt
D="a"*64
class T(unittest.TestCase):
 def test_binds_compiler_target(self): self.assertEqual(ShaderBakeReceipt("s",D,D,"spirv",D).target,"spirv")
if __name__=="__main__": unittest.main()
