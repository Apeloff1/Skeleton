import unittest
from skeleton.game.project_migration import CreatorContractError, MigrationStep, plan_migration
D="a"*64
class TestProjectMigration(unittest.TestCase):
    def test_migration_requires_gapless_single_version_steps(self):
        steps=(MigrationStep("m1",1,2,D,True),MigrationStep("m2",2,3,D,True))
        self.assertEqual([s.migration_id for s in plan_migration(steps,1,3)],["m1","m2"])
        with self.assertRaises(CreatorContractError): plan_migration((steps[1],),1,3)
if __name__=="__main__": unittest.main()
