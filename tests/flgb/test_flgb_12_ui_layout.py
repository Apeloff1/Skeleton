import unittest
from skeleton.game.presentation.ui_layout import PresentationContractError, UILayout, UINode

class TestUILayout(unittest.TestCase):
    def test_paint_order_and_cycle_rejection(self):
        layout=UILayout((UINode("root",None,0,0,100,100,0),UINode("top","root",0,0,10,10,2),UINode("mid","root",0,0,10,10,1)))
        self.assertEqual(layout.paint_order,("root","mid","top"))
        with self.assertRaises(PresentationContractError):
            UILayout((UINode("a","b",0,0,1,1),UINode("b","a",0,0,1,1)))

if __name__=="__main__": unittest.main()
