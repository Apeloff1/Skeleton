import unittest
from skeleton.game.project_migration import GameContractError, MigrationStep, validate_migration_path
D="a"*64

class TestProjectMigration(unittest.TestCase):
    def test_path_is_contiguous_and_reaches_target(self):
        steps=(MigrationStep("1-2",1,2,D,True),MigrationStep("2-3",2,3,D,False))
        self.assertEqual(validate_migration_path(steps,1,3),steps)
        with self.assertRaises(GameContractError):
            validate_migration_path((MigrationStep("2-3",2,3,D,False),),1,3)

if __name__=="__main__": unittest.main()
