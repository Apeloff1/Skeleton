"""GB-30 SSE tests. Default off. Client reads 2 events when enabled."""

from __future__ import annotations

import unittest

from skeleton.telemetry import EventStore, PATH, Stream, capabilities


class TestDefaultOff(unittest.TestCase):
    def test_default_closed(self) -> None:
        store = EventStore()
        store.append("forge")
        store.append("gossip")
        s = Stream(store)
        self.assertFalse(s.open())
        self.assertEqual(s.client_read(2), [])

    def test_mobile_skips(self) -> None:
        s = Stream(EventStore(), enabled=True, mobile=True)
        self.assertFalse(s.open())


class TestClient(unittest.TestCase):
    def test_reads_two(self) -> None:
        store = EventStore()
        store.append("forge")
        store.append("gossip")
        frames = Stream(store, enabled=True).client_read(2)
        self.assertEqual(len(frames), 2)
        self.assertIn("event: forge", frames[0])
        self.assertIn("event: gossip", frames[1])
        self.assertNotIn("prose", frames[0])

    def test_caps_path(self) -> None:
        cap = capabilities()
        self.assertEqual(PATH, "/api/v1/events/stream")
        self.assertEqual(cap["contract"]["default_on"], 0)
        self.assertEqual(cap["contract"]["operator_routes"], 0)


if __name__ == "__main__":
    unittest.main()
