import unittest

from ai_tree_fill.ed25519_hold import Ed25519Hold
from ai_tree_fill.hybrid_rank import HybridRank, MemoryRetrievalSink, TranscriptVideoAdapter
from ai_tree_fill.memory_store import FenceError, MemoryDistributedBackend, StoreConflict


class StubFillTests(unittest.TestCase):
    def test_store_cas_and_fence(self):
        store = MemoryDistributedBackend()
        first = store.put_if_absent("ai", "k", {"n": 1})
        with self.assertRaises(StoreConflict):
            store.put_if_absent("ai", "k", {"n": 2})
        second = store.compare_and_swap("ai", "k", expected_revision=first.revision, value={"n": 2})
        self.assertEqual(second.revision, 2)
        lease = store.acquire_lease("ai", "k", owner="p5", ttl_seconds=30)
        swapped = store.fenced_compare_and_swap(lease, expected_revision=2, value={"n": 3})
        self.assertEqual(swapped.revision, 3)
        store.release_lease(lease)
        with self.assertRaises(FenceError):
            store.require_fence(lease)

    def test_sink_rank_and_video(self):
        sink = MemoryRetrievalSink()
        sink.upsert({"content_hash": "h1", "body": "VOL-113 github.com/Apeloff1/Skeleton", "metadata": {}})
        self.assertIn("h1", sink.rows)
        rank = HybridRank(
            [{"id": "a", "room": "forge", "text": "forge plan VOL-113"}, {"id": "b", "room": "court", "text": "other"}],
            [("a", "b")],
        )
        hits = rank.retrieve("forge plan", "forge")
        self.assertEqual(hits[0]["id"], "a")
        frames = list(TranscriptVideoAdapter(["line one", "line two"]).observations("https://example.test/v"))
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].modality, "transcript")

    def test_ed25519_roundtrip(self):
        hold = Ed25519Hold.mint()
        envelope = hold.sign(b"AIFT-FILL")
        self.assertTrue(hold.verify(b"AIFT-FILL", envelope))
        self.assertEqual(len(envelope.signature), 128)
        self.assertEqual(hold.fingerprint(), __import__("hashlib").sha256(bytes.fromhex(hold.public_hex)).hexdigest())


if __name__ == "__main__":
    unittest.main()
