import unittest
from skeleton.game.render.mesh_pipeline import MeshArtifact, RenderContractError
D="a"*64

class TestMeshPipeline(unittest.TestCase):
    def test_indexed_mesh_requires_vertices(self):
        mesh=MeshArtifact("m",D,10,30,"triangles",D)
        self.assertEqual(len(mesh.digest),64)
        with self.assertRaises(RenderContractError):
            MeshArtifact("bad",D,0,3,"triangles",D)

if __name__=="__main__": unittest.main()
