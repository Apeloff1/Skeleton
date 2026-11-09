import unittest
from skeleton.game.project_migration import GameProjectError, MigrationStep, migration_path
D="a"*64
E="b"*64

class TestProjectMigration(unittest.TestCase):
    def test_migration_path_is_contiguous_and_reversible(self):
        steps=(MigrationStep("1-2",1,2,D,E),MigrationStep("2-3",2,3,E,D))
        self.assertEqual([s.to_version for s in migration_path(1,3,steps)],[2,3])
        with self.assertRaises(GameProjectError):
            migration_path(1,3,(steps[1],))

if __name__=="__main__": unittest.main()
