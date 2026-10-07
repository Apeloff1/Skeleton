import unittest
from skeleton.game.presentation.accessibility_semantics import AccessibilityNode, PresentationContractError, accessibility_focus_order

class TestAccessibility(unittest.TestCase):
    def test_focus_order_is_explicit_and_labels_are_required(self):
        nodes=(AccessibilityNode("b","button","Back",True,2),AccessibilityNode("title","heading","Menu",False,0),AccessibilityNode("a","button","Play",True,1))
        self.assertEqual(accessibility_focus_order(nodes),("a","b"))
        with self.assertRaises(PresentationContractError):
            AccessibilityNode("bad","button"," ",True,0)

if __name__=="__main__": unittest.main()
