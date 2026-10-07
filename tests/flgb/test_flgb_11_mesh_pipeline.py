import unittest
from skeleton.game.render.mesh_pipeline import MeshArtifact, RenderContractError
D="a"*64

class TestMeshPipeline(unittest.TestCase):
    def test_mesh_identity_binds_geometry_and_provenance(self):
        mesh=MeshArtifact("m",D,D,3,3,"triangles",D)
        self.assertEqual(len(mesh.digest),64)
        with self.assertRaises(RenderContractError):
            MeshArtifact("m",D,D,0,3,"triangles",D)

if __name__=="__main__": unittest.main()
