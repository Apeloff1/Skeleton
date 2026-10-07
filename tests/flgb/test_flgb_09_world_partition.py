import unittest
from skeleton.game.world_partition import GameContractError, WorldPartition, validate_partitions
D="a"*64

class TestWorldPartition(unittest.TestCase):
    def test_entity_has_single_partition_owner(self):
        a=WorldPartition("a","w",D,("e1","e2"),"shard-a")
        b=WorldPartition("b","w",D,("e3",),"shard-b")
        self.assertEqual([p.partition_id for p in validate_partitions((b,a))],["a","b"])
        with self.assertRaises(GameContractError):
            validate_partitions((a,WorldPartition("b","w",D,("e2",),"shard-b")))

if __name__=="__main__": unittest.main()
