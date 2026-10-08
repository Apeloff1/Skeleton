import unittest
from skeleton.ai.model_runtime.tokenization import (
    ModelRuntimeError,
    TokenSequence,
    TokenizerContractError,
    deserialize_token_sequence,
    serialize_token_sequence,
)

D = "a" * 64


class TestTokenization(unittest.TestCase):
    def test_identity_and_bounds(self):
        seq = TokenSequence(D, (1, 2, 3), D)
        self.assertEqual(len(seq.digest), 64)
        with self.assertRaises(ModelRuntimeError):
            TokenSequence(D, (-1,), D)

    def test_serialization_round_trip_is_deterministic(self):
        seq = TokenSequence(D, (1, 2, 3), D)
        payload = serialize_token_sequence(seq)
        self.assertEqual(deserialize_token_sequence(payload), seq)
        self.assertEqual(serialize_token_sequence(deserialize_token_sequence(payload)), payload)

    def test_deserializer_rejects_bool_and_malformed_digest(self):
        bad_id = b'{"source_text_digest":"'+D.encode()+b'","token_ids":[true],"tokenizer_digest":"'+D.encode()+b'"}'
        with self.assertRaises(TokenizerContractError):
            deserialize_token_sequence(bad_id)
        bad_digest = b'{"source_text_digest":"'+D.encode()+b'","token_ids":[1],"tokenizer_digest":"xyz"}'
        with self.assertRaises(TokenizerContractError):
            deserialize_token_sequence(bad_digest)

    def test_deserializer_rejects_duplicate_json_fields(self):
        payload = (
            b'{"source_text_digest":"' + D.encode() +
            b'","token_ids":[1],"token_ids":[2],"tokenizer_digest":"' + D.encode() + b'"}'
        )
        with self.assertRaisesRegex(TokenizerContractError, "duplicate serialized JSON key"):
            deserialize_token_sequence(payload)

    def test_deserializer_rejects_unknown_shape(self):
        payload = b'{"source_text_digest":"'+D.encode()+b'","token_ids":[1],"tokenizer_digest":"'+D.encode()+b'","extra":1}'
        with self.assertRaises(TokenizerContractError):
            deserialize_token_sequence(payload)


if __name__ == "__main__":
    unittest.main()
