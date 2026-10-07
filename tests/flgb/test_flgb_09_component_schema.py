import unittest
from skeleton.game.component_schema import ComponentField, ComponentSchema, GameContractError
D="a"*64

class TestComponentSchema(unittest.TestCase):
    def test_field_names_unique_and_required_default_conflict_rejected(self):
        schema=ComponentSchema("transform",1,(ComponentField("x","float",True),ComponentField("y","float",False,D)))
        self.assertEqual([f.name for f in schema.fields],["x","y"])
        with self.assertRaises(GameContractError):
            ComponentField("x","float",True,D)
        with self.assertRaises(GameContractError):
            ComponentSchema("bad",1,(ComponentField("x","float",True),ComponentField("x","int",False)))

if __name__=="__main__": unittest.main()
