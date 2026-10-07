import unittest
from skeleton.game.generation.style_bible import GenerationContractError, StyleBible
D="a"*64
class TestStyleBible(unittest.TestCase):
    def test_required_and_forbidden_tags_are_non_compensable(self):
        bible=StyleBible("b",1,("grounded","original"),("licensed-style",),D)
        self.assertEqual(bible.validate_tags(("grounded","original")),())
        self.assertEqual(bible.validate_tags(("grounded","licensed-style")),("forbidden:licensed-style","missing:original"))
        with self.assertRaises(GenerationContractError):
            StyleBible("bad",1,("x",),("x",),D)
if __name__=="__main__": unittest.main()
