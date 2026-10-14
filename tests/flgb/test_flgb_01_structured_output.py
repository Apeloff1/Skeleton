import unittest
from skeleton.inference.structured_output import FLGBInferenceError, parse_structured_output
class TestStructuredOutput(unittest.TestCase):
    def test_duplicate_and_extra_keys_fail_closed(self):
        self.assertEqual(parse_structured_output('{"answer":1}', required_keys=("answer",), allowed_keys=("answer",))["answer"], 1)
        with self.assertRaises(FLGBInferenceError):
            parse_structured_output('{"a":1,"a":2}')
        with self.assertRaises(FLGBInferenceError):
            parse_structured_output('{"answer":1,"extra":2}', allowed_keys=("answer",))
if __name__ == "__main__": unittest.main()
