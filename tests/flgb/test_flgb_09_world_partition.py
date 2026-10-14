import unittest
from skeleton.game.world_partition import GameProjectError, WorldCell, validate_partitions

class TestWorldPartition(unittest.TestCase):
    def test_entity_has_single_partition_custody(self):
        cells=(WorldCell("a",0,0,0,("e1",)),WorldCell("b",1,0,0,("e2",)))
        self.assertEqual([c.cell_id for c in validate_partitions(cells)],["a","b"])
        with self.assertRaises(GameProjectError):
            validate_partitions((WorldCell("a",0,0,0,("e",)),WorldCell("b",1,0,0,("e",))))

if __name__=="__main__": unittest.main()
