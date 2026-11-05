"""Native lexical/tokenization deficits are measured rather than waived."""
from __future__ import annotations
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_catalog import iter_challenges
from skeleton.ai.runtime.operational_ai.native_supervised.representability import (
    inspect,full_audit,
)
from skeleton.ai.runtime.operational_ai.native_supervised.lexical_gaps import inspect as gaps


class TestNativeRepresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime=NativeLLMRuntime(TinyTransformer(
            vocab=("key","sample","redacted","json","csv","allow",
                   "deny","read","write","task","one","two","three"),
            dim=8,ctx=64,seed=1,n_heads=2,d_ff=0,
        ))
        cls.cases=tuple(iter_challenges())

    def test_original_json_format_cannot_render_punctuation(self):
        case=next(x for x in self.cases if x.domain=="json_merge")
        result=inspect(self.runtime,case)
        self.assertFalse(result.exact_native_renderable)
        self.assertEqual(len(result.expected_sha256),64)

    def test_comma_delimited_format_not_reconstructible(self):
        case=next(x for x in self.cases if x.domain=="csv_row")
        result=inspect(self.runtime,case)
        self.assertFalse(result.exact_native_renderable)

    def test_uppercase_labels_not_renderable_with_lowercase_only(self):
        case=next(x for x in self.cases if x.domain=="uppercase")
        result=inspect(self.runtime,case)
        self.assertFalse(result.exact_native_renderable)

    def test_all_768_are_retained_in_diagnostic_denominator(self):
        result=full_audit(self.runtime)
        self.assertEqual(result["cases"],768)
        self.assertEqual(result["exact_renderable"]+result["unrenderable"],768)
        self.assertFalse(result["unrenderable_counted_as_pass"])

    def test_lexical_report_is_observational_only(self):
        result=gaps(self.runtime)
        self.assertEqual(len(result["domains"]),32)
        self.assertGreater(result["unknown_answer_tokens"],0)
        self.assertFalse(result["vocabulary_mutated"])
        self.assertFalse(result["release_certified"])


if __name__=="__main__":
    unittest.main()
