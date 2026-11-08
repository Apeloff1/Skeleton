"""Fail-closed regression tests for provider-neutral JSONL stream custody."""

import json
import unittest

from skeleton.inference.flgb_runtime import FLGBInferenceError, StreamDecoder


def frame(sequence, kind="text", payload="token"):
    return (json.dumps({"sequence": sequence, "kind": kind, "payload": payload}) + "\n").encode()


class StreamEventTypeFencingTests(unittest.TestCase):
    def test_valid_fragmented_stream_and_finalize(self):
        decoder = StreamDecoder()
        first = frame(0)
        self.assertEqual(decoder.feed(first[:4]), ())
        self.assertEqual(decoder.feed(first[4:])[0]["sequence"], 0)
        self.assertEqual(decoder.feed(frame(1, "final"))[0]["kind"], "final")
        self.assertEqual(decoder.finalize(), ())

    def test_non_integer_sequence_rejected_without_advancing_cursor(self):
        for bad in (False, True, 0.0, 1.0, None, "0", [], {}):
            with self.subTest(sequence=bad):
                decoder = StreamDecoder()
                with self.assertRaises(FLGBInferenceError):
                    decoder.feed(frame(bad))
                # An invalid cursor must never count as accepted.
                self.assertEqual(decoder._count, 0)

    def test_malformed_kind_fails_closed_without_python_type_error(self):
        for bad in (None, True, False, 0, [], {}, ["text"]):
            with self.subTest(kind=bad):
                decoder = StreamDecoder()
                with self.assertRaises(FLGBInferenceError):
                    decoder.feed(frame(0, bad))
                self.assertEqual(decoder._count, 0)

    def test_restart_requires_new_decoder_and_zero_sequence(self):
        old = StreamDecoder()
        self.assertEqual(old.feed(frame(0))[0]["sequence"], 0)
        new = StreamDecoder()
        with self.assertRaises(FLGBInferenceError):
            new.feed(frame(1))
        self.assertEqual(new._count, 0)
        self.assertEqual(new.feed(frame(0))[0]["sequence"], 0)

    def test_duplicate_cursor_rejected(self):
        decoder = StreamDecoder()
        decoder.feed(frame(0))
        with self.assertRaises(FLGBInferenceError):
            decoder.feed(frame(0))


if __name__ == "__main__":
    unittest.main()
