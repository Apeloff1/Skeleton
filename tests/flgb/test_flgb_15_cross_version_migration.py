import unittest
from skeleton.game.platform.cross_version_migration import PlatformContractError, VersionMigration, migration_path
D="a"*64
class T(unittest.TestCase):
 def test_gapless_path(self):
  s=(VersionMigration("1-2",1,2,D,D),VersionMigration("2-3",2,3,D,D))
  self.assertEqual([x.migration_id for x in migration_path(s,1,3)],["1-2","2-3"])
  with self.assertRaises(PlatformContractError): migration_path((s[1],),1,3)
if __name__=="__main__": unittest.main()
