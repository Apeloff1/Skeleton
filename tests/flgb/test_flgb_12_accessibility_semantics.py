import unittest
from skeleton.game.presentation.accessibility_semantics import AccessibilityNode, PresentationContractError, validate_accessibility
class TestAccessibility(unittest.TestCase):
    def test_focus_order_is_unique_for_enabled_nodes(self):
        nodes=(AccessibilityNode("a","button","Play","",0),AccessibilityNode("b","button","Quit","",1))
        self.assertEqual([n.node_id for n in validate_accessibility(nodes)],["a","b"])
        with self.assertRaises(PresentationContractError):
            validate_accessibility((AccessibilityNode("a","button","A","",0),AccessibilityNode("b","button","B","",0)))
if __name__=="__main__":unittest.main()
