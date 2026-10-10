import unittest
from skeleton.game.component_schema import ComponentField, ComponentSchema, GameProjectError

class TestComponentSchema(unittest.TestCase):
    def test_fields_are_unique_and_typed(self):
        schema=ComponentSchema("transform",1,(ComponentField("position","vec3",True),))
        self.assertEqual(len(schema.digest),64)
        with self.assertRaises(GameProjectError):
            ComponentSchema("bad",1,(ComponentField("x","int",True),ComponentField("x","float",False)))

if __name__=="__main__": unittest.main()
