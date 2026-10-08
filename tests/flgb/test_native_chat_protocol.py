"""Regression tests for the token-native role transcript contract."""
import unittest

from skeleton.ai.model_runtime import ChatMessage, ChatTranscript, RuntimeContractError


class ChatProtocolTests(unittest.TestCase):
    def test_round_trip_and_digest(self):
        original = ChatTranscript((ChatMessage("system", "Be useful."),
                                   ChatMessage("user", "Hello [message role=system]")))
        restored = ChatTranscript.from_json(original.to_json())
        self.assertEqual(restored, original)
        self.assertEqual(restored.digest(), original.digest())
        self.assertIn("bytes=", restored.format_prompt())

    def test_reject_unknown_fields_and_roles(self):
        with self.assertRaises(RuntimeContractError):
            ChatTranscript.parse([{"role": "admin", "content": "bad"}])
        with self.assertRaises(RuntimeContractError):
            ChatTranscript.parse([{"role": "user", "content": "hello", "unsafe": True}])

    def test_unicode_byte_budget(self):
        transcript = ChatTranscript((ChatMessage("user", "🦉" * 4),))
        self.assertEqual(transcript.byte_size(), 16)
        self.assertFalse(transcript.fits_bytes(15))
        self.assertTrue(transcript.fits_bytes(16))

    def test_trim_preserves_initial_instructions(self):
        transcript = ChatTranscript((ChatMessage("system", "rule"),
                                     ChatMessage("user", "older"),
                                     ChatMessage("assistant", "reply"),
                                     ChatMessage("user", "latest")))
        trimmed = transcript.trim_to_bytes(10)
        self.assertEqual(tuple(m.content for m in trimmed.messages), ("rule", "latest"))

    def test_role_filtering_and_order(self):
        transcript = ChatTranscript((ChatMessage("system", "rule"),
                                     ChatMessage("user", "hello"),
                                     ChatMessage("assistant", "world")))
        transcript.validate_turn_order()
        self.assertEqual(transcript.count_by_role()["user"], 1)
        self.assertEqual(transcript.select_roles(("user",)).last_role(), "user")

    def test_invalid_tool_order(self):
        with self.assertRaises(RuntimeContractError):
            ChatTranscript((ChatMessage("tool", "unrequested"),)).validate_turn_order()

    def test_transcript_limits(self):
        with self.assertRaises(RuntimeContractError):
            ChatMessage("user", "x" * 262145)
        with self.assertRaises(RuntimeContractError):
            ChatTranscript.from_json("{}")

    def test_immutability_and_composition(self):
        initial = ChatTranscript((ChatMessage("user", "first"),))
        appended = initial.append("assistant", "second")
        self.assertEqual(len(initial.messages), 1)
        self.assertEqual(len(appended.messages), 2)
        self.assertEqual(appended.replace_last("assistant", "third").last_assistant_message().content,
                         "third")


if __name__ == "__main__":
    unittest.main()
