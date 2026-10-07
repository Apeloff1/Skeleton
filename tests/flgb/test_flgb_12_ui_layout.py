import unittest
from skeleton.game.presentation.ui_layout import PresentationContractError, UINode, validate_ui_layout
class TestUILayout(unittest.TestCase):
    def test_ui_hierarchy_is_acyclic(self):
        nodes=(UINode("root",None,"window",(0,0,100,100)),UINode("button","root","button",(0,0,10,10)))
        self.assertEqual(len(validate_ui_layout(nodes)),2)
        with self.assertRaises(PresentationContractError):
            validate_ui_layout((UINode("a","b","x",(0,0,1,1)),UINode("b","a","x",(0,0,1,1))))
if __name__=="__main__":unittest.main()
