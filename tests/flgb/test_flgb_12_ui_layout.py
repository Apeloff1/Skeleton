import unittest
from skeleton.game.presentation.ui_layout import PresentationContractError, UILayout, UILayoutNode
class TestUILayout(unittest.TestCase):
    def test_paint_order_and_cycles(self):
        layout=UILayout((UILayoutNode("root",None,0,0,100,100,0),UILayoutNode("modal","root",0,0,50,50,10)))
        self.assertEqual(layout.paint_order,("root","modal"))
        with self.assertRaises(PresentationContractError):
            UILayout((UILayoutNode("a","b",0,0,1,1,0),UILayoutNode("b","a",0,0,1,1,0)))
if __name__=="__main__": unittest.main()
