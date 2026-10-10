import unittest
from skeleton.game.generation.terrain_generation import GenerationContractError, TerrainChunkReceipt, TerrainChunkRequest
D="a"*64
E="b"*64

class TestTerrainGeneration(unittest.TestCase):
    def test_request_receipt_bind_chunk_identity(self):
        request=TerrainChunkRequest("w",2,-3,256,D,E)
        receipt=TerrainChunkReceipt(request.request_digest,D,E,D)
        self.assertEqual(receipt.request_digest,request.request_digest)
        with self.assertRaises(GenerationContractError):
            TerrainChunkRequest("w",0,0,1,D,E)

if __name__=="__main__": unittest.main()
