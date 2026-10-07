import unittest
from skeleton.game.presentation.accessibility_semantics import AccessibilityNode, PresentationContractError, validate_accessibility
class TestAccessibility(unittest.TestCase):
    def test_visible_nodes_require_labels_and_focus_is_unique(self):
        nodes=(AccessibilityNode("a","button","Play",0),AccessibilityNode("b","button","Quit",1))
        self.assertEqual([n.node_id for n in validate_accessibility(nodes)],["a","b"])
        with self.assertRaises(PresentationContractError): AccessibilityNode("x","button","",0)
        with self.assertRaises(PresentationContractError): validate_accessibility((nodes[0],AccessibilityNode("c","button","Other",0)))
if __name__=="__main__": unittest.main()
