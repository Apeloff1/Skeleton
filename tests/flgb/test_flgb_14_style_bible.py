import unittest
from skeleton.game.generation.style_bible import ContinuityContractError, StyleBible, StyleRule
D="a"*64

class TestStyleBible(unittest.TestCase):
    def test_rule_identity_is_unique_and_digest_stable(self):
        bible=StyleBible((StyleRule("voice","dialogue",D,"required"),StyleRule("palette","visual",D,"advisory")))
        self.assertEqual(len(bible.digest),64)
        with self.assertRaises(ContinuityContractError):
            StyleBible((StyleRule("voice","dialogue",D,"required"),StyleRule("voice","dialogue",D,"required")))

if __name__=="__main__": unittest.main()
