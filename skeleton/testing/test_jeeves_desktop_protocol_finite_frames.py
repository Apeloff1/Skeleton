"""Offline Jeeves stdio framing: finite JSON and bounded resource proof.

This suite uses BytesIO only. No GGUF, Tk, model provider, SQLite, or device is
started. These checks are not evidence of live-model inference.
"""
from __future__ import annotations

import io
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_protocol as frame


class DesktopPrivateFrameBoundaryTests(unittest.TestCase):
    def test_finite_command_roundtrip_remains_byte_exact(self):
        original = frame.command("turn", prompt="Compose an original game", request_id="req_123")
        wire = frame.encoded(original, limit=frame.MAX_INBOUND)
        result = frame.read_frame(io.BytesIO(wire), limit=frame.MAX_INBOUND)
        self.assertEqual(result, original)
        self.assertEqual(frame.require_command(result), original)

    def test_finite_response_roundtrip_keeps_native_provenance(self):
        original = frame.response("ok", release_certified=False, generated_tokens=2, loss=0.25)
        wire = frame.encoded(original, limit=frame.MAX_OUTBOUND)
        received = frame.read_frame(io.BytesIO(wire), limit=frame.MAX_OUTBOUND)
        self.assertEqual(received, original)
        self.assertIs(received["release_certified"], False)

    def test_exponential_overflow_is_rejected_before_response_interpretation(self):
        for token in ("1e9999", "-1e9999", "9e999", "-9e999", "1.0e9999"):
            with self.subTest(token=token):
                source = ('{"schema":"jeeves.desktop.response.v1","cost":'
                          + token + '}').encode("utf-8")
                with self.assertRaises(frame.DesktopProtocolHold):
                    frame.decoded(source, limit=frame.MAX_OUTBOUND)

    def test_literals_and_duplicate_keys_remain_forbidden(self):
        for raw in (b'{"value":NaN}', b'{"value":Infinity}',
                    b'{"value":-Infinity}', b'{"a":1,"a":2}'):
            with self.subTest(raw=raw):
                with self.assertRaises(frame.DesktopProtocolHold):
                    frame.decoded(raw, limit=frame.MAX_INBOUND)

    def test_lone_surrogates_in_values_and_keys_cannot_reach_gui(self):
        for raw in (b'{"message":"\\ud800"}', b'{"\\udfff":"value"}',
                    b'{"nested":["\\udc00"]}'):
            with self.subTest(raw=raw):
                with self.assertRaises(frame.DesktopProtocolHold):
                    frame.decoded(raw, limit=frame.MAX_INBOUND)

    def test_structural_depth_is_bounded_independently_of_byte_count(self):
        nested = "[" * (frame.MAX_FRAME_DEPTH + 5) + "0" + "]" * (frame.MAX_FRAME_DEPTH + 5)
        payload = nested.encode("ascii")
        self.assertLess(len(payload), frame.MAX_INBOUND)
        with self.assertRaises(frame.DesktopProtocolHold):
            frame.decoded(payload, limit=frame.MAX_INBOUND)

    def test_structural_node_limit_is_bounded_for_wide_lists(self):
        raw = json.dumps([0] * (frame.MAX_FRAME_NODES + 1), separators=(",", ":")).encode()
        self.assertLess(len(raw), frame.MAX_OUTBOUND)
        with self.assertRaises(frame.DesktopProtocolHold):
            frame.decoded(raw, limit=frame.MAX_OUTBOUND)

    def test_valid_finite_nested_data_is_retained(self):
        original = {"result": {"probability": 0.9999, "runs": [{"seed": 1}, {"seed": 2}]}}
        raw = json.dumps(original, separators=(",", ":")).encode()
        self.assertEqual(frame.decoded(raw, limit=frame.MAX_INBOUND), original)

    def test_deep_encoder_recursion_has_controlled_hold(self):
        value = 0
        for _ in range(1100):
            value = [value]
        with self.assertRaises(frame.DesktopProtocolHold):
            frame.encoded(value, limit=frame.MAX_OUTBOUND)

    def test_short_read_and_short_write_are_not_retried(self):
        with self.assertRaises(frame.DesktopProtocolHold):
            frame.read_frame(io.BytesIO(b"\x00\x00\x00\x10" + b"{}"), limit=frame.MAX_INBOUND)

        class ShortWriter(io.BytesIO):
            def write(self, payload):
                return len(payload) - 1

        with self.assertRaises(frame.DesktopProtocolHold):
            frame.write_frame(ShortWriter(), {"status": "ok"})

    def test_status_identity_is_bounded(self):
        with self.assertRaises(frame.DesktopProtocolHold):
            frame.response("s" * 65)
        self.assertEqual(frame.response("ready")["status"], "ready")

    def test_nested_Unicode_text_still_passes_exactly(self):
        raw = '{"text":"Jeeves — local AI 🚀","count":1.25}'.encode("utf-8")
        result = frame.decoded(raw, limit=frame.MAX_INBOUND)
        self.assertEqual(result["text"], "Jeeves — local AI 🚀")
        self.assertEqual(result["count"], 1.25)


if __name__ == "__main__":
    unittest.main()
