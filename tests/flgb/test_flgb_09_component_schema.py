import unittest
from skeleton.game.component_schema import ComponentField, ComponentSchema, CreatorContractError
class TestComponentSchema(unittest.TestCase):
    def test_duplicate_fields_fail_closed(self):
        schema=ComponentSchema("transform",1,(ComponentField("position","vec3",True),))
        self.assertEqual(len(schema.digest),64)
        with self.assertRaises(CreatorContractError):
            ComponentSchema("bad",1,(ComponentField("x","int",True),ComponentField("x","int",False)))
if __name__=="__main__": unittest.main()
