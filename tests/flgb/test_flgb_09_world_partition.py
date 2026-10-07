import unittest
from skeleton.game.world_partition import WorldPartition, partitions_for_point
D="a"*64
class TestWorldPartition(unittest.TestCase):
    def test_half_open_partition_bounds(self):
        parts=(WorldPartition("a","w",0,0,10,10,D),WorldPartition("b","w",10,0,20,10,D))
        self.assertEqual([p.partition_id for p in partitions_for_point(parts,"w",9,5)],["a"])
        self.assertEqual([p.partition_id for p in partitions_for_point(parts,"w",10,5)],["b"])
if __name__=="__main__": unittest.main()
