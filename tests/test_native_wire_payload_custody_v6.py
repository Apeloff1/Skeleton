"""Adversarial accelerator wire-envelope custody tests."""
import unittest
from datetime import datetime, timedelta, timezone

from skeleton.native.protocol import (
    ACCELERATION_PROTOCOL_ID, CURRENT_PROTOCOL_VERSION,
    AcceleratorProtocolError, make_request_envelope,
)


def envelope(payload):
    return make_request_envelope(
        protocol_id=ACCELERATION_PROTOCOL_ID,
        version=CURRENT_PROTOCOL_VERSION,
        operation="infer",
        payload=payload,
        deadline_utc=(datetime.now(timezone.utc) + timedelta(minutes=2))
        .isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


class WirePayloadCustodyTests(unittest.TestCase):
    def test_valid_nested_wire_payload(self):
        self.assertEqual(
            envelope({"tokens": [1, 2], "metadata": {"stop": False, "text": "ok"}})["payload"],
            {"tokens": [1, 2], "metadata": {"stop": False, "text": "ok"}},
        )

    def test_rejects_invalid_numeric_and_object_values(self):
        for payload in ({"x": float("nan")}, {"x": float("inf")},
                        {"x": object()}, {1: "not-text-key"}, {"x": b"bytes"}):
            with self.subTest(payload=str(payload)), self.assertRaises(AcceleratorProtocolError):
                envelope(payload)

    def test_rejects_cyclic_and_aliased_containers(self):
        cycle = []
        cycle.append(cycle)
        shared = [1]
        for payload in ({"x": cycle}, {"x": shared, "y": shared}):
            with self.assertRaises(AcceleratorProtocolError):
                envelope(payload)

    def test_rejects_excessive_depth_and_size(self):
        nested = {"leaf": True}
        for _ in range(18):
            nested = {"next": nested}
        huge_integer = 1 << (1_048_576 * 4 + 1)
        too_many_nodes = {
            "first": [None] * 131_072,
            "second": [None] * 131_072,
        }
        for payload in (nested, {"text": "x" * 1_048_577},
                        {"integer": huge_integer}, too_many_nodes):
            with self.assertRaises(AcceleratorProtocolError):
                envelope(payload)

    def test_rejects_non_mapping(self):
        with self.assertRaises(TypeError):
            envelope(["not", "mapping"])


if __name__ == "__main__":
    unittest.main()
