import unittest
from skeleton.ai.forge.clean_room_transformation import CleanRoomTransformation, ForgeContractError
D="a"*64
E="b"*64

class TestCleanRoom(unittest.TestCase):
    def test_similarity_threshold_is_non_compensable(self):
        x=CleanRoomTransformation("x",D,E,D,120000,E)
        self.assertTrue(x.clears(120000))
        self.assertFalse(x.clears(119999))
        with self.assertRaises(ForgeContractError): x.clears(1000001)

if __name__=="__main__": unittest.main()
