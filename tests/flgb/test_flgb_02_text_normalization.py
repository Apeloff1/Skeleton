import unittest

from skeleton.ai.model_runtime.text_normalization import normalize_text
from skeleton.ai.model_runtime.tokenization import TokenizerContractError


class TestTextNormalization(unittest.TestCase):
    def test_normalizes_unicode_newlines_and_bom(self):
        self.assertEqual(normalize_text("\ufeffCafe\u0301\r\nnext"), "Caf\u00e9\nnext")

    def test_none_preserves_unicode_composition(self):
        self.assertEqual(normalize_text("e\u0301", "NONE"), "e\u0301")

    def test_rejects_controls_and_bad_form(self):
        with self.assertRaises(TokenizerContractError):
            normalize_text("ok\x00bad")
        with self.assertRaises(TokenizerContractError):
            normalize_text("ok", "BAD")

    def test_idempotent(self):
        value = "Caf\u00e9\ntext"
        self.assertEqual(normalize_text(normalize_text(value)), value)


if __name__ == "__main__":
    unittest.main()
