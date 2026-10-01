from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from skeleton.native.protocol import (
    ACCELERATION_PROTOCOL_ID,
    CURRENT_PROTOCOL_VERSION,
    AcceleratorProtocolError,
    ProtocolVersion,
    make_request_envelope,
    negotiate_version,
)


class AccelerationProtocolTests(unittest.TestCase):
    def test_highest_exact_shared_version_wins(self) -> None:
        selected = negotiate_version(
            [ProtocolVersion(1, 0), ProtocolVersion(1, 1)],
            [ProtocolVersion(1, 0), ProtocolVersion(2, 0)],
        )
        self.assertEqual(str(selected), "1.0")

    def test_noncanonical_version_text_rejects(self) -> None:
        for raw in ("01.0", "1.00", "00.01"):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "canonical decimal form"):
                    ProtocolVersion.parse(raw)

    def test_wire_major_negotiation(self) -> None:
        from skeleton.native.protocol import (
            CURRENT_PROTOCOL_VERSION,
            negotiate_wire_major,
        )
        self.assertEqual(
            negotiate_wire_major(CURRENT_PROTOCOL_VERSION.major),
            CURRENT_PROTOCOL_VERSION,
        )
        with self.assertRaises(AcceleratorProtocolError):
            negotiate_wire_major(2)
        with self.assertRaises(AcceleratorProtocolError):
            negotiate_wire_major(True)

    def test_unknown_version_rejects(self) -> None:
        with self.assertRaises(AcceleratorProtocolError):
            negotiate_version(
                [ProtocolVersion(1, 0)],
                [ProtocolVersion(2, 0)],
            )

    def test_request_envelope_requires_future_deadline(self) -> None:
        deadline = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        payload = make_request_envelope(
            protocol_id="skeleton.acceleration.rpc",
            version=ProtocolVersion(1, 0),
            operation="vector.search",
            payload={"k": 5},
            deadline_utc=deadline,
            request_id="req-1",
        )
        self.assertEqual(payload["version"], "1.0")
        self.assertEqual(payload["request_id"], "req-1")

        with self.assertRaisesRegex(ValueError, "future"):
            make_request_envelope(
                protocol_id="skeleton.acceleration.rpc",
                version=ProtocolVersion(1, 0),
                operation="vector.search",
                payload={},
                deadline_utc="2000-01-01T00:00:00+00:00",
                request_id="req-2",
            )


    def test_rejects_wrong_protocol_id(self) -> None:
        deadline = (
            datetime.now(timezone.utc) + timedelta(minutes=1)
        ).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(
            AcceleratorProtocolError,
            "unsupported accelerator protocol id",
        ):
            make_request_envelope(
                protocol_id="other.protocol",
                version=CURRENT_PROTOCOL_VERSION,
                operation="vector.search",
                payload={},
                deadline_utc=deadline,
            )

    def test_rejects_unsupported_envelope_version(self) -> None:
        deadline = (
            datetime.now(timezone.utc) + timedelta(minutes=1)
        ).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(
            AcceleratorProtocolError,
            "unsupported accelerator protocol version",
        ):
            make_request_envelope(
                protocol_id=ACCELERATION_PROTOCOL_ID,
                version=ProtocolVersion(2, 0),
                operation="vector.search",
                payload={},
                deadline_utc=deadline,
            )


if __name__ == "__main__":
    unittest.main()
