import unittest
from skeleton.game.render.shadow_system import RenderContractError, ShadowAllocation, validate_shadow_atlas

class TestShadowSystem(unittest.TestCase):
    def test_atlas_allocations_cannot_overlap_or_escape(self):
        alloc=(ShadowAllocation("a",0,0,64),ShadowAllocation("b",64,0,64))
        self.assertEqual(len(validate_shadow_atlas(alloc,128)),2)
        with self.assertRaises(RenderContractError):
            validate_shadow_atlas((ShadowAllocation("a",0,0,80),ShadowAllocation("b",64,0,64)),128)

if __name__=="__main__": unittest.main()
